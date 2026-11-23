"""F-015: closing the Intruder tab must stop its attack.

`action_start_attack` creates an attack, puts it into the tab state and starts
the worker. Closing a tab used to only remove the pane from `TabbedContent`:
the attack kept sending requests to the target that the user no longer sees,
and the worker lived until the end of `attack.run()`. The same happened when
leaving the screen — and there `query_one("#intruder-tabs")` in `on_unmount`
did not find the DOM at all, so not even the tab list was read.

The tests hold a real twin attack: it never finishes on its own, so "stopped"
and "not stopped" are distinguishable by the `stop()` counter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.widgets import ContentSwitcher

from pentool.tui.screens.intruder.screen import IntruderScreen


class _SpyAttack:
    """Twin attack: hangs until it is released.

    ``stop()`` only counts the call. Whether it releases ``run()`` is a
    parameter: with ``releases=False`` the worker is taken down exclusively via
    ``workers.cancel_group``, and then the test tells "asked to stop" apart from
    "worker removed". The real attack behaves exactly like that: ``stop()``
    raises a flag inside the network loop and does not return immediately.
    """

    def __init__(self, releases: bool = True) -> None:
        self.stopped = 0
        self.started = 0
        self._releases = releases
        self._release = asyncio.Event()

    async def run(self, on_result, on_progress) -> None:
        self.started += 1
        await self._release.wait()

    async def stop(self) -> None:
        self.stopped += 1
        if self._releases:
            self._release.set()

    async def pause(self) -> None:
        return None

    async def resume(self) -> None:
        return None


@dataclass
class _FakeApi:
    attack: _SpyAttack

    def make_attack(self, config, turbo_mode: bool = False) -> _SpyAttack:
        return self.attack


class _App(App):
    def compose(self) -> ComposeResult:
        with ContentSwitcher():
            yield IntruderScreen()


async def _settle(pilot, cycles: int = 8) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def _screen_with_running_attack(pilot, releases: bool = True):
    """Bring the screen to the "attack is running" state without network and without DB."""
    screen = pilot.app.query_one(IntruderScreen)
    spy = _SpyAttack(releases=releases)
    screen._api = _FakeApi(attack=spy)  # type: ignore[assignment]
    screen._get_api = lambda: screen._api  # type: ignore[method-assign]

    tab = screen._active_tab
    assert tab is not None, "the screen must open with one tab"
    tab.attack_type = tab.attack_type  # noqa: B018 — keep the state object
    tab.template_text = "GET /§§ HTTP/1.1\r\nHost: example.com\r\n\r\n"

    # Minimal path without UI validation: the same as action_start_attack does
    # after building the config.
    tab.attack = spy  # type: ignore[assignment]
    tab.running = True
    screen._live_attacks[tab.tab_id] = spy
    group = screen._attack_group(tab.tab_id)
    screen.run_worker(screen._run_attack(tab, spy), exclusive=False, name=group, group=group)
    await _settle(pilot)
    return screen, tab, spy


class TestClosingATabStopsItsAttack:
    async def test_closing_the_tab_asks_the_attack_to_stop(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen, tab, spy = await _screen_with_running_attack(pilot)
            assert spy.started == 1, "precondition: the attack worker must be running"

            # A second tab is needed: closing the last panel is not allowed.
            screen._tc_panel.action_new_tab()
            await _settle(pilot)
            screen._tc_panel.switch_to(tab.tab_id)
            await _settle(pilot)

            screen._tc_panel.action_close_tab()
            await _settle(pilot)

            assert spy.stopped >= 1, (
                "the tab was closed but its attack kept running — the worker is "
                "cancelled only by name, and closing a tab never asked it to stop"
            )
            assert tab.tab_id not in screen._live_attacks, (
                "a closed tab's attack stayed registered — on_unmount would try to stop an attack that no longer exists"
            )
            assert tab.running is False

    async def test_the_worker_is_cancelled_not_just_asked(self) -> None:
        """Removing the group means not waiting for the end of `attack.run()`.

        ``releases=False``: `stop()` does not release `run()`, so the worker
        disappears only if it was really cancelled.
        """
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen, tab, spy = await _screen_with_running_attack(pilot, releases=False)

            screen._stop_tab_attack(tab)
            await _settle(pilot)

            groups = {w.group for w in screen.workers._workers if w.group}
            assert screen._attack_group(tab.tab_id) not in groups, (
                "the attack worker is still registered: cancel_group never reached it"
            )


class TestLeavingTheScreenStopsAttacks:
    async def test_unmount_reaches_an_attack_whose_dom_is_already_gone(self) -> None:
        """`on_unmount` cannot look up tabs in the DOM — only in its own dict."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen, tab, spy = await _screen_with_running_attack(pilot)

            screen.on_unmount()
            await _settle(pilot)

            assert spy.stopped >= 1, "leaving the screen left its attack running"
            assert screen._live_attacks == {}
