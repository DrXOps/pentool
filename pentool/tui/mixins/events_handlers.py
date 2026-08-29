"""ProxyEventHandlersMixin — Textual/EventBus handlers for proxy activity.

Extracted from PentoolApp (Этап 5.1, events-handlers domain) so the app class
stays thin and the proxy→UI bridge is tested/understood in one place.

The mixin expects its host (the App) to expose:
    _proxy                  — ProxyServer | None
    _pending_done_ids       — set of request ids awaiting GUI row completion
    _get_proxy_screen()     — cached ProxyScreen | None
    post_message(msg)        — Textual API
    call_from_thread(fn, *a) — thread-safe dispatch into the TUI loop
    query_one(...)           — Textual API
"""

from __future__ import annotations

import logging

from textual import on

from pentool.api.proxy_api import InterceptedRequest as _IR
from pentool.core.events import ProxyRequestCaptured, ProxyRequestCompleted
from pentool.tui.messages import (
    ProxyClearHistory,
    ProxyLoadProject,
    ProxyRequestAdded,
    ProxyRequestDone,
    SendToTarget,
)
from pentool.tui.constants import SCREEN_PROXY
from pentool.tui.screens import ProxyScreen

logger = logging.getLogger(__name__)


class ProxyEventHandlersMixin:
    """Mix-in handling proxy request/response lifecycle events for the UI."""

    @on(ProxyRequestAdded)
    def on_proxy_request_added(self, msg: ProxyRequestAdded) -> None:
        """Proxy captured a new request → update ProxyScreen."""
        if not (self._proxy and self._proxy.is_running):  # type: ignore[attr-defined]
            return
        try:
            screen = self._get_proxy_screen()  # type: ignore[attr-defined]
            if screen is None:
                return  # quiet no-op — screen not mounted; do NOT log each call
            screen.add_request_row(msg.req)
            if self._proxy and self._proxy.intercept_enabled:  # type: ignore[attr-defined]
                screen.show_intercepted_request(msg.req)  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("on_proxy_request_added: %s", e)

    @on(ProxyRequestDone)
    def on_proxy_request_done(self, msg: ProxyRequestDone) -> None:
        """Proxy completed a request/response cycle → update the row and SiteMap."""
        # Remove from pending — the next request with this id will pass through again
        req_id = getattr(msg.req, "id", None)
        self._pending_done_ids.discard(req_id)  # type: ignore[attr-defined]
        # Guard: msg.req must be InterceptedRequest
        if not isinstance(msg.req, _IR):
            logger.warning("on_proxy_request_done: msg.req is %s, skipping", type(msg.req))
            return
        try:
            screen = self._get_proxy_screen()  # type: ignore[attr-defined]
            if screen is None:
                return  # quiet no-op — screen not mounted; do NOT log each call
            screen.update_request_row(msg.req)
            if self._proxy and self._proxy.intercept_enabled:  # type: ignore[attr-defined]
                screen.show_intercept_response(msg.req)  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("on_proxy_request_done (proxy screen): %s", e)
        # Auto-build SiteMap
        self.post_message(SendToTarget(msg.req))  # type: ignore[attr-defined]

    @on(ProxyClearHistory)
    def on_proxy_clear_history(self, msg: ProxyClearHistory) -> None:
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)  # type: ignore[attr-defined]
            screen.action_clear_list()
        except Exception as e:
            logger.debug("on_proxy_clear_history: %s", e)

    @on(ProxyLoadProject)
    def on_proxy_load_project(self, msg: ProxyLoadProject) -> None:
        """Reload the ProxyScreen table after loading a project."""
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)  # type: ignore[attr-defined]
            screen.load_from_project()
        except Exception as e:
            logger.debug("on_proxy_load_project: %s", e)

    def _on_bus_proxy_captured(self, event: ProxyRequestCaptured) -> None:
        """EventBus: proxy captured a new request.

        Bridge: proxy emit from its thread → EventBus → this method is called
        synchronously in the proxy thread → call_from_thread → Textual Message in TUI thread.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        self.call_from_thread(  # type: ignore[attr-defined]
            self.post_message, ProxyRequestAdded(req)  # type: ignore[attr-defined]
        )

    def _on_bus_proxy_completed(self, event: ProxyRequestCompleted) -> None:
        """EventBus: request through proxy completed.

        Bridge: proxy emit from its thread → EventBus → call_from_thread → Textual Message.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        req_id = req.id
        # Deduplication: if already pending, ignore
        if req_id in self._pending_done_ids:  # type: ignore[attr-defined]
            return
        self._pending_done_ids.add(req_id)  # type: ignore[attr-defined]
        self.call_from_thread(  # type: ignore[attr-defined]
            self.post_message, ProxyRequestDone(req)  # type: ignore[attr-defined]
        )
