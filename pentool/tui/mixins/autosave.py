"""AutoSaveMixin — shared tracked fire-and-forget worker pattern.

Repeater and Intruder both auto-save state/results to the DB in background
workers, tracking the in-flight worker name in `_running_save_tasks` and
cancelling them on teardown so an in-flight commit never hits a closed DB
when the user exits or switches projects. This mixin centralises that reduce
duplicated logic.
"""

from __future__ import annotations

import time


class AutoSaveMixin:
    """Mix-in that provides tracked, cancellable auto-save workers.

    Subclass must have `run_worker(...)`/`workers` (Textual Widget interface).
    """

    def _init_save_tasks(self) -> None:
        """Initialise the tracked-worker list (call once, e.g. in compose/on_mount)."""
        if not hasattr(self, "_running_save_tasks"):
            self._running_save_tasks: list[str] = []

    # ── Tracked worker helpers ────────────────────────────────────────────────

    def _track_save_worker(self, name: str) -> None:
        self._init_save_tasks()
        self._running_save_tasks.append(name)

    async def _do_auto_save(self, coro, worker_name: str) -> None:
        """Await a save coroutine, then drop it from the tracked list."""
        try:
            await coro
        except Exception:
            pass
        finally:
            self._running_save_tasks = [
                w for w in self._running_save_tasks if w != worker_name
            ]

    def _cancel_save_workers(self) -> None:
        """Cancel all tracked auto-save workers and clear the list."""
        if not hasattr(self, "_running_save_tasks"):
            self._running_save_tasks = []
        for wname in list(self._running_save_tasks):
            try:
                self.workers.cancel(wname)
            except Exception:
                pass
        self._running_save_tasks.clear()

    # ── Worker-name helper ────────────────────────────────────────────────────

    @staticmethod
    def _save_worker_name(prefix: str) -> str:
        return f"{prefix}-{time.monotonic_ns()}"
