"""ProjectAutoSaveMixin — periodic project auto-save timer for the App.

Extracted from PentoolApp (Этап 5.1, autosave domain). This is the periodic
*TUI* timer that re-arms from config and surfaces a toast on each tick — it is
deliberately NOT merged into ProjectManager (whose save_project/save_project_json
are on-demand saves); a timer that needs set_interval + notify belongs to the
App layer, not the project store.

The mixin expects its host (the App) to expose:
    _cfg               — Config (auto_save_enabled, auto_save_interval, db_path)
    _auto_save_timer   — Textual timer or None (owned by the mixin)
    _project_loaded    — bool
    _project_path      — str | None
    set_interval(...)   — Textual API
    notify(...)         — from NotificationsMixin
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class ProjectAutoSaveMixin:
    """Mix-in providing the periodic project auto-save timer + tick."""

    def _setup_auto_save(self) -> None:
        """Configure / restart the auto-save timer from the current config.

        Safe to call at any time — including from call_after_refresh and on_mount.
        Stops the old timer cleanly before creating a new one.
        """
        # Pause the old timer before replacing it.
        # Timer.pause() is safe to call from any point in the event loop;
        # .stop() schedules a cancellation but may race if called during a tick.
        if self._auto_save_timer is not None:  # type: ignore[attr-defined]
            try:
                self._auto_save_timer.pause()  # type: ignore[attr-defined]
                self._auto_save_timer.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._auto_save_timer = None  # type: ignore[attr-defined]

        if getattr(self._cfg, "auto_save_enabled", False):  # type: ignore[attr-defined]
            interval_min = max(1, getattr(self._cfg, "auto_save_interval", 5))
            interval_sec = interval_min * 60
            self._auto_save_timer = self.set_interval(  # type: ignore[attr-defined]
                interval_sec, self._auto_save_tick  # type: ignore[attr-defined]
            )
            logger.info("APP: auto-save enabled, interval=%d min", interval_min)
        else:
            logger.info("APP: auto-save disabled")

    def _auto_save_tick(self) -> None:
        """Periodic auto-save of the project (silent, no dialogs)."""
        if not self._project_loaded:  # type: ignore[attr-defined]
            return
        path = self._project_path or self._cfg.db_path  # type: ignore[attr-defined]
        if not path:
            return
        try:
            # SQLite DB is already in place — just show a notification
            name = os.path.basename(path)
            self.notify(f"Auto-saved: {name}", timeout=2)  # type: ignore[attr-defined]
            logger.info("APP: auto-saved project %s", path)
        except Exception as exc:
            logger.debug("_auto_save_tick: %s", exc)
