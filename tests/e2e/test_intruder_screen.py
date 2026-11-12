"""E2E: IntruderScreen — the Start button label tells the truth about state.

``#btn-start`` toggles "▶ Start" / "⏸ Pause" / "▶ Resume" as
``action_toggle_pause()`` and ``action_stop()`` run. The state these labels
mirror lives on the active tab (``_IntruderTabState.running/.paused``), not on
the screen: when Intruder became multi-tab, per-tab attack state moved into the
tab and the screen kept only the toolbar sync.

These tests were failing before the audit for two different reasons, and both
are pinned here:

* a fresh tab showed "⏸ Pause" — ``_sync_toolbar_from_tab`` calls
  ``set_running(False)`` and then ``set_paused(False)``, and the latter used to
  relabel the button to "⏸ Pause" regardless of whether anything was running;
* the tests themselves still poked ``screen._attack_running`` / ``_paused`` /
  ``_api``, attributes that stopped existing with the multi-tab refactor. They
  are rewritten against the tab, which is what the production code reads.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.widgets.toolbar_button import ToolbarButton


class _FakeAttack:
    """An attack with nothing to do: pause/resume/stop must exist and return."""

    async def pause(self) -> None:
        ...

    async def resume(self) -> None:
        ...

    async def stop(self) -> None:
        ...


async def _open_intruder(pilot) -> tuple[IntruderScreen, ToolbarButton]:
    await pilot.pause()
    await pilot.press("I")
    await pilot.pause()
    await pilot.pause()
    screen = pilot.app.query_one(IntruderScreen)
    return screen, screen.query_one("#btn-start", ToolbarButton)


def _start_fake_attack(screen: IntruderScreen) -> None:
    """Put the active tab into "attack running" without touching the network."""
    tab = screen._active_tab
    assert tab is not None, "the screen has no active tab to run an attack on"
    tab.attack = _FakeAttack()
    tab.running = True
    tab.paused = False
    screen._ssw.set_running(True)


@pytest.mark.e2e
class TestIntruderScreen:
    async def test_fresh_tab_starts_stopped(self) -> None:
        """The toolbar must not claim an attack is running before there is one.

        This is the state the label bug produced: restoring a tab called
        ``set_paused(False)`` after ``set_running(False)`` and the button left
        as "⏸ Pause".
        """
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            _, btn = await _open_intruder(pilot)
            assert btn.label == "▶ Start"
            assert btn.has_class("active") is True, "Stop-equivalent state must offer Start as the action"

    async def test_pause_resume_button_label_toggles(self) -> None:
        """Pause → "▶ Resume", resume → "⏸ Pause", both reflected on the tab."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            screen, btn = await _open_intruder(pilot)
            _start_fake_attack(screen)
            tab = screen._active_tab

            assert btn.label == "⏸ Pause"

            screen.action_toggle_pause()
            await pilot.pause()
            assert tab is not None and tab.paused is True
            assert btn.label == "▶ Resume"

            screen.action_toggle_pause()
            await pilot.pause()
            assert tab.paused is False
            assert btn.label == "⏸ Pause"

    async def test_stop_resets_pause_label_even_when_paused(self) -> None:
        """Stopping while paused resets to "▶ Start".

        Otherwise the next Start Attack would show "▶ Resume" left over from
        the stopped run.
        """
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            screen, btn = await _open_intruder(pilot)
            _start_fake_attack(screen)
            tab = screen._active_tab

            screen.action_toggle_pause()
            await pilot.pause()
            assert btn.label == "▶ Resume"

            screen.action_stop()
            await pilot.pause()
            assert tab is not None
            assert tab.running is False
            assert tab.paused is False
            assert btn.label == "▶ Start"
