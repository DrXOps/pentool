"""Unit tests for AutoSaveMixin (Этап 3.1)."""

from __future__ import annotations

import pytest

from pentool.tui.mixins.autosave import AutoSaveMixin


class _FakeWorkers:
    def __init__(self, host):
        self._host = host
        self._names = set()

    def cancel(self, name: str) -> None:
        self._host.workers_names.discard(name)


class _FakeHost(AutoSaveMixin):
    """Minimal host exposing only what the mixin touches."""

    def __init__(self):
        self._running_save_tasks: list[str] = []
        self.workers_names = set()

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
        host._running_save_tasks = ["a", "b"]
        host.workers_names = {"a", "b"}
        host._cancel_save_workers()
        assert host._running_save_tasks == []
        assert host.workers_names == set()

    def test_save_worker_name_unique(self):
        host = _FakeHost()
        n1 = host._save_worker_name("save-1")
        n2 = host._save_worker_name("save-1")
        assert n1 != n2
        assert n1.startswith("save-1-")
