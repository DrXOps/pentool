"""Port completeness: per-tab state and tooltips must survive a tab switch.

The pre-multitab Intruder had one set of Threads/Delay/Turbo inputs and one set
of tooltips, all written once from ``on_mount``. Both assumptions broke when
the screen became tabbed, and both broke silently:

* ``_sync_toolbar_from_tab`` pushes a tab's threads/delay/turbo *into* the
  toolbar on activation, but nothing ever pulled them back out. Type 77
  threads, switch tabs, come back — the field reads 10 again. The dispatch
  path (``action_start_attack``) reads the widget, so the value you see *is*
  the value used for the next attack; it just silently reverted first.
* ``_setup_tooltips`` addressed Start/Stop as ``btn-start-<tab_id>`` and the
  per-tab buttons the same way, from ``on_mount``. ``compose`` builds empty
  ``TabPane``s and the bodies mount later, so *none* of those ids existed yet;
  every lookup raised ``NoMatches`` into a swallowed ``except Exception``.
  Start/Stop also have no tab suffix at all — they live in the global toolbar.

The attack-type button had a third variant of the same bug: its label and
description are written by whoever changes the mode (menu, DB load, auto-mark),
and each writer updated one widget or the other. Switching to a tab that was
loaded with ``battering_ram`` showed "Sniper ▼" with the sniper description
until something else repainted it.

Reading the toolbar back into a tab has its own trap, and the first version of
this fix fell into it: a batch restore from the DB creates every tab up front,
so only the last one is ever painted into the toolbar, and saving on
``TabDeactivated`` without checking *whose* values the toolbar holds stamps one
tab's numbers onto the rest. ``test_a_batch_restore_keeps_the_values_that_came
_from_the_db`` is the guard for that.

These tests drive the real widgets on a mounted screen, so a regression shows
up as the user would see it: as a value that quietly went back to its default.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import ContentSwitcher, Input

from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.widgets.toolbar_button import ToolbarButton


class _App(App):
    """Minimal host: the screen only needs ``show_context_menu`` to open menus."""

    _menu: dict[str, object] = {}

    def compose(self) -> ComposeResult:
        with ContentSwitcher():
            yield IntruderScreen()

    def show_context_menu(self, items, x, y, callback=None) -> None:
        """Capture the menu instead of opening it (the real one is in PentoolApp)."""
        type(self)._menu = {"items": list(items), "callback": callback}


async def _settle(pilot, cycles: int = 8) -> None:
    """Let the tab's staged mount finish (add_pane → TabCreated → body)."""
    for _ in range(cycles):
        await pilot.pause()


async def _mounted(pilot):
    await _settle(pilot)
    screen = pilot.app.query_one(IntruderScreen)
    return screen, screen._tc_panel


class TestToolbarValuesSurviveTabSwitch:
    """Threads/Delay/Turbo belong to a tab, not to the global toolbar."""

    async def test_threads_typed_on_one_tab_come_back_after_switching(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            first = panel.active_tab_id

            screen.query_one("#intruder-threads", Input).value = "77"
            await _settle(pilot)

            panel.action_new_tab()
            await _settle(pilot)
            second = panel.active_tab_id

            panel.switch_to(first)
            await _settle(pilot)
            assert screen.query_one("#intruder-threads", Input).value == "77", (
                "threads typed on the first tab were lost: the toolbar was pushed "
                "into the new tab on activation but never read back out of the tab "
                "being left behind"
            )

            panel.switch_to(second)
            await _settle(pilot)
            assert screen.query_one("#intruder-threads", Input).value == "10", (
                "the second tab must keep its own thread count, not inherit 77"
            )

    async def test_delay_and_turbo_travel_with_their_tab_too(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            first = panel.active_tab_id

            screen.query_one("#intruder-delay", Input).value = "250"
            await _settle(pilot)

            panel.action_new_tab()
            await _settle(pilot)
            panel.switch_to(first)
            await _settle(pilot)

            assert screen.query_one("#intruder-delay", Input).value == "250", (
                "delay typed on the first tab was lost on the round trip"
            )

    async def test_an_emptied_field_does_not_become_zero(self) -> None:
        """An empty input means "default", not "no threads".

        ``action_start_attack`` reads the widget and falls back to 10 when it
        is blank. Saving the blank as ``0`` would make the tab claim "0
        threads" and the revert-to-default behaviour would be lost.
        """
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            first = panel.active_tab_id
            threads = screen.query_one("#intruder-threads", Input)

            threads.value = "42"
            panel.action_new_tab()
            await _settle(pilot)
            panel.switch_to(first)
            await _settle(pilot)
            assert screen.query_one("#intruder-threads", Input).value == "42", (
                "precondition: 42 must have been committed to the tab"
            )

            screen.query_one("#intruder-threads", Input).value = ""
            panel.action_new_tab()
            await _settle(pilot)
            panel.switch_to(first)
            await _settle(pilot)

            assert screen.query_one("#intruder-threads", Input).value == "42", (
                "clearing the field erased the tab's thread count instead of leaving the last real value in place"
            )

    async def test_a_batch_restore_keeps_the_values_that_came_from_the_db(self) -> None:
        """Restoring N tabs must not write the active tab's values into all of them.

        ``_do_load_tabs_from_db`` creates tabs back to back; only the last one
        is ever painted into the toolbar by ``_sync_toolbar_from_tab``. A save
        on deactivation that does not check *whose* values the toolbar is
        showing would stamp those values onto every tab it leaves — turning a
        restored "55 threads" into the default 10 the moment the user switches.
        """
        from pentool.tui.screens.intruder.screen import _IntruderTabState

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            first = _IntruderTabState(tab_id="", tab_uid="uid-a", name="A", thread_count=55, delay_ms=300)
            second = _IntruderTabState(tab_id="", tab_uid="uid-b", name="B", thread_count=7, delay_ms=0)

            panel.action_new_tab(state=first)
            panel.action_new_tab(state=second)
            await _settle(pilot)

            assert panel.get_state(first.tab_id).thread_count == 55, (
                "the restored thread count of a non-active tab was overwritten "
                "by the values the toolbar had from its neighbour"
            )
            assert panel.get_state(second.tab_id).thread_count == 7

            panel.switch_to(first.tab_id)
            await _settle(pilot)
            assert screen.query_one("#intruder-threads", Input).value == "55"
            assert screen.query_one("#intruder-delay", Input).value == "300"
            assert panel.get_state(second.tab_id).thread_count == 7, (
                "leaving the second tab stamped the first tab's values onto it"
            )


class TestTooltipsReachTheirButtons:
    """Every id in the tooltip tables must exist when the tooltip is applied."""

    async def test_global_start_and_stop_are_not_addressed_with_a_tab_suffix(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            tab_id = panel.active_tab_id

            # StartStopWidget lives in compose(), so its ids carry no suffix.
            assert not len(screen.query(f"#btn-start-{tab_id}")), (
                "btn-start took a tab suffix — the tooltip table would miss it again"
            )
            start = screen.query_one("#btn-start", ToolbarButton)
            stop = screen.query_one("#btn-stop", ToolbarButton)
            assert start.tooltip, "Start/Pause has no tooltip"
            assert stop.tooltip, "Stop has no tooltip"

    async def test_first_tab_gets_its_tooltips(self) -> None:
        """Applied after the body mounts, not from on_mount where it is empty."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            tab_id = panel.active_tab_id

            for suffix in (
                "btn-add-marker",
                "btn-clear-markers",
                "btn-payload-add",
                "btn-payload-load",
            ):
                button = screen.query_one(f"#{suffix}-{tab_id}", ToolbarButton)
                assert button.tooltip, f"{suffix} lost its tooltip on the first tab"

    async def test_every_new_tab_gets_its_tooltips(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            panel.action_new_tab()
            await _settle(pilot)
            tab_id = panel.active_tab_id

            button = screen.query_one(f"#btn-add-marker-{tab_id}", ToolbarButton)
            assert button.tooltip, "a tab created after mount has no tooltips"


class TestAttackTypeShowsTheTabsOwnMode:
    """Label and description are two widgets for one piece of state."""

    async def test_switching_to_a_tab_shows_its_mode_not_the_last_painted_one(self) -> None:
        from pentool.api.intruder_api import AttackType

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            first = panel.active_tab_id

            panel.action_new_tab()
            await _settle(pilot)

            panel.get_state(first).attack_type = AttackType.PITCHFORK
            panel.switch_to(first)
            await _settle(pilot)

            label = screen.query_one(f"#btn-attack-type-{first}", ToolbarButton).label
            desc = str(screen.query_one(f"#attack-type-desc-{first}").render())
            assert "Pitchfork" in label, f"the tab shows another mode's label: {label!r}"
            assert "zip" in desc, f"the description lags behind the label: {desc!r}"

    async def test_the_mode_menu_updates_label_and_description_together(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, panel = await _mounted(pilot)
            tab_id = panel.active_tab_id

            button = screen.query_one(f"#btn-attack-type-{tab_id}", ToolbarButton)
            screen._open_attack_type_menu(button)
            callback = _App._menu.get("callback")
            assert callable(callback), "the attack-type menu never opened"
            callback("cluster_bomb")
            await _settle(pilot)

            label = screen.query_one(f"#btn-attack-type-{tab_id}", ToolbarButton).label
            desc = str(screen.query_one(f"#attack-type-desc-{tab_id}").render())
            assert "Cluster Bomb" in label, f"label not updated: {label!r}"
            assert "Cartesian" in desc, f"description not updated with the label: {desc!r}"
            assert not label.startswith("⚡"), (
                "the DB-load path used to prefix the label with ⚡ while every other "
                f"writer did not — the two spellings must stay one: {label!r}"
            )
