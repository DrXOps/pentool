"""Unit tests for AutoSaveMixin (Stage 3.1)."""

from __future__ import annotations

import pytest

from pentool.tui.mixins.autosave import AutoSaveMixin


class _FakeWorkers:
    """Emulates Textual's WorkerManager: workers live in named groups.

    The real manager has no ``cancel(name)`` — only ``cancel_group``,
    ``cancel_all``, ``cancel_node``, ``add_worker``, ``start_all`` and
    ``wait_for_complete``. The fake mirrors that surface so a regression to
    the removed ``cancel`` call fails loudly instead of being swallowed.
    """

    def __init__(self, host):
        self._host = host

    def cancel_group(self, node, group: str) -> None:
        for name in [n for n, g in self._host.worker_groups.items() if g == group]:
            del self._host.worker_groups[name]

    def cancel_all(self, node=None) -> None:
        self._host.worker_groups.clear()


class _FakeHost(AutoSaveMixin):
    """Minimal host exposing only what the mixin touches."""

    def __init__(self):
        self._running_save_tasks: list[str] = []
        self.worker_groups: dict[str, str] = {}

    def run_worker(self, awaitable, *, name, group, exclusive, exit_on_error):
        self.worker_groups[name] = group
        awaitable.close()
        return name

    @property
    def workers(self):
        return _FakeWorkers(self)


class TestAutoSaveMixin:
    def test_init_and_track(self):
        host = _FakeHost()
        host._init_save_tasks()
        host._track_save_worker("w1")
        host._track_save_worker("w2")
        assert host._running_save_tasks == ["w1", "w2"]

    @pytest.mark.asyncio
    async def test_do_auto_save_cleans_up(self):
        async def _noop():
            return None

        host = _FakeHost()
        host._init_save_tasks()
        host._track_save_worker("w1")
        await host._do_auto_save(_noop(), "w1")
        assert host._running_save_tasks == []

    @pytest.mark.asyncio
    async def test_do_auto_save_cleans_up_on_error(self):
        async def _boom():
            raise RuntimeError("save failed")

        host = _FakeHost()
        host._init_save_tasks()
        host._track_save_worker("w1")
        await host._do_auto_save(_boom(), "w1")  # must not raise
        assert host._running_save_tasks == []

    def test_cancel_save_workers(self):
        host = _FakeHost()
        host._init_save_tasks()
        host.worker_groups = {"a": "autosave", "b": "autosave", "other": "attack"}
        host._running_save_tasks = ["a", "b"]
        host._cancel_save_workers()
        assert host._running_save_tasks == []
        # Only the autosave group is cancelled — an attack worker survives.
        assert host.worker_groups == {"other": "attack"}

    def test_start_save_worker_puts_it_in_group(self):
        class _Noop:
            """Awaitable that never needs awaiting — keeps the test warning-free."""

            def __await__(self):
                return iter(())

        host = _FakeHost()
        host._init_save_tasks()
        host._start_save_worker(_Noop(), "save-x")
        assert host._running_save_tasks == ["save-x"]
        assert host.worker_groups == {"save-x": AutoSaveMixin.SAVE_WORKER_GROUP}

    def test_save_worker_name_unique(self):
        host = _FakeHost()
        n1 = host._save_worker_name("save-1")
        n2 = host._save_worker_name("save-1")
        assert n1 != n2
        assert n1.startswith("save-1-")
