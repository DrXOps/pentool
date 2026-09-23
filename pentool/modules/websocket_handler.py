"""WebSocketHandler — WebSocket frame tunneling and parsing."""

from __future__ import annotations

import asyncio
import os
import ssl

from pentool.core.logging import get_logger

logger = get_logger(__name__)

# Cached SSL context for outgoing WebSocket connections (reused across all
# WS upgrades so we don't load system CA certs from disk on every upgrade).
# ssl.create_default_context() → load_default_certs() is I/O-heavy and was
# blocking the proxy event loop under burst traffic.
_SSL_CTX: ssl.SSLContext | None = None

# How long a writer may take to actually close (fd teardown) before we give up
# and let the fd be reclaimed at loop shutdown. Bounded so a wedged socket can't
# hold a cancellation hostage — same rationale as Proxy._WRITER_CLOSE_GRACE.
_WRITER_CLOSE_GRACE = 0.5


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
            except asyncio.CancelledError:
                # CancelledError is BaseException — it would bypass the generic
                # handler below. We let it propagate; the shared finally after
                # the gather closes both writers (see below), so a cancelled
                # relay can't leave the far side open.
                raise
            except Exception as exc:
                logger.debug("_ws_tunnel relay error (%s): %s", direction, exc)
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        try:
            await asyncio.gather(
                _relay(client_reader, srv_writer, "client->server"),
                _relay(srv_reader, client_writer, "server->client"),
                return_exceptions=False,
            )
        except asyncio.CancelledError:
            # Task cancelled (proxy stop / app teardown). We cannot `await` in
            # a finally here — at this point GeneratorExit is in flight and an
            # await on a half-closed coroutine raises "RuntimeError: coroutine
            # ignored GeneratorExit" (the very error that silently killed run()).
            # Close both writers synchronously (no await), then re-raise.
            for w in (client_writer, srv_writer):
                try:
                    w.close()
                except Exception:
                    pass
            raise
        finally:
            # Normal (non-cancel) teardown: one relay ended the tunnel. Close
            # BOTH writers even when only one side broke — leaving srv_writer
            # (upstream) open left _handle_client's wait_closed() pending
            # forever. Bounded wait so we never block shutdown.
            for w in (client_writer, srv_writer):
                try:
                    w.close()
                    await asyncio.wait_for(w.wait_closed(), timeout=_WRITER_CLOSE_GRACE)
                except Exception:
                    pass

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

        srv_reader: asyncio.StreamReader | None = None
        srv_writer: asyncio.StreamWriter | None = None
        try:
            if use_ssl:
                # Cached SSL context — ssl.create_default_context() calls
                # load_default_certs() which reads all system CA files. Under
                # burst traffic (many tabs refreshing) every WebSocket upgrade
                # triggered a fresh cert load, blocking the proxy event loop
                # and causing the main loop to time out → clean run() exit.
                # NOTE: _SSL_CTX is module-level; the assignment below made it
                # a local without `global`, so the `if _SSL_CTX is None` read
                # raised UnboundLocalError ("_SSL_CTX ... local variable") on
                # every HTTPS WebSocket upgrade.
                global _SSL_CTX
                if _SSL_CTX is None:
                    _SSL_CTX = ssl.create_default_context()
                    _SSL_CTX.check_hostname = False
                    _SSL_CTX.verify_mode = ssl.CERT_NONE
                srv_reader, srv_writer = await asyncio.open_connection(
                    host, port, ssl=_SSL_CTX,
                )
            else:
                srv_reader, srv_writer = await asyncio.open_connection(host, port)

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
                # Close the (unused) upstream connection before returning.
                srv_writer.close()
                try:
                    await asyncio.wait_for(srv_writer.wait_closed(), timeout=_WRITER_CLOSE_GRACE)
                except Exception:
                    pass
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

            # tunnel() owns both writers from here (it closes them in its
            # finally, including on cancellation).
            await self.tunnel(
                request_id=ireq.id,
                client_reader=client_reader,
                client_writer=client_writer,
                srv_reader=srv_reader,
                srv_writer=srv_writer,
            )
        except asyncio.CancelledError:
            # Task cancelled (e.g. proxy.stop() or project switch) while we were
            # still connecting / before tunnel() took ownership. Close both
            # writers so no pending read/write future survives to loop teardown —
            # a pending asyncio.gather/StreamWriter on a half-open socket is what
            # produced "RuntimeError: coroutine ignored GeneratorExit".
            for w in (client_writer, srv_writer):
                if w is None:
                    continue
                try:
                    w.close()
                    await asyncio.wait_for(w.wait_closed(), timeout=_WRITER_CLOSE_GRACE)
                except Exception:
                    pass
            raise
        except Exception:
            # On a non-101/upgrade failure we already close srv_writer above;
            # any other failure should still release the upstream socket.
            if srv_writer is not None:
                try:
                    srv_writer.close()
                except Exception:
                    pass
            raise
