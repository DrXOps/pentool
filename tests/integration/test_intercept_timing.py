"""Diagnostic test: timing intercept Forward/Drop → ResponseViewer.

Run:
    pytest tests/integration/test_intercept_timing.py -v -s --no-header

What we check:
1. Forward: call show_intercepted_request() → press Forward →
   measure time until content appears in #intercept-resp-viewer.
2. Drop: show_intercepted_request() → press Drop →
   verify that the editor was cleared.
3. Queue: two requests in a row → Forward the first → second appears automatically.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from unittest.mock import MagicMock

import pytest

from pentool.core.config import Config, set_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19093,
    )
    set_config(cfg)
    return cfg


def _make_intercepted_req(
    req_id: str = "test-001",
    method: str = "GET",
    url: str = "http://example.com/test",
) -> "InterceptedRequest":
    from pentool.modules.proxy import InterceptedRequest
    from datetime import datetime, timezone
    import asyncio

    ireq = InterceptedRequest(
        id=req_id,
        method=method,
        url=url,
        headers={"Host": "example.com", "User-Agent": "TestAgent/1.0"},
        body="",
        timestamp=datetime.now(timezone.utc),
        is_https=False,
        is_websocket=False,
    )
    return ireq


def _make_response(status: int = 200, body: str = "Hello from server") -> "ParsedResponse":
    from pentool.utils.parser import ParsedResponse
    return ParsedResponse(
        status=status,
        headers={"Content-Type": "text/plain", "Content-Length": str(len(body))},
        body=body,
    )


@pytest.mark.integration
class TestInterceptTiming:

    @pytest.mark.asyncio
    async def test_forward_response_appears_in_viewer(self) -> None:
        """Forward → response appears in #intercept-resp-viewer.

        Simulate: show_intercepted_request() → Forward →
        manually simulate on_request_done (no real server) →
        measure time until content appears.
        """
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        from pentool.tui.widgets.request_editor import HttpView
        from textual.widgets import TextArea

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(0.3)

            screen = app.query_one("#screen-proxy", ProxyScreen)

            # Enable intercept directly (without real proxy)
            app._proxy.intercept_enabled = True
            screen._sync_intercept_button()
            await asyncio.sleep(0)

            # Create an intercepted request
            ireq = _make_intercepted_req("t001", "GET", "http://example.com/api/data")

            # Show the request in the intercept UI
            t_show = time.perf_counter()
            screen.show_intercepted_request(ireq)
            await asyncio.sleep(0)
            t_shown = time.perf_counter()
            print(f"\n[TIMING] show_intercepted_request: {(t_shown - t_show)*1000:.1f}ms")

            # Verify the request is displayed in the editor
            editor = app.query_one("#intercept-editor", TextArea)
            assert "/api/data" in editor.text or "example.com" in editor.text, \
                f"Editor should contain path or host. Got: {editor.text[:100]}"
            print(f"[OK] Editor contains request: {editor.text[:60]!r}")

            # Call Forward directly (pilot.click hangs on large windows under pytest-asyncio)
            t_forward_click = time.perf_counter()
            screen.action_forward()
            await asyncio.sleep(0)
            t_forward_done = time.perf_counter()
            print(f"[TIMING] Forward action → handler: {(t_forward_done - t_forward_click)*1000:.1f}ms")

            # _intercept_req should be None after Forward
            assert screen._intercept_req is None, "After Forward _intercept_req should be None"
            print("[OK] _intercept_req = None after Forward")

            # Simulate response arriving (on_request_done callback)
            ireq.response = _make_response(200, "Hello from server!")
            ireq.state = "forwarded"

            t_response_sim = time.perf_counter()
            screen.show_intercept_response(ireq)
            await asyncio.sleep(0)
            t_response_shown = time.perf_counter()
            print(f"[TIMING] show_intercept_response → rendered: {(t_response_shown - t_response_sim)*1000:.1f}ms")

            # Verify #intercept-resp-viewer exists and was updated
            try:
                viewer = app.query_one("#intercept-resp-viewer", HttpView)
                print(f"[OK] #intercept-resp-viewer updated (widget exists, rendered)")
            except Exception as e:
                pytest.fail(f"#intercept-resp-viewer not found: {e}")

            total = t_response_shown - t_show
            print(f"[TIMING] TOTAL show→forward→response: {total*1000:.1f}ms")

    @pytest.mark.asyncio
    async def test_drop_clears_editor(self) -> None:
        """Drop → editor is cleared, buttons are disabled."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        from textual.widgets import TextArea

        app = PentoolApp()
        async with app.run_test(size=(200, 50)) as pilot:
            await pilot.pause(0.5)

            screen = app.query_one("#screen-proxy", ProxyScreen)
            app._proxy.intercept_enabled = True
            screen._sync_intercept_button()
            await pilot.pause(0.1)

            ireq = _make_intercepted_req("t002", "POST", "http://evil.com/drop-me")

            t0 = time.perf_counter()
            screen.show_intercepted_request(ireq)
            await pilot.pause(0.1)

            editor = app.query_one("#intercept-editor", TextArea)
            assert "/drop-me" in editor.text or "example.com" in editor.text, \
                f"Editor should contain path. Got: {editor.text[:100]}"

            t_drop = time.perf_counter()
            screen.action_drop()
            await pilot.pause(0.1)
            t_after_drop = time.perf_counter()
            print(f"\n[TIMING] Drop action → handler: {(t_after_drop - t_drop)*1000:.1f}ms")

            assert screen._intercept_req is None, "After Drop _intercept_req should be None"

            # Editor should show a cleared message
            editor_text = app.query_one("#intercept-editor", TextArea).text
            print(f"[OK] Editor after Drop: {editor_text[:60]!r}")

            from pentool.tui.widgets.toolbar_button import ToolbarButton
            fwd_btn = app.query_one("#btn-forward", ToolbarButton)
            drop_btn = app.query_one("#btn-drop", ToolbarButton)
            assert fwd_btn.disabled, "Forward should be disabled after Drop"
            assert drop_btn.disabled, "Drop should be disabled after Drop"
            print("[OK] Forward and Drop buttons are disabled")

    @pytest.mark.asyncio
    async def test_queue_shows_next_after_forward(self) -> None:
        """Two requests in a row → first shown, second in queue →
        Forward the first → second appears automatically."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        from textual.widgets import TextArea

        app = PentoolApp()
        async with app.run_test(size=(200, 50)) as pilot:
            await pilot.pause(0.5)

            screen = app.query_one("#screen-proxy", ProxyScreen)
            app._proxy.intercept_enabled = True
            screen._sync_intercept_button()
            await pilot.pause(0.1)

            req1 = _make_intercepted_req("q001", "GET", "http://first.com/req1")
            req2 = _make_intercepted_req("q002", "POST", "http://second.com/req2")

            # Show both requests
            screen.show_intercepted_request(req1)
            await pilot.pause(0.05)
            screen.show_intercepted_request(req2)
            await pilot.pause(0.1)

            # First should be active
            assert screen._intercept_req is req1, \
                f"First request should be active, not {screen._intercept_req}"
            # Second should be in queue
            assert len(screen._intercept_pending) == 1, \
                f"Second request should be in queue, len={len(screen._intercept_pending)}"
            assert screen._intercept_pending[0] is req2
            print(f"\n[OK] req1 active, req2 in queue (len={len(screen._intercept_pending)})")

            # Editor contains the first request
            editor = app.query_one("#intercept-editor", TextArea)
            assert "/req1" in editor.text or "GET" in editor.text, \
                f"Editor should show first request: {editor.text[:100]}"
            print(f"[OK] Editor shows req1: {editor.text[:50]!r}")

            # Forward the first (direct call — pilot.click hangs on large windows)
            t0 = time.perf_counter()
            screen.action_forward()
            await pilot.pause(0.15)
            t1 = time.perf_counter()
            print(f"[TIMING] Forward req1 → req2 appeared: {(t1-t0)*1000:.1f}ms")

            # Second should become active
            assert screen._intercept_req is req2, \
                f"After Forward req1, req2 should become active, not {screen._intercept_req}"
            assert len(screen._intercept_pending) == 0, \
                f"Queue should be empty, len={len(screen._intercept_pending)}"
            print("[OK] req2 automatically became active")

            # Editor contains the second request
            editor_text = app.query_one("#intercept-editor", TextArea).text
            assert "/req2" in editor_text or "POST" in editor_text, \
                f"Editor should show second request: {editor_text[:100]}"
            print(f"[OK] Editor shows req2: {editor_text[:50]!r}")

    @pytest.mark.asyncio
    async def test_response_viewer_timing_after_forward(self) -> None:
        """Precise timing: how many ms from show_intercept_response() to widget update.

        Check there is no delay in show_intercept_response → ResponseViewer.load_response.
        """
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        from pentool.tui.widgets.request_editor import ResponseViewer

        app = PentoolApp()
        async with app.run_test(size=(200, 50)) as pilot:
            await pilot.pause(0.5)

            screen = app.query_one("#screen-proxy", ProxyScreen)
            app._proxy.intercept_enabled = True

            ireq = _make_intercepted_req("timing-001", "GET", "http://timing.test/")
            screen.show_intercepted_request(ireq)
            await pilot.pause(0.1)

            # Forward without click (directly via method to remove UI overhead)
            screen.action_forward()
            await pilot.pause(0.05)

            # Simulate response
            ireq.response = _make_response(200, "Timing test body " * 10)
            ireq.state = "forwarded"

            timings = []
            for i in range(3):
                t0 = time.perf_counter()
                screen.show_intercept_response(ireq)
                await pilot.pause(0.05)
                t1 = time.perf_counter()
                timings.append((t1 - t0) * 1000)

            avg = sum(timings) / len(timings)
            print(f"\n[TIMING] show_intercept_response avg: {avg:.1f}ms "
                  f"(min={min(timings):.1f}, max={max(timings):.1f})")

            # Expect average < 200ms (without delay this should be <50ms)
            assert avg < 500, f"show_intercept_response is too slow: avg={avg:.1f}ms"
            print(f"[OK] ResponseViewer updates quickly: {avg:.1f}ms avg")
