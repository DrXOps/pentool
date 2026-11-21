"""AutoSaveMixin — shared tracked fire-and-forget worker pattern.

Repeater, Intruder and Target all auto-save state to the DB in background
workers and cancel them on teardown, so an in-flight commit never hits a
closed DB when the user exits or switches projects.

Workers are started through :meth:`AutoSaveMixin._start_save_worker`, which
puts them in the dedicated group `SAVE_WORKER_GROUP` and tracks the worker
name. Cancellation goes through ``WorkerManager.cancel_group`` — the previous
implementation called ``self.workers.cancel(name)``, a method that does not
exist on Textual's ``WorkerManager`` (its API is ``add_worker``,
``cancel_all``, ``cancel_group``, ``cancel_node``, ``start_all``,
``wait_for_complete``), so the ``except Exception`` around it swallowed an
``AttributeError`` and cancellation was a no-op (REPORT F-045).
"""

from __future__ import annotations

import time
from typing import Any

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class AutoSaveMixin:
    """Mix-in that provides tracked, cancellable auto-save workers.

    Subclass must have `run_worker(...)`/`workers` (Textual Widget interface).
    """

    #: Worker group used for every auto-save worker of this widget.
    SAVE_WORKER_GROUP: str = "autosave"

    def _init_save_tasks(self) -> None:
        """Initialise the tracked-worker list (call once, e.g. in compose/on_mount)."""
        if not hasattr(self, "_running_save_tasks"):
            self._running_save_tasks: list[str] = []

    # ── Tracked worker helpers ────────────────────────────────────────────────

    def _track_save_worker(self, name: str) -> None:
        self._init_save_tasks()
        self._running_save_tasks.append(name)

    def _start_save_worker(
        self,
        save_task: Any,
        worker_name: str,
        *,
        exit_on_error: bool = False,
    ) -> None:
        """Run ``save_task`` as a tracked, cancellable background worker."""
        self._track_save_worker(worker_name)
        self.run_worker(  # type: ignore[attr-defined]
            self._do_auto_save(save_task, worker_name),
            name=worker_name,
            group=self.SAVE_WORKER_GROUP,
            exclusive=False,
            exit_on_error=exit_on_error,
        )

    async def _do_auto_save(self, coro: Any, worker_name: str) -> None:
        """Await a save coroutine, then drop it from the tracked list."""
        try:
            await coro
        except Exception:
            # The module state was not saved: after a restart the user will see
            # an older version than the one they worked with. That is data loss —
            # log an error with a traceback, not debug.
            logger.error("autosave: %s did not save", worker_name, exc_info=True)
        finally:
            self._running_save_tasks = [w for w in self._running_save_tasks if w != worker_name]

    def _cancel_save_workers(self) -> None:
        """Cancel every in-flight auto-save worker and clear the tracked list."""
        self._init_save_tasks()
        try:
            self.workers.cancel_group(self, self.SAVE_WORKER_GROUP)  # type: ignore[attr-defined]
        except Exception:
            # The group was not cancelled — the save will finish after the DB is
            # already closed (exactly the case this mixin exists for): the write
            # may fail or get lost, hence error with a traceback.
            logger.error("autosave: worker group not cancelled", exc_info=True)
        self._running_save_tasks.clear()

    # ── Worker-name helper ────────────────────────────────────────────────────

    @staticmethod
    def _save_worker_name(prefix: str) -> str:
        return f"{prefix}-{time.monotonic_ns()}"
