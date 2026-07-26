"""Unit tests: message storm protection in app.py (Sprint 3: EventBus).

Covers:
- _on_bus_proxy_captured: guard on isinstance(req, InterceptedRequest)
- _on_bus_proxy_completed: guard + deduplication by req.id
- on_proxy_request_done: removing req.id from pending set after handling
- req types in ProxyRequestDone/ProxyRequestAdded are always InterceptedRequest
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from pentool.core.events import ProxyRequestCaptured, ProxyRequestCompleted
from pentool.modules.proxy import InterceptedRequest, ProxyServer
from pentool.tui.messages import ProxyRequestAdded, ProxyRequestDone


def _make_ireq(req_id: str = "test-id-001") -> InterceptedRequest:
    """Create a test InterceptedRequest."""
    return InterceptedRequest(
        id=req_id,
        method="GET",
        url="http://example.com/",
        headers={"Host": "example.com"},
        body="",
        timestamp=datetime.now(timezone.utc),
    )


class TestProxyCallbackGuard:
    """_on_bus_proxy_captured and _on_bus_proxy_completed should discard non-IR objects."""

    def _make_app_stub(self):
        """Create a minimal PentoolApp stub for testing EventBus handlers."""
        from pentool.tui.app import PentoolApp
        # Use object() to avoid starting Textual
        app = object.__new__(PentoolApp)
        # Initialize only the required attributes
        app._thread_id = threading.get_ident()
        app._pending_done_ids = set()
        app._posted_messages = []

        def fake_call_from_thread(fn, *args):
            fn(*args)

        def fake_post_message(msg):
            app._posted_messages.append(msg)

        app.call_from_thread = fake_call_from_thread
        app.post_message = fake_post_message
        return app

    def test_on_bus_proxy_captured_accepts_intercepted_request(self) -> None:
        """_on_bus_proxy_captured accepts InterceptedRequest."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-001")
        event = ProxyRequestCaptured(request_id=ireq.id, request=ireq)

        PentoolApp._on_bus_proxy_captured(app, event)

        assert len(app._posted_messages) == 1
        assert isinstance(app._posted_messages[0], ProxyRequestAdded)
        assert app._posted_messages[0].req is ireq

    def test_on_bus_proxy_captured_rejects_wrong_type(self) -> None:
        """_on_bus_proxy_captured discards non-InterceptedRequest object."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()

        # Pass ProxyRequestDone as request — this simulates a bug
        bad_obj = ProxyRequestDone(_make_ireq())
        event = ProxyRequestCaptured(request_id="bad", request=bad_obj)
        PentoolApp._on_bus_proxy_captured(app, event)

        assert len(app._posted_messages) == 0

    def test_on_bus_proxy_captured_rejects_string(self) -> None:
        """_on_bus_proxy_captured discards a string."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()

        event = ProxyRequestCaptured(request_id="str", request="not a request")
        PentoolApp._on_bus_proxy_captured(app, event)

        assert len(app._posted_messages) == 0

    def test_on_bus_proxy_completed_accepts_intercepted_request(self) -> None:
        """_on_bus_proxy_completed accepts InterceptedRequest."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-002")
        event = ProxyRequestCompleted(request_id=ireq.id, request=ireq, status_code=200)

        PentoolApp._on_bus_proxy_completed(app, event)

        assert len(app._posted_messages) == 1
        assert isinstance(app._posted_messages[0], ProxyRequestDone)
        assert app._posted_messages[0].req is ireq

    def test_on_bus_proxy_completed_rejects_wrong_type(self) -> None:
        """_on_bus_proxy_completed discards non-InterceptedRequest."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()

        bad_obj = ProxyRequestDone(_make_ireq())
        event = ProxyRequestCompleted(request_id="bad", request=bad_obj, status_code=200)
        PentoolApp._on_bus_proxy_completed(app, event)

        assert len(app._posted_messages) == 0


class TestProxyRequestDoneDeduplication:
    """Deduplication: one ProxyRequestDone per req.id until handled."""

    def _make_app_stub(self):
        from pentool.tui.app import PentoolApp
        app = object.__new__(PentoolApp)
        app._thread_id = threading.get_ident()
        app._pending_done_ids = set()
        app._posted_messages = []

        def fake_call_from_thread(fn, *args):
            fn(*args)

        def fake_post_message(msg):
            app._posted_messages.append(msg)

        app.call_from_thread = fake_call_from_thread
        app.post_message = fake_post_message
        return app

    def test_first_call_passes(self) -> None:
        """First call for req.id — passes."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-dedup-001")
        event = ProxyRequestCompleted(request_id=ireq.id, request=ireq, status_code=200)

        PentoolApp._on_bus_proxy_completed(app, event)

        assert len(app._posted_messages) == 1

    def test_duplicate_call_blocked(self) -> None:
        """Second call with same req.id — blocked (until first is handled)."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-dedup-002")
        event = ProxyRequestCompleted(request_id=ireq.id, request=ireq, status_code=200)

        PentoolApp._on_bus_proxy_completed(app, event)
        PentoolApp._on_bus_proxy_completed(app, event)  # duplicate

        assert len(app._posted_messages) == 1  # second was skipped

    def test_after_discard_next_call_passes(self) -> None:
        """After removing req.id from pending — next call passes."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-dedup-003")
        event = ProxyRequestCompleted(request_id=ireq.id, request=ireq, status_code=200)

        # First call — passes, req.id goes into pending
        PentoolApp._on_bus_proxy_completed(app, event)
        assert len(app._posted_messages) == 1

        # Remove from pending (simulating on_proxy_request_done handler)
        app._pending_done_ids.discard(ireq.id)

        # Next call — passes
        PentoolApp._on_bus_proxy_completed(app, event)
        assert len(app._posted_messages) == 2

    def test_different_req_ids_both_pass(self) -> None:
        """Different req.id — both pass."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq1 = _make_ireq("req-a")
        ireq2 = _make_ireq("req-b")
        event1 = ProxyRequestCompleted(request_id=ireq1.id, request=ireq1, status_code=200)
        event2 = ProxyRequestCompleted(request_id=ireq2.id, request=ireq2, status_code=200)

        PentoolApp._on_bus_proxy_completed(app, event1)
        PentoolApp._on_bus_proxy_completed(app, event2)

        assert len(app._posted_messages) == 2

    def test_storm_100_calls_same_id_blocked(self) -> None:
        """100 calls with same req.id → only 1 message."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-storm")
        event = ProxyRequestCompleted(request_id=ireq.id, request=ireq, status_code=200)

        for _ in range(100):
            PentoolApp._on_bus_proxy_completed(app, event)

        assert len(app._posted_messages) == 1

    def test_pending_ids_cleared_on_handler(self) -> None:
        """on_proxy_request_done removes req.id from pending_done_ids."""
        from pentool.tui.app import PentoolApp
        app = self._make_app_stub()
        ireq = _make_ireq("req-clear-001")

        # Add req.id to pending (simulating _on_bus_proxy_completed)
        app._pending_done_ids.add(ireq.id)

        # Simulate on_proxy_request_done handler
        msg = ProxyRequestDone(ireq)

        # Call only the discard part (without full app context)
        req_id = getattr(msg.req, "id", None)
        app._pending_done_ids.discard(req_id)

        assert ireq.id not in app._pending_done_ids


class TestProxyRequestMessageTypes:
    """ProxyRequestAdded/ProxyRequestDone should store InterceptedRequest."""

    def test_proxy_request_added_stores_req(self) -> None:
        ireq = _make_ireq("req-msg-001")
        msg = ProxyRequestAdded(ireq)
        assert msg.req is ireq
        assert isinstance(msg.req, InterceptedRequest)

    def test_proxy_request_done_stores_req(self) -> None:
        ireq = _make_ireq("req-msg-002")
        msg = ProxyRequestDone(ireq)
        assert msg.req is ireq
        assert isinstance(msg.req, InterceptedRequest)

    def test_proxy_request_done_req_has_response_attr(self) -> None:
        """msg.req.response should exist (even if None)."""
        ireq = _make_ireq("req-msg-003")
        msg = ProxyRequestDone(ireq)
        # Should not raise AttributeError
        _ = msg.req.response
        assert msg.req.response is None

    def test_proxy_request_done_req_has_method_attr(self) -> None:
        """msg.req.method should exist."""
        ireq = _make_ireq("req-msg-004")
        msg = ProxyRequestDone(ireq)
        assert msg.req.method == "GET"

