"""Guards: the site map must reach the DB even for a single seeded host.

`--url/--smart` adds exactly one host through `add_request_from_proxy`, and the
old code persisted every 20th request only: a fresh project opened with an empty
Target tree ("the host does not land in Target"). The flush is now debounced, forced
on unmount, and forced right after the seed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pentool.tui.screens.target.screen import TargetScreen


def _screen() -> TargetScreen:
    screen = TargetScreen()
    screen._target_api = MagicMock()
    screen._target_api.save = AsyncMock()
    return screen


def test_first_request_marks_the_site_map_dirty() -> None:
    screen = _screen()
    screen.set_timer = MagicMock()
    screen.call_after_refresh = MagicMock()

    screen.add_request_from_proxy(MagicMock(method="GET", url="https://example.com/", headers={}, body=b""))

    assert screen._sitemap_dirty is True, "one seed request must schedule a flush, not wait for the 20th"
    screen.set_timer.assert_called_once()


def test_flush_writes_and_clears_the_flag() -> None:
    screen = _screen()
    screen._sitemap_dirty = True

    asyncio.run(screen.flush_sitemap())

    screen._target_api.save.assert_awaited_once()
    assert screen._sitemap_dirty is False


def test_flush_is_a_no_op_when_nothing_changed() -> None:
    screen = _screen()

    asyncio.run(screen.flush_sitemap())

    screen._target_api.save.assert_not_awaited()


def test_timer_flush_starts_a_tracked_worker() -> None:
    screen = _screen()
    screen._sitemap_dirty = True
    screen._start_save_worker = MagicMock()
    # Plot stub, not a coroutine: the real method returns an awaitable, and a
    # never-awaited coroutine would fail the suite with a RuntimeWarning.
    screen._do_save_sitemap = MagicMock(return_value="save-task")

    with patch.object(TargetScreen, "is_mounted", property(lambda self: True)):
        screen._flush_sitemap_sync()

    screen._start_save_worker.assert_called_once()
    assert screen._sitemap_dirty is False


def test_unmounted_screen_does_not_start_a_flush() -> None:
    """Unmount has its own flush; a timer firing afterwards must not leak a coroutine."""
    screen = _screen()
    screen._sitemap_dirty = True
    screen._start_save_worker = MagicMock()

    with patch.object(TargetScreen, "is_mounted", property(lambda self: False)):
        screen._flush_sitemap_sync()

    screen._start_save_worker.assert_not_called()
    assert screen._sitemap_dirty is True, "the write is still owed and must be flushed on unmount"
