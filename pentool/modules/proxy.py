"""Proxy server core: HTTP/HTTPS interception, scope."""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from pentool.core.logging import get_logger
from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
from pentool.modules.websocket_handler import WebSocketHandler
from pentool.utils.cert import create_ssl_context_for_domain, load_or_create_ca
from pentool.utils.http_client import HTTPClient
from pentool.utils.scope import host_in_scope
from pentool.utils.parser import (
    ParsedRequest,
    ParsedResponse,
    parse_http_request,
    parse_http_response,
)

logger = get_logger(__name__)

# Maximum request/response body size to read (10 MB)
_MAX_BODY = 10 * 1024 * 1024

# Socket read timeout (seconds)
_READ_TIMEOUT = 30.0

# Timeout waiting for user decision during interception (seconds)
_INTERCEPT_TIMEOUT = 300.0


InterceptState = Literal["waiting", "forwarded", "dropped"]


@dataclass
class InterceptedRequest:
    """Intercepted request with state and response."""

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
    # asyncio.Event — set when the user has made a decision
    _decision_event: asyncio.Event = field(
        default_factory=asyncio.Event, repr=False, compare=False
    )
    # If the user edited the request before forwarding
    _modified_raw: str | None = field(default=None, repr=False, compare=False)

    def to_parsed_request(self) -> ParsedRequest:
        """Convert to ParsedRequest for sending via HTTPClient."""
        return ParsedRequest(
            method=self.method,
            url=self.url,
            headers=self.headers,
            body=self.body,
        )

    def to_dict(self) -> dict:
        """Serialize the intercepted request to a dict (full format with response).

        Symmetric with from_dict() — suitable for project persistence.
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
        """Restore InterceptedRequest from a dict (deserialization from project)."""
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
    """Asynchronous HTTP/HTTPS proxy server with traffic interception.

    Runs as an asyncio server. Supports:
    - HTTP and HTTPS interception (via CONNECT + dynamic certificates)
    - Interactive mode (intercept): pauses request until user decision
    - Scope: host filtering
    - Match/Replace: automatic replacement in requests/responses (via MatchReplaceEngine)
    - Logging to SQLite via core/database
    - Notifications via EventBus: ProxyRequestCaptured, ProxyRequestCompleted
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
        self.scope: list[str] = []  # Empty = intercept everything
        # When False (default), scope is informational only — ALL traffic is
        # captured/shown regardless of self.scope. Scope filtering (dropping
        # out-of-scope requests from capture) only takes effect when this is
        # explicitly turned on via the "Skip out-of-scope" toggle button.
        # Without this flag, a leftover/stale `scope` list (e.g. saved from a
        # previous project) would silently blackhole all non-matching traffic
        # the moment the proxy starts, with no visible indication why.
        self.enforce_scope: bool = False

        # Match/Replace via dedicated engine
        self._match_replace_engine = MatchReplaceEngine()
        # WebSocket handler
        self._ws_handler = WebSocketHandler()

        # Queue of requests waiting for decision in interactive mode
        self.intercept_queue: asyncio.Queue[InterceptedRequest] = asyncio.Queue()

        # All intercepted requests (in-memory history, bounded ring).
        # Full HTTP history is persisted to SQLite via HttpStorage — this
        # in-memory list only backs the legacy proxy.get_requests() API
        # (Repeater "load from history", project export/import,
        # reload_from_proxy() reconstruction). Lowered from 10000 to 1000:
        # each entry holds a full InterceptedRequest (headers + body +
        # response), and the persistent source of truth is SQLite, not this
        # list — 1000 is plenty for the legacy in-memory consumers above.
        # Mutated from the proxy's own thread (_add_request) and read from
        # the TUI thread (get_requests, _find_request, export/import) —
        # protect with a lock to avoid race conditions (torn reads, list
        # mutation during iteration).
        self._requests_lock = threading.Lock()
        self.requests: list[InterceptedRequest] = []
        self._requests_max = 1000


        self._server: asyncio.AbstractServer | None = None
        self._ca_cert_path: str | None = None
        self._ca_key_path: str | None = None
        self._running = False
        # Proxy thread loop — saved on start, needed for thread-safe wakeup
        self._loop: asyncio.AbstractEventLoop | None = None
        # Singleton HTTP client — do not create on every request
        self._http_client: HTTPClient | None = None

    async def start(self) -> None:
        # Save the current thread's loop — needed for thread-safe event wakeup
        self._loop = asyncio.get_running_loop()
        # Load or create CA
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
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.debug("ProxyServer.stop: wait_closed timeout, continuing")
            self._server = None
        # Close singleton HTTP client
        if self._http_client:
            try:
                await self._http_client.close()
            except Exception as e:
                logger.warning("ProxyServer.stop: http_client.close() error: %s", e)
            self._http_client = None
        # Cancel all remaining active tasks (open TLS tunnels, keep-alive
        # connections, intercept waits) so the event loop can exit promptly.
        # Without this, _handle_connect loops on _READ_TIMEOUT=30s and
        # _INTERCEPT_TIMEOUT=300s — the proxy thread would not exit for up to
        # 5 minutes after stop(), blocking project switches and restarts.
        loop = asyncio.get_running_loop()
        current = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks(loop) if t is not current and not t.done()]
        if pending:
            logger.debug("ProxyServer.stop: cancelling %d active task(s)", len(pending))
            for task in pending:
                task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                logger.debug("ProxyServer.stop: task cancellation timed out")
        logger.info("Proxy stopped")

    async def serve_forever(self) -> None:
        await self.start()
        async with self._server:
            await self._server.serve_forever()

    @property
    def is_running(self) -> bool:
        """True if the proxy server is running and listening on the port."""
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
        """Check if a host is in scope.

        If scope is empty — all hosts are in scope.
        Supports wildcards: *.example.com

        Delegates to the shared pentool.utils.scope.host_in_scope() —
        also used by AsyncSpider (modules/spider.py) so both modules
        implement scope matching once instead of twice.
        """
        return host_in_scope(host, self.scope)

    def forward(self, req_id: str, modified_raw: str | None = None) -> None:
        req = self._find_request(req_id)
        if req and req.state == "waiting":
            req._modified_raw = modified_raw
            req.state = "forwarded"
            self._set_event_threadsafe(req._decision_event)

    def drop(self, req_id: str) -> None:
        """Drop an intercepted request."""
        req = self._find_request(req_id)
        if req and req.state == "waiting":
            req.state = "dropped"
            self._set_event_threadsafe(req._decision_event)

    def _set_event_threadsafe(self, event: asyncio.Event) -> None:
        """Wake up an asyncio.Event from any thread."""
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(event.set)
        else:
            # Fallback — direct call (if loop is not running)
            try:
                event.set()
            except Exception as e:
                logger.warning("_set_event_threadsafe: failed to set event: %s", e)

    def set_intercept(self, enabled: bool) -> None:
        """Thread-safe setting of intercept_enabled flag from any thread.

        When called from the TUI thread (Textual) uses call_soon_threadsafe
        to avoid race conditions: the proxy loop reads intercept_enabled
        in an asyncio coroutine, and a direct write from another thread may
        cause the flag to change after the check.
        """
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(setattr, self, "intercept_enabled", enabled)
        else:
            self.intercept_enabled = enabled

    def set_enforce_scope(self, enabled: bool) -> None:
        """Thread-safe setting of enforce_scope flag from any thread.

        Same rationale as set_intercept — the proxy loop reads this flag
        in _handle_http/_handle_connect, so writes from the TUI thread must
        go through call_soon_threadsafe to avoid a torn read.
        """
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(setattr, self, "enforce_scope", enabled)
        else:
            self.enforce_scope = enabled

    def _find_request(self, req_id: str) -> InterceptedRequest | None:
        with self._requests_lock:
            for r in reversed(self.requests):
                if r.id == req_id:
                    return r
        return None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming client connection."""
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
        """Read the first request and decide: HTTP or HTTPS CONNECT."""
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
        """Handle CONNECT method: establish HTTPS tunnel."""
        first_line = raw_connect.split("\n")[0].strip()
        # CONNECT example.com:443 HTTP/1.1
        parts = first_line.split()
        if len(parts) < 2:
            return

        host_port = parts[1]
        domain = host_port.split(":")[0]

        # Respond 200 Connection Established
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()

        # If host is out of scope — just tunnel without interception
        # (only enforced when the user turned on "Skip out-of-scope")
        if self.enforce_scope and not self.is_in_scope(domain):
            await self._tunnel_raw(domain, host_port, reader, writer)
            return

        # Generate SSL context for the domain (with disk-cache via cert_dir)
        try:
            ssl_ctx = create_ssl_context_for_domain(
                domain, self._ca_cert_path, self._ca_key_path,
                cert_dir=self.cert_dir,
            )
        except Exception as exc:
            logger.warning("SSL context error for %s: %s", domain, exc)
            return

        # Upgrade TLS via start_tls with a new StreamReaderProtocol.
        # connection_made must be called BEFORE start_tls so the protocol
        # knows about the transport and the handshake proceeds correctly.
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

        # Read HTTPS requests
        try:
            while True:
                raw_req = await asyncio.wait_for(
                    self._read_http_message(tls_reader),
                    timeout=_READ_TIMEOUT,
                )
                if not raw_req.strip():
                    break

                # Insert https scheme into the request
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
        """Transparent TCP tunnel for out-of-scope hosts."""
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
                pass  # normal TCP tunnel termination
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
        """Handle an HTTP request: scope, match/replace, interception, sending."""
        try:
            req = parse_http_request(raw_request)
        except ValueError as exc:
            logger.debug("Parse error: %s", exc)
            return None

        host = req.host.split(":")[0]
        logger.debug("PROXY: _handle_http: %s %s (https=%s, intercept=%s, in_scope=%s)",
                    req.method, req.url, is_https, self.intercept_enabled, self.is_in_scope(host))

        # Check scope (for HTTP; HTTPS already checked in _handle_connect)
        # (only enforced when the user turned on "Skip out-of-scope")
        if self.enforce_scope and not is_https and not self.is_in_scope(host):
            logger.debug("PROXY: _handle_http: host %s out of scope, forwarding direct", host)
            return await self._forward_direct(req, writer)

        # Apply match/replace to request (via engine)
        raw_request = self._request_to_raw(req)
        modified_raw = self._match_replace_engine.apply_to_request(raw_request)
        if modified_raw != raw_request:
            try:
                req = parse_http_request(modified_raw)
            except ValueError:
                pass

        # Detect WebSocket connection (by Upgrade: websocket header)
        is_websocket = req.headers.get("Upgrade", "").lower() == "websocket"

        # Create InterceptedRequest
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

        # Notify subscribers via EventBus (main channel)
        try:
            from urllib.parse import urlparse as _urlparse

            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ProxyRequestCaptured
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

        # Interactive interception
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

            # User may have edited the request
            if ireq._modified_raw:
                try:
                    req = parse_http_request(ireq._modified_raw)
                    ireq.method = req.method
                    ireq.url = req.url
                    ireq.headers = dict(req.headers)
                    ireq.body = req.body
                except ValueError:
                    pass

        # WebSocket upgrade — separate path (requires raw TCP tunnel)
        if is_websocket:
            await self._handle_websocket(req, ireq, reader, writer)
            return None

        # Send request to target server
        response = await self._send_request(req)

        if response is None:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\nProxy error")
            await writer.drain()
            ireq.state = "forwarded"
            ireq.response = None
            # Was a silent early-return — no ProxyRequestCompleted was ever
            # emitted for network failures (DNS error, connection refused,
            # timeout, unreachable host, etc). That meant:
            #   1. on_proxy_request_done() in app.py never fired → the row
            #      already in HTTP History (from the earlier
            #      ProxyRequestCaptured/add_request_row on capture) never got
            #      its status/response, so it looked "stuck"/incomplete.
            #   2. SendToTarget never posted → TargetScreen.add_request_from_proxy
            #      was never called for these requests — SiteMap silently
            #      missed every host that had ANY failed request (very common
            #      with ad/analytics/CDN domains that time out or get
            #      DNS-blocked — exactly the "many requests fly past, Target
            #      doesn't fill up" symptom).
            # Emit here too so failed requests still show up (with no status)
            # instead of vanishing from both History and the SiteMap.
            try:
                from pentool.core.event_bus import get_event_bus
                from pentool.core.events import ProxyRequestCompleted
                get_event_bus().emit(ProxyRequestCompleted(
                    source="proxy",
                    request_id=ireq.id,
                    status_code=0,
                    request=ireq,
                ))
            except Exception as exc:
                logger.debug("EventBus emit ProxyRequestCompleted (failed request) error: %s", exc)
            return None

        # Apply match/replace to response (via engine)
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

        # Notify subscribers via EventBus (main channel)
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

        # Send response to client (raw bytes without re-encoding)
        writer.write(self._response_to_bytes(response))
        await writer.drain()

        return response

    # ── WebSocket support (delegated to WebSocketHandler) ──────────────────

    @staticmethod
    def _parse_ws_frame(data: bytes) -> tuple[int, bool, bytes, int] | None:
        """Backward compatibility — delegates to WebSocketHandler.parse_frame."""
        return WebSocketHandler.parse_frame(data)

    @staticmethod
    def _build_ws_frame(opcode: int, payload: bytes, mask: bool = False) -> bytes:
        """Backward compatibility — delegates to WebSocketHandler.build_frame."""
        return WebSocketHandler.build_frame(opcode, payload, mask)

    async def _ws_tunnel(
        self,
        request_id: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        srv_reader: asyncio.StreamReader,
        srv_writer: asyncio.StreamWriter,
    ) -> None:
        """Backward compatibility — delegates to WebSocketHandler.tunnel."""
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
        """Backward compatibility — delegates to WebSocketHandler.connect_and_handle."""
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
        """Forward request without interception (host out of scope)."""
        response = await self._send_request(req)
        if response:
            writer.write(self._response_to_bytes(response))
            await writer.drain()
        return response

    async def _send_request(self, req: ParsedRequest) -> ParsedResponse | None:
        try:
            # Use singleton client for connection pooling
            if self._http_client is None:
                from pentool.core.config import get_config
                cfg = get_config()
                self._http_client = HTTPClient(verify_ssl=cfg.verify_ssl, timeout=cfg.request_timeout)
            return await self._http_client.send(req)
        except Exception as exc:
            logger.warning("Request failed %s %s: %s", req.method, req.url, exc)
            return None

    async def _read_http_message(self, reader: asyncio.StreamReader) -> str:
        """Read an HTTP message (headers + body by Content-Length)."""
        # Read headers line by line until empty line
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

        # Determine Content-Length for body reading
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
        with self._requests_lock:
            self.requests.append(req)
            if len(self.requests) > self._requests_max:
                self.requests = self.requests[-self._requests_max:]

    def get_requests(
        self,
        limit: int = 100,
        method: str | None = None,
        host: str | None = None,
    ) -> list[InterceptedRequest]:
        with self._requests_lock:
            result = list(reversed(self.requests))
        if method:
            result = [r for r in result if r.method.upper() == method.upper()]
        if host:
            result = [r for r in result if host.lower() in r.url.lower()]
        return result[:limit]

    def clear_requests(self) -> None:
        with self._requests_lock:
            self.requests.clear()

    def replace_requests(self, requests: list[InterceptedRequest]) -> None:
        """Atomically replace the in-memory request history.

        Used by project import/export code that used to mutate
        `self.requests` directly (bypassing the lock).
        """
        with self._requests_lock:
            self.requests = list(requests)

    @staticmethod
    def _request_to_raw(req: "ParsedRequest") -> str:
        """Serialize ParsedRequest to raw HTTP string (for match-replace)."""
        lines = [f"{req.method} {req.url} HTTP/1.1"]
        for k, v in req.headers.items():
            lines.append(f"{k}: {v}")
        raw = "\r\n".join(lines) + "\r\n\r\n"
        if req.body:
            raw += req.body
        return raw

    @staticmethod
    def _response_to_raw(resp: ParsedResponse) -> str:
        """Serialize ParsedResponse to raw HTTP string (for TUI/match-replace)."""
        lines = [f"{resp.http_version} {resp.status} {resp.reason}"]
        for k, v in resp.headers.items():
            lines.append(f"{k}: {v}")
        raw = "\r\n".join(lines) + "\r\n\r\n"
        if resp.body:
            raw += resp.body
        return raw

    @staticmethod
    def _response_to_bytes(resp: ParsedResponse) -> bytes:
        """Serialize ParsedResponse to bytes for sending to the browser.

        aiohttp already decoded gzip/deflate and removed chunked — need to
        clean up the corresponding headers and set the correct Content-Length.
        """
        # Body — raw bytes (already decoded by aiohttp)
        if resp._raw_body is not None:
            body_bytes = resp._raw_body
        elif resp.body:
            body_bytes = resp.body.encode("utf-8", errors="replace")
        else:
            body_bytes = b""

        # Headers: remove those that became invalid after aiohttp decoding
        skip = {"transfer-encoding", "content-encoding", "content-length"}
        lines = [f"{resp.http_version} {resp.status} {resp.reason}"]
        for k, v in resp.headers.items():
            if k.lower() in skip:
                continue
            lines.append(f"{k}: {v}")
        # Set actual Content-Length
        lines.append(f"Content-Length: {len(body_bytes)}")

        header_bytes = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8", errors="replace")
        return header_bytes + body_bytes

    def get_status(self) -> dict:
        with self._requests_lock:
            requests_count = len(self.requests)
            waiting_count = sum(1 for r in self.requests if r.state == "waiting")
        return {
            "running": self.is_running,
            "host": self.host,
            "port": self.port,
            "intercept_enabled": self.intercept_enabled,
            "scope": self.scope,
            "requests_count": requests_count,
            "rules_count": len(self.match_replace_rules),
            "waiting_count": waiting_count,
        }
