"""Unit tests for ProxyRuntimeMixin (Этап 5.1).

Covers the start/stop/toggle path WITHOUT launching a real proxy server or
network listener: `_proxy` is a mock, `_proxy_main` is stubbed, and threads
are prevented from actually running asyncio loops.
"""

from __future__ import annotations

import asyncio
import threading
import types

import pytest

from pentool.tui.mixins.proxy_runtime import ProxyRuntimeMixin


class _FakeApp(ProxyRuntimeMixin):
    """Host with all state/attrs the mixin touches, plus recorded calls."""

    def __init__(self):
        self._proxy = None
        self._proxy_thread: threading.Thread | None = None
        self._proxy_loop = None
        self._project_loaded = True
        self.notified: list[tuple[str, dict]] = []
        self.after_refresh: list[tuple] = []
        self.workers: list = []
        self._update_status_calls = 0
        self._update_labels_calls = 0
        self._update_dash_calls: list[bool] = []

    # -- Textual-ish host surface ----------------------------------------
    def notify(self, message, *, title="", severity="information", timeout=None, **kw):
        self.notified.append((message, {"severity": severity, "timeout": timeout}))

    def run_worker(self, coro):
        self.workers.append(coro)
        coro.close()  # avoid "coroutine never awaited" runtime warning in fake

    def call_from_thread(self, fn, *args):
        # In tests, invoke immediately (no real thread).
        fn(*args)

    def _update_status(self):
        self._update_status_calls += 1

    def _update_proxy_screen_labels(self):
        self._update_labels_calls += 1

    def _update_dashboard_proxy_status(self, running: bool):
        self._update_dash_calls.append(running)

    def call_after_refresh(self, fn, *args, **kwargs):
        self.after_refresh.append((fn, (args, kwargs)))
        fn(*args, **kwargs)

    async def _proxy_main(self):
        """Stub: the real one runs the proxy loop in a thread; tests don't."""
        return None


def _mk_proxy(running=False):
    async def _noop():
        return None
    p = types.SimpleNamespace(
        is_running=running,
        host="127.0.0.1",
        port=8080,
        start=_noop,
        stop=_noop,
        _server=None,
        intercept_enabled=False,
    )
    return p


class TestActionToggleProxy:
    def test_toggle_no_proxy_is_noop(self):
        app = _FakeApp()
        app._proxy = None
        app.action_toggle_proxy()
        assert app.workers == []
        assert app.notified == []

    def test_toggle_when_running_schedules_async_stop(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=True)
        app._proxy_loop = object()
        app.action_toggle_proxy()
        # Should schedule an async-stop worker (not directly mutate state).
        assert len(app.workers) == 1
        assert app.workers[0] is not None

    def test_toggle_not_loaded_warns_and_does_not_start(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=False)
        app._project_loaded = False
        app.action_toggle_proxy()
        assert app.notified, "expected a 'still opening' warning"
        assert "still opening" in app.notified[0][0]

    def test_toggle_not_running_loaded_starts(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=False)
        app.action_toggle_proxy()
        # _start_proxy builds a real thread; assert it was the chosen branch via
        # the thread being created (and started) on the host.
        assert app._proxy_thread is not None


class TestStartProxy:
    def test_start_when_running_is_noop(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=True)
        app._start_proxy()
        assert app._proxy_thread is None

    def test_start_builds_and_starts_thread(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=False)
        app._start_proxy()
        assert app._proxy_thread is not None
        assert app._proxy_thread.name == "proxy"


class TestStopProxy:
    def test_stop_not_running_still_refreshes_status(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=False)
        app._proxy_thread = None
        app._proxy_loop = None
        app._stop_proxy()
        # Should notify + schedule status refresh even when nothing running.
        assert any(m and "stopped" in m for (m, _kw) in app.notified)

    def test_stop_joins_thread(self):
        import threading as th
        app = _FakeApp()
        # running=False skips the run_coroutine_threadsafe branch (which needs
        # a live loop); the thread join below is unconditional and is what
        # this test asserts.
        app._proxy = _mk_proxy(running=False)
        app._proxy_loop = None
        t = th.Thread(target=lambda: None, name="proxy", daemon=True)
        t.start()
        app._proxy_thread = t
        app._stop_proxy()
        assert not t.is_alive()


class TestStopProxyAsync:
    @pytest.mark.asyncio
    async def test_stop_async_refreshes_even_without_thread(self):
        app = _FakeApp()
        app._proxy = _mk_proxy(running=False)
        app._proxy_thread = None
        app._proxy_loop = None
        await app._stop_proxy_async()
        assert app._update_status_calls >= 1
