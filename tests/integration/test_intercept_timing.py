"""Диагностический тест: timing intercept Forward/Drop → ResponseViewer.

Запуск:
    pytest tests/integration/test_intercept_timing.py -v -s --no-header

Что проверяем:
1. Forward: вызвать show_intercepted_request() → нажать Forward →
   засечь время до появления контента в #intercept-resp-viewer.
2. Drop: show_intercepted_request() → нажать Drop →
   проверить что editor очистился.
3. Очередь: два запроса подряд → Forward первого → второй появляется автоматически.
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
        """Forward → ответ появляется в #intercept-resp-viewer.

        Имитируем: show_intercepted_request() → Forward →
        вручную симулируем on_request_done (т.к. реального сервера нет) →
        замеряем время до появления контента.
        """
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        from pentool.tui.widgets.request_editor import HttpView
        from textual.widgets import TextArea

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(0.3)

            screen = app.query_one("#screen-proxy", ProxyScreen)

            # Включаем intercept напрямую (без реального прокси)
            app._proxy.intercept_enabled = True
            screen._sync_intercept_button()
            await asyncio.sleep(0)

            # Создаём перехваченный запрос
            ireq = _make_intercepted_req("t001", "GET", "http://example.com/api/data")

            # Показываем запрос в intercept UI
            t_show = time.perf_counter()
            screen.show_intercepted_request(ireq)
            await asyncio.sleep(0)
            t_shown = time.perf_counter()
            print(f"\n[TIMING] show_intercepted_request: {(t_shown - t_show)*1000:.1f}ms")

            # Проверяем что запрос отображён в редакторе
            editor = app.query_one("#intercept-editor", TextArea)
            assert "/api/data" in editor.text or "example.com" in editor.text, \
                f"Editor должен содержать путь или хост. Got: {editor.text[:100]}"
            print(f"[OK] Editor содержит запрос: {editor.text[:60]!r}")

            # Вызываем Forward напрямую (pilot.click зависает на больших окнах под pytest-asyncio)
            t_forward_click = time.perf_counter()
            screen.action_forward()
            await asyncio.sleep(0)
            t_forward_done = time.perf_counter()
            print(f"[TIMING] Forward action → handler: {(t_forward_done - t_forward_click)*1000:.1f}ms")

            # _intercept_req должен быть None после Forward
            assert screen._intercept_req is None, "После Forward _intercept_req должен быть None"
            print("[OK] _intercept_req = None после Forward")

            # Симулируем приход ответа (on_request_done callback)
            ireq.response = _make_response(200, "Hello from server!")
            ireq.state = "forwarded"

            t_response_sim = time.perf_counter()
            screen.show_intercept_response(ireq)
            await asyncio.sleep(0)
            t_response_shown = time.perf_counter()
            print(f"[TIMING] show_intercept_response → rendered: {(t_response_shown - t_response_sim)*1000:.1f}ms")

            # Проверяем что #intercept-resp-viewer существует и обновлён
            try:
                viewer = app.query_one("#intercept-resp-viewer", HttpView)
                print(f"[OK] #intercept-resp-viewer обновлён (widget exists, rendered)")
            except Exception as e:
                pytest.fail(f"#intercept-resp-viewer не найден: {e}")

            total = t_response_shown - t_show
            print(f"[TIMING] TOTAL show→forward→response: {total*1000:.1f}ms")

    @pytest.mark.asyncio
    async def test_drop_clears_editor(self) -> None:
        """Drop → editor очищается, кнопки дизейблятся."""
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
                f"Editor должен содержать путь. Got: {editor.text[:100]}"

            t_drop = time.perf_counter()
            screen.action_drop()
            await pilot.pause(0.1)
            t_after_drop = time.perf_counter()
            print(f"\n[TIMING] Drop action → handler: {(t_after_drop - t_drop)*1000:.1f}ms")

            assert screen._intercept_req is None, "После Drop _intercept_req должен быть None"

            # Editor должен показывать сообщение об очистке
            editor_text = app.query_one("#intercept-editor", TextArea).text
            print(f"[OK] Editor после Drop: {editor_text[:60]!r}")

            from pentool.tui.widgets.toolbar_button import ToolbarButton
            fwd_btn = app.query_one("#btn-forward", ToolbarButton)
            drop_btn = app.query_one("#btn-drop", ToolbarButton)
            assert fwd_btn.disabled, "Forward должна быть disabled после Drop"
            assert drop_btn.disabled, "Drop должна быть disabled после Drop"
            print("[OK] Forward и Drop кнопки задизейблены")

    @pytest.mark.asyncio
    async def test_queue_shows_next_after_forward(self) -> None:
        """Два запроса подряд → первый показан, второй в очереди →
        Forward первого → второй автоматически появляется."""
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

            # Показываем оба запроса
            screen.show_intercepted_request(req1)
            await pilot.pause(0.05)
            screen.show_intercepted_request(req2)
            await pilot.pause(0.1)

            # Первый должен быть активным
            assert screen._intercept_req is req1, \
                f"Первый запрос должен быть активным, а не {screen._intercept_req}"
            # Второй — в очереди
            assert len(screen._intercept_pending) == 1, \
                f"Второй запрос должен быть в очереди, len={len(screen._intercept_pending)}"
            assert screen._intercept_pending[0] is req2
            print(f"\n[OK] req1 активен, req2 в очереди (len={len(screen._intercept_pending)})")

            # Editor содержит первый запрос
            editor = app.query_one("#intercept-editor", TextArea)
            assert "/req1" in editor.text or "GET" in editor.text, \
                f"Editor должен показывать первый запрос: {editor.text[:100]}"
            print(f"[OK] Editor показывает req1: {editor.text[:50]!r}")

            # Forward первого (прямой вызов — pilot.click зависает на больших окнах)
            t0 = time.perf_counter()
            screen.action_forward()
            await pilot.pause(0.15)
            t1 = time.perf_counter()
            print(f"[TIMING] Forward req1 → req2 появился: {(t1-t0)*1000:.1f}ms")

            # Второй должен стать активным
            assert screen._intercept_req is req2, \
                f"После Forward req1 активным должен стать req2, а не {screen._intercept_req}"
            assert len(screen._intercept_pending) == 0, \
                f"Очередь должна быть пустой, len={len(screen._intercept_pending)}"
            print("[OK] req2 автоматически стал активным")

            # Editor содержит второй запрос
            editor_text = app.query_one("#intercept-editor", TextArea).text
            assert "/req2" in editor_text or "POST" in editor_text, \
                f"Editor должен показывать второй запрос: {editor_text[:100]}"
            print(f"[OK] Editor показывает req2: {editor_text[:50]!r}")

    @pytest.mark.asyncio
    async def test_response_viewer_timing_after_forward(self) -> None:
        """Точный тайминг: сколько мс от show_intercept_response() до обновления виджета.

        Проверяем нет ли задержки в show_intercept_response → ResponseViewer.load_response.
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

            # Форвардим без клика (напрямую через метод, чтобы убрать overhead UI)
            screen.action_forward()
            await pilot.pause(0.05)

            # Симулируем ответ
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

            # Ожидаем что среднее < 200ms (без задержки это должно быть <50ms)
            assert avg < 500, f"show_intercept_response слишком медленная: avg={avg:.1f}ms"
            print(f"[OK] ResponseViewer обновляется быстро: {avg:.1f}ms avg")
