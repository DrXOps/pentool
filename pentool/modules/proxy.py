"""Ядро прокси-сервера: HTTP/HTTPS перехват, scope."""

from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal

from pentool.core.logging import get_logger
from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
from pentool.modules.websocket_handler import WebSocketHandler
from pentool.utils.cert import create_ssl_context_for_domain, load_or_create_ca
from pentool.utils.http_client import HTTPClient
from pentool.utils.parser import (
    ParsedRequest,
    ParsedResponse,
    build_http_request,
    parse_http_request,
    parse_http_response,
)

logger = get_logger(__name__)

# Максимальный размер тела запроса/ответа для чтения (10 МБ)
_MAX_BODY = 10 * 1024 * 1024

# Таймаут чтения данных из сокета (секунды)
_READ_TIMEOUT = 30.0

# Таймаут ожидания решения пользователя при перехвате (секунды)
_INTERCEPT_TIMEOUT = 300.0


InterceptState = Literal["waiting", "forwarded", "dropped"]


@dataclass
class InterceptedRequest:
    """Перехваченный запрос с состоянием и ответом."""

    id: str
    method: str
    url: str
    headers: dict[str, str]
    body: str
    timestamp: datetime
    state: InterceptState = "waiting"
    response: ParsedResponse | None = None
    is_https: bool = False
    is_websocket: bool = False
    # asyncio.Event — устанавливается когда пользователь принял решение
    _decision_event: asyncio.Event = field(
        default_factory=asyncio.Event, repr=False, compare=False
    )
    # Если пользователь отредактировал запрос перед forwarding
    _modified_raw: str | None = field(default=None, repr=False, compare=False)

    def to_parsed_request(self) -> ParsedRequest:
        """Конвертировать в ParsedRequest для отправки через HTTPClient."""
        return ParsedRequest(
            method=self.method,
            url=self.url,
            headers=self.headers,
            body=self.body,
        )

    def to_dict(self) -> dict:
        """Сериализовать перехваченный запрос в словарь (полный формат с response).

        Симметрично from_dict() — пригоден для project persistence.
        """
        resp = self.response
        return {
            "id": self.id,
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
            "body": self.body if isinstance(self.body, str) else self.body.decode("utf-8", errors="replace"),
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "is_https": self.is_https,
            "is_websocket": self.is_websocket,
            "response": {
                "status": resp.status,
                "reason": resp.reason,
                "headers": resp.headers,
                "body": resp.body if isinstance(resp.body, str) else resp.body.decode("utf-8", errors="replace"),
            } if resp else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterceptedRequest":
        """Восстановить InterceptedRequest из словаря (десериализация из проекта)."""
        from datetime import datetime, timezone
        ts_raw = data.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw)
        except Exception:
            ts = datetime.now(timezone.utc)

        resp_data = data.get("response")
        response = None
        if resp_data:
            response = ParsedResponse(
                status=resp_data.get("status", 0),
                reason=resp_data.get("reason", ""),
                headers=resp_data.get("headers", {}),
                body=resp_data.get("body", ""),
            )

        return cls(
            id=data["id"],
            method=data["method"],
            url=data["url"],
            headers=data.get("headers", {}),
            body=data.get("body", ""),
            timestamp=ts,
            state=data.get("state", "forwarded"),
            is_https=data.get("is_https", False),
            is_websocket=data.get("is_websocket", False),
            response=response,
        )


class ProxyServer:
    """Асинхронный HTTP/HTTPS прокси-сервер с перехватом трафика.

    Запускается как asyncio-сервер. Поддерживает:
    - Перехват HTTP и HTTPS (через CONNECT + динамические сертификаты)
    - Интерактивный режим (intercept): приостановка запроса до решения пользователя
    - Scope: фильтрация хостов
    - Match/Replace: автоматическая замена в запросах/ответах (через MatchReplaceEngine)
    - Логирование в SQLite через core/database
    - Уведомления через EventBus: ProxyRequestCaptured, ProxyRequestCompleted
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        cert_dir: str = "/tmp/pentool_certs",
        db_path: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.cert_dir = cert_dir
        self.db_path = db_path

        self.intercept_enabled: bool = False
        self.scope: list[str] = []  # Пустой = перехватывать всё

        # Match/Replace через выделенный движок (Sprint 5)
        self._match_replace_engine = MatchReplaceEngine()
        # WebSocket-обработчик (Sprint 5)
        self._ws_handler = WebSocketHandler()

        # Очередь запросов, ожидающих решения в интерактивном режиме
        self.intercept_queue: asyncio.Queue[InterceptedRequest] = asyncio.Queue()

        # Все перехваченные запросы (история в памяти, макс. 10000)
        self.requests: list[InterceptedRequest] = []
        self._requests_max = 10000

        self._server: asyncio.AbstractServer | None = None
        self._ca_cert_path: str | None = None
        self._ca_key_path: str | None = None
        self._running = False
        # Луп прокси-треда — сохраняется при старте, нужен для thread-safe wakeup
        self._loop: asyncio.AbstractEventLoop | None = None
        # Singleton HTTP-клиент — не создавать на каждый запрос
        self._http_client: HTTPClient | None = None

    async def start(self) -> None:
        # Сохраняем луп текущего треда — нужен для thread-safe wakeup event'ов
        self._loop = asyncio.get_running_loop()
        # Загрузить или создать CA
        self._ca_cert_path, self._ca_key_path = load_or_create_ca(self.cert_dir)
        logger.info("CA certificate: %s", self._ca_cert_path)

        self._server = await asyncio.start_server(
            self._handle_client,
            host=self.host,
            port=self.port,
        )
        self._running = True
        addr = self._server.sockets[0].getsockname()
        logger.info("Proxy listening on %s:%s", addr[0], addr[1])

    async def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        # Закрыть singleton HTTP-клиент
        if self._http_client:
            try:
                await self._http_client.close()
            except Exception as e:
                logger.warning("ProxyServer.stop: http_client.close() error: %s", e)
            self._http_client = None
        logger.info("Proxy stopped")

    async def serve_forever(self) -> None:
        await self.start()
        async with self._server:
            await self._server.serve_forever()

    @property
    def is_running(self) -> bool:
        """True если прокси-сервер запущен и слушает порт."""
        return self._running and self._server is not None

    def set_scope(self, hosts: list[str]) -> None:
        self.scope = [h.lower().strip() for h in hosts if h.strip()]

    @property
    def match_replace_rules(self) -> list[MatchReplaceRule]:
        return self._match_replace_engine.rules

    @match_replace_rules.setter
    def match_replace_rules(self, rules: list[MatchReplaceRule]) -> None:
        self._match_replace_engine.set_rules(rules)

    def is_in_scope(self, host: str) -> bool:
        """Проверить, входит ли хост в scope.

        Если scope пустой — все хосты в scope.
        Поддерживает wildcards: *.example.com
        """
        if not self.scope:
            return True
        host = host.lower().split(":")[0]  # убрать порт
        for pattern in self.scope:
            pattern = pattern.split(":")[0]
            if pattern.startswith("*."):
                suffix = pattern[1:]  # ".example.com"
                if host.endswith(suffix) or host == suffix[1:]:
                    return True
            elif pattern == host:
                return True
        return False

    def forward(self, req_id: str, modified_raw: str | None = None) -> None:
        req = self._find_request(req_id)
        if req and req.state == "waiting":
            req._modified_raw = modified_raw
            req.state = "forwarded"
            self._set_event_threadsafe(req._decision_event)

    def drop(self, req_id: str) -> None:
        """Отбросить перехваченный запрос."""
        req = self._find_request(req_id)
        if req and req.state == "waiting":
            req.state = "dropped"
            self._set_event_threadsafe(req._decision_event)

    def _set_event_threadsafe(self, event: asyncio.Event) -> None:
        """Разбудить asyncio.Event из любого треда."""
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(event.set)
        else:
            # Запасной вариант — прямой вызов (если луп не запущен)
            try:
                event.set()
            except Exception as e:
                logger.warning("_set_event_threadsafe: failed to set event: %s", e)

    def set_intercept(self, enabled: bool) -> None:
        """Thread-safe установка флага intercept_enabled из любого треда.

        При вызове из TUI-треда (Textual) использует call_soon_threadsafe
        чтобы избежать race condition: proxy-loop читает intercept_enabled
        в asyncio-корутине, и прямая запись из другого треда может привести
        к тому, что флаг изменится уже после проверки.
        """
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(setattr, self, "intercept_enabled", enabled)
        else:
            self.intercept_enabled = enabled

    def _find_request(self, req_id: str) -> InterceptedRequest | None:
        for r in reversed(self.requests):
            if r.id == req_id:
                return r
        return None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Обработать входящее клиентское соединение."""
        try:
            await self._process_connection(reader, writer)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        except Exception as exc:
            logger.warning("Connection error: %s", exc, exc_info=True)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.debug("_handle_client: writer.close() error (connection already reset?): %s", e)

    async def _process_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Прочитать первый запрос и решить: HTTP или HTTPS CONNECT."""
        try:
            raw_request = await asyncio.wait_for(
                self._read_http_message(reader),
                timeout=_READ_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return

        if not raw_request.strip():
            return

        first_line = raw_request.split("\n")[0].strip()

        if first_line.upper().startswith("CONNECT "):
            await self._handle_connect(raw_request, reader, writer)
        else:
            await self._handle_http(raw_request, reader, writer, is_https=False)

    async def _handle_connect(
        self,
        raw_connect: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Обработать CONNECT-метод: установить HTTPS-туннель."""
        first_line = raw_connect.split("\n")[0].strip()
        # CONNECT example.com:443 HTTP/1.1
        parts = first_line.split()
        if len(parts) < 2:
            return

        host_port = parts[1]
        domain = host_port.split(":")[0]

        # Ответить 200 Connection Established
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()

        # Если хост вне scope — просто тунелируем без перехвата
        if not self.is_in_scope(domain):
            await self._tunnel_raw(domain, host_port, reader, writer)
            return

        # Генерировать SSL-контекст для домена (с disk-cache через cert_dir)
        try:
            ssl_ctx = create_ssl_context_for_domain(
                domain, self._ca_cert_path, self._ca_key_path,
                cert_dir=self.cert_dir,
            )
        except Exception as exc:
            logger.warning("SSL context error for %s: %s", domain, exc)
            return

        # Поднять TLS через start_tls с новым StreamReaderProtocol.
        # connection_made нужно вызвать ДО start_tls чтобы протокол
        # знал о транспорте и handshake прошёл корректно.
        logger.debug("TLS: upgrading %s", domain)
        try:
            loop = asyncio.get_running_loop()
            raw_transport = writer.transport

            tls_reader = asyncio.StreamReader()
            tls_proto  = asyncio.StreamReaderProtocol(tls_reader)
            tls_proto.connection_made(raw_transport)

            ssl_transport = await loop.start_tls(
                raw_transport, tls_proto, ssl_ctx, server_side=True
            )
            tls_writer = asyncio.StreamWriter(ssl_transport, tls_proto, tls_reader, loop)
            logger.debug("TLS: upgrade OK for %s", domain)
        except Exception as exc:
            logger.warning("TLS upgrade failed for %s: %s", domain, exc)
            return

        # Читать HTTPS-запросы
        try:
            while True:
                raw_req = await asyncio.wait_for(
                    self._read_http_message(tls_reader),
                    timeout=_READ_TIMEOUT,
                )
                if not raw_req.strip():
                    break

                # Вставить схему https в запрос
                if not raw_req.startswith("http"):
                    first = raw_req.split("\n")[0]
                    method, path, *rest = first.split()
                    if not path.startswith("http"):
                        full_url = f"https://{host_port}{path}"
                        raw_req = raw_req.replace(first, f"{method} {full_url} HTTP/1.1", 1)

                response = await self._handle_http(
                    raw_req, tls_reader, tls_writer, is_https=True
                )
                if response is None:
                    break
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                tls_writer.close()
            except Exception as e:
                logger.debug("_handle_connect: tls_writer.close() error: %s", e)

    async def _tunnel_raw(
        self,
        domain: str,
        host_port: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Прозрачный TCP-туннель для хостов вне scope."""
        port = int(host_port.split(":")[1]) if ":" in host_port else 443
        try:
            rem_reader, rem_writer = await asyncio.open_connection(domain, port)
        except Exception as exc:
            logger.debug("Tunnel connect failed %s: %s", host_port, exc)
            return

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await src.read(4096)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
                pass  # нормальное завершение TCP-туннеля
            except Exception as e:
                logger.debug("_tunnel_raw pipe error: %s", e)
            finally:
                try:
                    dst.close()
                except Exception as e:
                    logger.debug("_tunnel_raw dst.close() error: %s", e)

        await asyncio.gather(
            pipe(reader, rem_writer),
            pipe(rem_reader, writer),
            return_exceptions=True,
        )

    async def _handle_http(
        self,
        raw_request: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        is_https: bool = False,
    ) -> ParsedResponse | None:
        """Обработать HTTP-запрос: scope, match/replace, перехват, отправка."""
        try:
            req = parse_http_request(raw_request)
        except ValueError as exc:
            logger.debug("Parse error: %s", exc)
            return None

        host = req.host.split(":")[0]
        logger.debug("PROXY: _handle_http: %s %s (https=%s, intercept=%s, in_scope=%s)",
                    req.method, req.url, is_https, self.intercept_enabled, self.is_in_scope(host))

        # Проверить scope (для HTTP; HTTPS уже проверен в _handle_connect)
        if not is_https and not self.is_in_scope(host):
            logger.debug("PROXY: _handle_http: host %s out of scope, forwarding direct", host)
            return await self._forward_direct(req, writer)

        # Применить match/replace к запросу (через engine)
        raw_request = self._request_to_raw(req)
        modified_raw = self._match_replace_engine.apply_to_request(raw_request)
        if modified_raw != raw_request:
            try:
                req = parse_http_request(modified_raw)
            except ValueError:
                pass

        # Определить WebSocket-соединение (по заголовку Upgrade: websocket)
        is_websocket = req.headers.get("Upgrade", "").lower() == "websocket"

        # Создать InterceptedRequest
        ireq = InterceptedRequest(
            id=str(uuid.uuid4())[:12],
            method=req.method,
            url=req.url,
            headers=dict(req.headers),
            body=req.body,
            timestamp=datetime.now(timezone.utc),
            is_https=is_https,
            is_websocket=is_websocket,
        )
        self._add_request(ireq)

        # Уведомить подписчиков через EventBus (основной канал)
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ProxyRequestCaptured
            from urllib.parse import urlparse as _urlparse
            _host = _urlparse(ireq.url).hostname or ""
            get_event_bus().emit(ProxyRequestCaptured(
                source="proxy",
                request_id=ireq.id,
                method=ireq.method,
                url=ireq.url,
                host=_host,
                request=ireq,
            ))
        except Exception as exc:
            logger.debug("EventBus emit ProxyRequestCaptured error: %s", exc)

        # Интерактивный перехват
        if self.intercept_enabled:
            logger.debug("INTERCEPT: waiting for decision on %s %s (id=%s, event_set=%s, loop=%s)",
                        ireq.method, ireq.url, ireq.id,
                        ireq._decision_event.is_set(), self._loop)
            await self.intercept_queue.put(ireq)
            try:
                await asyncio.wait_for(
                    ireq._decision_event.wait(), timeout=_INTERCEPT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning("INTERCEPT: timeout on %s — request dropped after %.0fs", ireq.id, _INTERCEPT_TIMEOUT)
                ireq.state = "dropped"

            logger.debug("INTERCEPT: decision=%s on %s", ireq.state, ireq.id)
            if ireq.state == "dropped":
                writer.write(b"HTTP/1.1 502 Dropped by Proxy\r\n\r\n")
                await writer.drain()
                return None

            # Пользователь мог отредактировать запрос
            if ireq._modified_raw:
                try:
                    req = parse_http_request(ireq._modified_raw)
                    ireq.method = req.method
                    ireq.url = req.url
                    ireq.headers = dict(req.headers)
                    ireq.body = req.body
                except ValueError:
                    pass

        # WebSocket upgrade — отдельный путь (нужен raw TCP-туннель)
        if is_websocket:
            await self._handle_websocket(req, ireq, reader, writer)
            return None

        # Отправить запрос к целевому серверу
        response = await self._send_request(req)

        if response is None:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\nProxy error")
            await writer.drain()
            ireq.state = "forwarded"
            ireq.response = None
            return None

        # Применить match/replace к ответу (через engine)
        resp_raw = self._response_to_raw(response)
        modified_resp_raw = self._match_replace_engine.apply_to_response(resp_raw)
        if modified_resp_raw != resp_raw:
            try:
                response = parse_http_response(modified_resp_raw)
            except ValueError:
                pass

        ireq.response = response
        if ireq.state == "waiting":
            ireq.state = "forwarded"

        # Уведомить подписчиков через EventBus (основной канал)
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ProxyRequestCompleted
            status = ireq.response.status if ireq.response else 0
            get_event_bus().emit(ProxyRequestCompleted(
                source="proxy",
                request_id=ireq.id,
                status_code=status,
                request=ireq,
            ))
        except Exception as exc:
            logger.debug("EventBus emit ProxyRequestCompleted error: %s", exc)

        # Отправить ответ клиенту (сырые байты без перекодирования)
        writer.write(self._response_to_bytes(response))
        await writer.drain()

        return response

    # ── WebSocket support (делегируется в WebSocketHandler) ──────────────────

    @staticmethod
    def _parse_ws_frame(data: bytes) -> tuple[int, bool, bytes, int] | None:
        """Обратная совместимость — делегирует в WebSocketHandler.parse_frame."""
        return WebSocketHandler.parse_frame(data)

    @staticmethod
    def _build_ws_frame(opcode: int, payload: bytes, mask: bool = False) -> bytes:
        """Обратная совместимость — делегирует в WebSocketHandler.build_frame."""
        return WebSocketHandler.build_frame(opcode, payload, mask)

    async def _ws_tunnel(
        self,
        request_id: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        srv_reader: asyncio.StreamReader,
        srv_writer: asyncio.StreamWriter,
    ) -> None:
        """Обратная совместимость — делегирует в WebSocketHandler.tunnel."""
        await self._ws_handler.tunnel(
            request_id=request_id,
            client_reader=client_reader,
            client_writer=client_writer,
            srv_reader=srv_reader,
            srv_writer=srv_writer,
        )

    async def _handle_websocket(
        self,
        req,
        ireq,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        """Обратная совместимость — делегирует в WebSocketHandler.connect_and_handle."""
        await self._ws_handler.connect_and_handle(
            req=req,
            ireq=ireq,
            client_reader=client_reader,
            client_writer=client_writer,
        )
    async def _forward_direct(
        self,
        req: ParsedRequest,
        writer: asyncio.StreamWriter,
    ) -> ParsedResponse | None:
        """Переслать запрос без перехвата (хост вне scope)."""
        response = await self._send_request(req)
        if response:
            writer.write(self._response_to_bytes(response))
            await writer.drain()
        return response

    async def _send_request(self, req: ParsedRequest) -> ParsedResponse | None:
        try:
            # Используем singleton-клиент для connection pooling
            if self._http_client is None:
                self._http_client = HTTPClient(verify_ssl=False, timeout=30.0)
            return await self._http_client.send(req)
        except Exception as exc:
            logger.warning("Request failed %s %s: %s", req.method, req.url, exc)
            return None

    async def _read_http_message(self, reader: asyncio.StreamReader) -> str:
        """Прочитать HTTP-сообщение (заголовки + тело по Content-Length)."""
        # Читаем заголовки построчно до пустой строки
        header_lines: list[bytes] = []
        while True:
            try:
                line = await reader.readline()
            except asyncio.IncompleteReadError:
                break
            if not line or line in (b"\r\n", b"\n"):
                header_lines.append(line)
                break
            header_lines.append(line)

        if not header_lines:
            return ""

        headers_raw = b"".join(header_lines)

        # Определить Content-Length для чтения тела
        content_length = 0
        for line in header_lines:
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded.lower().startswith("content-length:"):
                try:
                    content_length = int(decoded.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break

        body = b""
        if content_length > 0:
            to_read = min(content_length, _MAX_BODY)
            try:
                body = await asyncio.wait_for(
                    reader.readexactly(to_read), timeout=_READ_TIMEOUT
                )
            except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                pass

        return (headers_raw + body).decode("utf-8", errors="replace")

    def _add_request(self, req: InterceptedRequest) -> None:
        self.requests.append(req)
        if len(self.requests) > self._requests_max:
            self.requests = self.requests[-self._requests_max:]

    def get_requests(
        self,
        limit: int = 100,
        method: str | None = None,
        host: str | None = None,
    ) -> list[InterceptedRequest]:
        result = list(reversed(self.requests))
        if method:
            result = [r for r in result if r.method.upper() == method.upper()]
        if host:
            result = [r for r in result if host.lower() in r.url.lower()]
        return result[:limit]

    def clear_requests(self) -> None:
        self.requests.clear()


    @staticmethod
    def _request_to_raw(req: "ParsedRequest") -> str:
        """Сериализовать ParsedRequest в сырую HTTP-строку (для match-replace)."""
        lines = [f"{req.method} {req.url} HTTP/1.1"]
        for k, v in req.headers.items():
            lines.append(f"{k}: {v}")
        raw = "\r\n".join(lines) + "\r\n\r\n"
        if req.body:
            raw += req.body
        return raw

    @staticmethod
    def _response_to_raw(resp: ParsedResponse) -> str:
        """Сериализовать ParsedResponse в сырую HTTP-строку (для TUI/match-replace)."""
        lines = [f"{resp.http_version} {resp.status} {resp.reason}"]
        for k, v in resp.headers.items():
            lines.append(f"{k}: {v}")
        raw = "\r\n".join(lines) + "\r\n\r\n"
        if resp.body:
            raw += resp.body
        return raw

    @staticmethod
    def _response_to_bytes(resp: ParsedResponse) -> bytes:
        """Сериализовать ParsedResponse в байты для отправки браузеру.

        aiohttp уже декодировал gzip/deflate и убрал chunked — нужно
        почистить соответствующие заголовки и выставить правильный Content-Length.
        """
        # Тело — сырые байты (уже декодированные aiohttp)
        if resp._raw_body is not None:
            body_bytes = resp._raw_body
        elif resp.body:
            body_bytes = resp.body.encode("utf-8", errors="replace")
        else:
            body_bytes = b""

        # Заголовки: убрать те что стали невалидны после декодирования aiohttp
        skip = {"transfer-encoding", "content-encoding", "content-length"}
        lines = [f"{resp.http_version} {resp.status} {resp.reason}"]
        for k, v in resp.headers.items():
            if k.lower() in skip:
                continue
            lines.append(f"{k}: {v}")
        # Выставить актуальный Content-Length
        lines.append(f"Content-Length: {len(body_bytes)}")

        header_bytes = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8", errors="replace")
        return header_bytes + body_bytes

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "host": self.host,
            "port": self.port,
            "intercept_enabled": self.intercept_enabled,
            "scope": self.scope,
            "requests_count": len(self.requests),
            "rules_count": len(self.match_replace_rules),
            "waiting_count": sum(1 for r in self.requests if r.state == "waiting"),
        }
