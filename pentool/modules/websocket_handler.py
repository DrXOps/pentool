"""WebSocketHandler — WebSocket frame tunneling and parsing."""

from __future__ import annotations

import asyncio
import os
import ssl

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class WebSocketHandler:
    """WebSocket connection handler for the proxy.

    Responsible for:
    - Parsing/building WebSocket frames (RFC 6455)
    - Establishing a WS connection to the target server
    - Bidirectional tunnel with frame interception and logging
    """

    @staticmethod
    def parse_frame(data: bytes) -> tuple[int, bool, bytes, int] | None:
        """Parse one WebSocket frame (RFC 6455).

        Returns:
            (opcode, is_final, payload, total_bytes_consumed) or None if not enough data.
        """
        if len(data) < 2:
            return None
        b0, b1 = data[0], data[1]
        is_final = bool(b0 & 0x80)
        opcode   = b0 & 0x0F
        masked   = bool(b1 & 0x80)
        pay_len  = b1 & 0x7F

        offset = 2
        if pay_len == 126:
            if len(data) < offset + 2:
                return None
            pay_len = int.from_bytes(data[offset:offset + 2], "big")
            offset += 2
        elif pay_len == 127:
            if len(data) < offset + 8:
                return None
            pay_len = int.from_bytes(data[offset:offset + 8], "big")
            offset += 8

        mask_key = b""
        if masked:
            if len(data) < offset + 4:
                return None
            mask_key = data[offset:offset + 4]
            offset += 4

        if len(data) < offset + pay_len:
            return None

        raw_payload = data[offset:offset + pay_len]
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(raw_payload)) if masked else raw_payload

        return opcode, is_final, payload, offset + pay_len

    @staticmethod
    def build_frame(opcode: int, payload: bytes, mask: bool = False) -> bytes:
        """Build a WebSocket frame (RFC 6455).

        Args:
            opcode: Frame type (0x1=text, 0x2=binary, ...)
            payload: Frame body (already unmasked)
            mask: True — add masking (client->server)
        """
        b0 = 0x80 | (opcode & 0x0F)
        pay_len = len(payload)

        if pay_len < 126:
            b1 = pay_len
            length_bytes = b""
        elif pay_len < 65536:
            b1 = 126
            length_bytes = pay_len.to_bytes(2, "big")
        else:
            b1 = 127
            length_bytes = pay_len.to_bytes(8, "big")

        if mask:
            b1 |= 0x80
            mask_key = os.urandom(4)
            masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            return bytes([b0, b1]) + length_bytes + mask_key + masked_payload
        else:
            return bytes([b0, b1]) + length_bytes + payload

    async def tunnel(
        self,
        request_id: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        srv_reader: asyncio.StreamReader,
        srv_writer: asyncio.StreamWriter,
    ) -> None:
        """WebSocket tunnel with frame parsing and logging.

        Proxies frames in both directions, emitting WebSocketFrameEvent
        for each TEXT/BINARY/CLOSE frame.
        """
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import WebSocketFrameEvent
            bus = get_event_bus()
        except Exception:
            bus = None

        _OPCODES_LOG = {0x1, 0x2, 0x8}  # text, binary, close

        async def _relay(
            src: asyncio.StreamReader,
            dst: asyncio.StreamWriter,
            direction: str,
        ) -> None:
            buf = b""
            try:
                while True:
                    chunk = await src.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        parsed = self.parse_frame(buf)
                        if parsed is None:
                            break
                        opcode, _fin, payload, consumed = parsed
                        buf = buf[consumed:]

                        if bus and opcode in _OPCODES_LOG:
                            try:
                                payload_text = ""
                                if opcode == 0x1:
                                    payload_text = payload.decode("utf-8", errors="replace")
                                bus.emit(WebSocketFrameEvent(
                                    source="proxy",
                                    request_id=request_id,
                                    direction=direction,
                                    opcode=opcode,
                                    payload=payload,
                                    payload_text=payload_text,
                                ))
                            except Exception as exc:
                                logger.debug("WS emit error: %s", exc)

                    dst.write(chunk)
                    await dst.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
                pass
            except Exception as exc:
                logger.debug("_ws_tunnel relay error (%s): %s", direction, exc)
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        await asyncio.gather(
            _relay(client_reader, srv_writer, "client->server"),
            _relay(srv_reader, client_writer, "server->client"),
            return_exceptions=True,
        )

    async def connect_and_handle(
        self,
        req: object,
        ireq: object,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        from urllib.parse import urlparse
        from pentool.utils.parser import build_http_request, parse_http_response

        parsed = urlparse(req.url)
        host = parsed.hostname or req.host.split(":")[0]
        default_port = 443 if (parsed.scheme in ("wss", "https") or ireq.is_https) else 80
        port = parsed.port or default_port
        use_ssl = parsed.scheme in ("wss", "https") or ireq.is_https

        try:
            if use_ssl:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                srv_reader, srv_writer = await asyncio.open_connection(host, port, ssl=ssl_ctx)
            else:
                srv_reader, srv_writer = await asyncio.open_connection(host, port)
        except Exception as exc:
            logger.debug("WS connect failed %s:%s: %s", host, port, exc)
            client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_writer.drain()
            return

        raw_req = build_http_request(req)
        srv_writer.write(raw_req.encode("utf-8", errors="replace"))
        await srv_writer.drain()

        resp_lines: list[bytes] = []
        while True:
            line = await srv_reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                resp_lines.append(line)
                break
            resp_lines.append(line)

        resp_bytes = b"".join(resp_lines)
        first_line = resp_bytes.split(b"\n")[0]
        status = int(first_line.split()[1]) if len(first_line.split()) >= 2 else 0
        if status != 101:
            logger.debug("WS upgrade failed: %s", first_line)
            client_writer.write(resp_bytes)
            await client_writer.drain()
            return

        try:
            parsed_resp = parse_http_response(resp_bytes.decode("utf-8", errors="replace") + "\r\n")
            ireq.response = parsed_resp
        except Exception:
            pass
        ireq.state = "forwarded"

        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ProxyRequestCompleted
            get_event_bus().emit(ProxyRequestCompleted(
                source="proxy",
                request_id=ireq.id,
                status_code=101,
                request=ireq,
            ))
        except Exception as exc:
            logger.debug("EventBus emit ProxyRequestCompleted (WS) error: %s", exc)

        client_writer.write(resp_bytes)
        await client_writer.drain()

        await self.tunnel(
            request_id=ireq.id,
            client_reader=client_reader,
            client_writer=client_writer,
            srv_reader=srv_reader,
            srv_writer=srv_writer,
        )
