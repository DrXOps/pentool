"""Unit tests for ProxyEventHandlersMixin (Этап 5.1) — EventBus bridge only.

The mixin contains ONLY the EventBus → Textual-message bridge
(_on_bus_proxy_captured / _on_bus_proxy_completed), which is invoked directly
by the bus (not via Textual `@on` dispatch), so it is safe as an MRO mixin.

The `@on(...)` proxy handlers (on_proxy_request_added/done/clear_history/
load_project) intentionally live in PentoolApp — see
test_proxy_event_dispatch.py for their coverage and the regression guard that
keeps them there.
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


class _FakeApp(ProxyEventHandlersMixin):
    def __init__(self):
        self._pending_done_ids: set = set()
        self.posted = []

    def post_message(self, msg):
        self.posted.append(msg)

    def call_from_thread(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


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

    def test_too_many_empty_is_noop(self):
        app = _FakeApp()
        app._on_bus_proxy_captured(types.SimpleNamespace(request=None))
        app._on_bus_proxy_completed(types.SimpleNamespace(request=None))
        assert app.posted == []
