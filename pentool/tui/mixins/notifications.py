"""NotificationsMixin — standardised toasts (flash/notify) for the App.

Extracted from PentoolApp (Этап 5.1, notifications domain) so the app class
stays thin and notification behaviour is tested/reused in one place. Ties all
`app.notify(...)` call sites into Textual's built-in toast rack and layers a
config-gated sound on top.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NotificationsMixin:
    """Mix-in providing flash() and notify() for a Textual App.

    Requires the host to be a Textual App subclass (super().notify exists) and
    to expose `_cfg.notifications_sound_enabled` (Config).
    """

    def flash(self, message: str, severity: str = "information", timeout: float = 2.5) -> None:
        """Short message on the right side of the module bar (tooltip2)."""
        try:
            from pentool.tui.widgets.module_tabs import ModuleTabs

            self.query_one("#module-tabs", ModuleTabs).flash(message, severity, timeout)  # type: ignore[attr-defined]
        except Exception:
            pass

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
        sound: bool = True,
    ) -> None:
        """Standard notification via Textual's built-in toast rack.

        Renders severity-styled cards bottom-right WITHOUT reserving a zone
        (no dark band). Sound is layered on top, respecting the user's
        `notifications_sound_enabled` config toggle.
        """
        super().notify(  # type: ignore[misc]
            message,
            title=title,
            severity=severity,
            timeout=timeout,
            markup=markup,
        )
        # Belt-and-braces dismissal: Textual's toast rack only prunes expired
        # toasts when the rack is refreshed. If the app is busy it can leave an
        # expired toast sitting. Unless kept forever (critical), schedule a
        # refresh shortly after the timeout so it always dismisses on its own.
        #
        # Guarded: notify() runs from many contexts (proxy threads via
        # call_from_thread, timers, right before/after screen teardown). If
        # set_timer/_refresh_notifications are unavailable (app winding down,
        # or a host that isn't a full Textual App) we still must never let a
        # toast break the caller — the toast itself is the failure surface the
        # user would see as "failed notification".
        if timeout is not None:
            try:
                self.set_timer(timeout + 0.5, self._refresh_notifications)  # type: ignore[attr-defined]
            except Exception as exc:
                # Timer unavailable — toast will just auto-expire on the next
                # refresh; not fatal, but log it so a real problem (e.g. a
                # missing _refresh_notifications after a refactor) is visible
                # instead of silently swallowed.
                logger.debug("notify: could not schedule toast refresh timer: %s", exc)
        if sound:
            try:
                if self._cfg.notifications_sound_enabled:  # type: ignore[attr-defined]
                    from pentool.core.notification_sound import play_notification_sound

                    play_notification_sound(severity)
            except Exception as exc:
                logger.debug("notify: sound failed: %s", exc)
