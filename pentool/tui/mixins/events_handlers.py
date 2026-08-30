"""ProxyEventHandlersMixin — EventBus bridge for proxy request activity.

Extracted from PentoolApp (Этап 5.1, events-handlers domain).

NOTE on Textual dispatch: methods decorated with `@on(...)` MUST live in the
App class itself — Textual only introspects the direct App class for
`@on(...)` handlers and does NOT see them in MRO mixins. The `@on(...)`
handlers (on_proxy_request_added / done / clear_history / load_project)
therefore stay in app.py, where Textual can dispatch them. What lives HERE is
only the EventBus → Textual bridge (bus.subscribe(...) callbacks, invoked
directly by the bus, not via Textual `@on`), so this mixin is safe as an MRO
mixin.

The mixin expects its host (the App) to expose:
    _pending_done_ids       — set of request ids awaiting GUI row completion
    post_message(msg)        — Textual API
    call_from_thread(fn, *a) — thread-safe dispatch into the TUI loop
"""

from __future__ import annotations

import logging

from pentool.api.proxy_api import InterceptedRequest as _IR
from pentool.core.events import ProxyRequestCaptured, ProxyRequestCompleted
from pentool.tui.messages import ProxyRequestAdded, ProxyRequestDone

logger = logging.getLogger(__name__)


class ProxyEventHandlersMixin:
    """Mix-in bridging proxy-thread events (EventBus) into the TUI loop."""

    def _app_still_running(self) -> bool:
        """Whether the Textual App is still mounted/running.

        These handlers run in the *proxy thread* (via EventBus). When the App
        is being torn down (its run() returned, not via action_quit), call_from_thread
        on a non-running App raises 'App is not running' — which, arriving from the
        proxy thread while the TUI has already exited, is exactly the
        'run() returned cleanly (not via action_quit)' + 'App is not running' spam we
        kept seeing. Guarding here stops bridging into a dead TUI.
        """
        # If the host has no `is_running` attribute (unit-test fake, plain object)
        # treat it as running — only gate on a real App that reports False.
        try:
            val = getattr(self, "is_running", None)
        except Exception:
            return True
        return True if val is None else bool(val)

    def _on_bus_proxy_captured(self, event: ProxyRequestCaptured) -> None:
        """EventBus: proxy captured a new request.

        Bridge: proxy emit from its thread → EventBus → this method is called
        synchronously in the proxy thread → call_from_thread → Textual Message in TUI thread.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        if not self._app_still_running():  # type: ignore[attr-defined]
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
        if not self._app_still_running():  # type: ignore[attr-defined]
            return
        req_id = req.id
        # Deduplication: if already pending, ignore
        if req_id in self._pending_done_ids:  # type: ignore[attr-defined]
            return
        self._pending_done_ids.add(req_id)  # type: ignore[attr-defined]
        self.call_from_thread(  # type: ignore[attr-defined]
            self.post_message, ProxyRequestDone(req)  # type: ignore[attr-defined]
        )
