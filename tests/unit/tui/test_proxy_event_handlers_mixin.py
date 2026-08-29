"""Unit tests for ProxyEventHandlersMixin (Этап 5.1).

Covers the proxy request lifecycle handlers without a real Textual App or a
running proxy — uses a fake host (pattern from test_notifications_mixin) and
mock ProxyScreen objects.
"""

from __future__ import annotations

from datetime import datetime, timezone

import types

from pentool.api.proxy_api import InterceptedRequest as _IR
from pentool.tui.mixins.events_handlers import ProxyEventHandlersMixin


def _mk_req(rid="r1"):
    return _IR(
        id=rid,
        method="GET",
        url="http://example.com/",
        headers={},
        body="",
        timestamp=datetime.now(timezone.utc),
    )


class _FakeScreen:
    """Fake ProxyScreen exposing the methods the handlers touch."""

    def __init__(self):
        self.rows = []
        self.intercepted = []
        self.cleared = 0
        self.loaded = 0

    def add_request_row(self, req):
        self.rows.append(("add", req))

    def update_request_row(self, req):
        self.rows.append(("update", req))

    def show_intercepted_request(self, req):
        self.intercepted.append(req)

    def show_intercept_response(self, req):
        self.intercepted.append(("resp", req))

    def action_clear_list(self):
        self.cleared += 1

    def load_from_project(self):
        self.loaded += 1


class _FakeApp(ProxyEventHandlersMixin):
    def __init__(self):
        self._proxy = None
        self._pending_done_ids: set = set()
        self._screen = None
        self.posted = []
        self._proxy_calls = []
        self._screen_calls = []

    # -- host surface ------------------------------------------------
    def _get_proxy_screen(self):
        self._screen_calls.append(1)
        return self._screen

    def post_message(self, msg):
        self.posted.append(msg)

    def call_from_thread(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def query_one(self, selector, cls=None):
        if selector == "#screen-proxy":
            return self._screen
        raise Exception(f"unmounted {selector}")


class TestOnProxyRequestAdded:
    def test_not_running_is_noop(self):
        app = _FakeApp()
        app._proxy = types.SimpleNamespace(is_running=False)
        app._screen = _FakeScreen()
        app.on_proxy_request_added(types.SimpleNamespace(req=_mk_req()))
        assert app._screen.rows == []

    def test_running_adds_row(self):
        app = _FakeApp()
        app._proxy = types.SimpleNamespace(is_running=True, intercept_enabled=False)
        app._screen = _FakeScreen()
        req = _mk_req()
        app.on_proxy_request_added(types.SimpleNamespace(req=req))
        assert app._screen.rows == [("add", req)]

    def test_running_intercept_enabled_shows_intercept(self):
        app = _FakeApp()
        app._proxy = types.SimpleNamespace(is_running=True, intercept_enabled=True)
        app._screen = _FakeScreen()
        req = _mk_req()
        app.on_proxy_request_added(types.SimpleNamespace(req=req))
        assert app._screen.intercepted == [req]


class TestOnProxyRequestDone:
    def test_guard_skips_non_intercepted_request(self):
        app = _FakeApp()
        app._screen = _FakeScreen()
        app.on_proxy_request_done(types.SimpleNamespace(req=types.SimpleNamespace(id="x")))
        # Non-_IR req → no row update, no SendToTarget posted.
        assert app._screen.rows == []
        assert app.posted == []

    def test_valid_updates_row_and_posts_send_to_target(self):
        from pentool.tui.messages import SendToTarget

        app = _FakeApp()
        app._screen = _FakeScreen()
        req = _mk_req("rid-1")
        app.on_proxy_request_done(types.SimpleNamespace(req=req))
        assert app._screen.rows == [("update", req)]
        assert len(app.posted) == 1
        assert isinstance(app.posted[0], SendToTarget)
        assert app.posted[0].req is req

    def test_discards_from_pending(self):
        app = _FakeApp()
        app._pending_done_ids = {"rid-1"}
        app._screen = _FakeScreen()
        app.on_proxy_request_done(types.SimpleNamespace(req=_mk_req("rid-1")))
        assert "rid-1" not in app._pending_done_ids


class TestBusBridges:
    def test_captured_ignores_non_ir(self):
        app = _FakeApp()
        app._on_bus_proxy_captured(types.SimpleNamespace(request=object()))
        assert app.posted == []

    def test_captured_posts_added(self):
        from pentool.tui.messages import ProxyRequestAdded

        app = _FakeApp()
        req = _mk_req("rid-2")
        app._on_bus_proxy_captured(types.SimpleNamespace(request=req))
        assert len(app.posted) == 1
        assert isinstance(app.posted[0], ProxyRequestAdded)
        assert app.posted[0].req is req

    def test_completed_deduplicates(self):
        from pentool.tui.messages import ProxyRequestDone

        app = _FakeApp()
        req = _mk_req("rid-3")
        app._on_bus_proxy_completed(types.SimpleNamespace(request=req))
        assert "rid-3" in app._pending_done_ids
        assert len(app.posted) == 1
        assert isinstance(app.posted[0], ProxyRequestDone)
        # Second time same id → deduplicated, no second post.
        app._on_bus_proxy_completed(types.SimpleNamespace(request=_mk_req("rid-3")))
        assert len(app.posted) == 1


class TestOnClearAndLoad:
    def test_clear_history(self):
        app = _FakeApp()
        app._screen = _FakeScreen()
        app.on_proxy_clear_history(types.SimpleNamespace())
        assert app._screen.cleared == 1

    def test_load_project(self):
        app = _FakeApp()
        app._screen = _FakeScreen()
        app.on_proxy_load_project(types.SimpleNamespace())
        assert app._screen.loaded == 1
