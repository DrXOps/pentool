"""E2E: reproduce the "TUI just vanished" via real proxy traffic + mouse.

Exercises the cross-thread path: proxy's own event loop → EventBus →
call_from_thread → Textual main loop. Real plain HTTP + WebSocket
connections through the proxy port, no mock.

Steps: proxy on → mouse over history → parallel traffic bursts
(HTTP + WS) while clicking rows → sustained 60s → app must survive.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from pentool.tui.app import PentoolApp


@pytest.mark.e2e
class TestProxyRealTraffic:

    async def _start_upstream(self) -> tuple[asyncio.AbstractServer, int]:
        async def handle(reader, writer):
            try:
                data = await reader.read(65536)
                resp = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n<html>ok</html>"
                writer.write(resp)
                await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        srv = await asyncio.start_server(handle, "127.0.0.1", 0)
        return srv, srv.sockets[0].getsockname()[1]

    async def test_survive_60s(self) -> None:
        ups, up_port = await self._start_upstream()
        up_host = f"127.0.0.1:{up_port}"

        app = PentoolApp()
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.action_switch_module("proxy")
            await pilot.pause(0.3)

            from pentool.tui.screens.proxy.screen import ProxyScreen
            screen = app.query_one(ProxyScreen)
            proxy = screen._get_proxy()
            app._project_loaded = True
            screen.action_toggle_proxy()
            for _ in range(50):
                await pilot.pause(0.1)
                if proxy.is_running:
                    break
            assert proxy.is_running

            # Seed rows
            for i in range(100):
                screen._rows_cache.append({
                    "id": i + 1, "host": f"ex{i}.com", "method": "GET",
                    "url": f"https://ex{i}.com/a?b={i}",
                    "status_code": 200, "length": 100 + i,
                    "timestamp": time.time() - (100 - i), "is_websocket": False,
                })
            from pentool.tui.screens.proxy import screen as _ps
            from textual_fastdatatable import ArrowBackend
            tbl = app.query_one("#request-list")
            tbl.backend = ArrowBackend(_ps._rows_to_arrow(screen._rows_cache))
            tbl._ordered_columns = None
            tbl._clear_caches()
            tbl._require_update_dimensions = True
            tbl.refresh()
            await pilot.pause(0.3)

            # ── clicker ──
            async def click_loop():
                from textual_fastdatatable import DataTable as FastDT
                tick = 0
                while True:
                    total = max(len(screen._rows_cache), 1)
                    row_idx = total - 1 - (tick % min(total, 30))
                    try:
                        screen.on_data_table_row_highlighted(
                            FastDT.RowHighlighted(
                                data_table=app.query_one("#request-list"),
                                cursor_row=max(row_idx, 0),
                            )
                        )
                    except Exception:
                        break
                    tick += 1
                    await asyncio.sleep(0.04)

            # ── HTTP burst ──
            async def http_burst(n: int, host: str):
                async def one(i: int):
                    try:
                        r, w = await asyncio.open_connection("127.0.0.1", proxy.port)
                        req = f"GET /p{i} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
                        w.write(req)
                        await w.drain()
                        try:
                            await asyncio.wait_for(r.read(65536), 1.5)
                        except Exception:
                            pass
                        w.close()
                        try:
                            await w.wait_closed()
                        except Exception:
                            pass
                    except Exception:
                        pass
                await asyncio.gather(*(one(i) for i in range(n)))

            # ── WS upgrade ──
            async def ws_burst(n: int, host: str):
                async def one(i: int):
                    try:
                        r, w = await asyncio.open_connection("127.0.0.1", proxy.port)
                        key = "dGhlIHNhbXBsZSBub25jZQ=="
                        req = (
                            f"GET /ws{i} HTTP/1.1\r\n"
                            f"Host: {host}\r\n"
                            f"Upgrade: websocket\r\n"
                            f"Connection: Upgrade\r\n"
                            f"Sec-WebSocket-Key: {key}\r\n"
                            f"Sec-WebSocket-Version: 13\r\n\r\n"
                        ).encode()
                        w.write(req)
                        await w.drain()
                        try:
                            await asyncio.wait_for(r.read(4096), 1.5)
                        except Exception:
                            pass
                        w.close()
                        try:
                            await w.wait_closed()
                        except Exception:
                            pass
                    except Exception:
                        pass
                await asyncio.gather(*(one(i) for i in range(n)))

            # ── SUSTAINED LOAD ──
            clicker = asyncio.create_task(click_loop())
            rounds = 0
            start = time.monotonic()
            while time.monotonic() - start < 55:  # ~55s
                await http_burst(30, up_host)
                await ws_burst(15, up_host)
                rounds += 1
                await pilot.pause(0.01)
                if not app.is_running:
                    break
            clicker.cancel()
            elapsed = time.monotonic() - start

            if not app.is_running:
                raise AssertionError(
                    f"APP DIED after {elapsed:.0f}s ({rounds} rounds)"
                )
            assert app.is_running, f"App dead after {elapsed:.0f}s"
            assert proxy.is_running, "Proxy dead"

        ups.close()
        await ups.wait_closed()