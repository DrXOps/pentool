"""Every button Intruder dispatches must exist — and every button must dispatch.

The bug this guards against already happened. Commit cb11bfd ("restore
pre-multitab content layout") rewrote the global ``Toolbar(...)`` and dropped
two entries while leaving their handlers in ``_on_toolbar_pressed``:
"Clear results" and "Export CSV" stayed in the dispatch dict for five weeks
with no widget to press. Nothing failed — the dispatch table is only read when
a button is pressed, and there was no button.

The old test missed it because it asserted on a ``DOMQuery``:

    btn_clear = pane.query(f"#btn-clear-results-{tid}")
    assert btn_clear is not None        # DOMQuery is never None

``query`` returns a lazy query object, so the assertion held for an id that
did not exist. These tests use ``query_one``/``len()``, which fail loudly.

The dispatch keys are read from the source rather than retyped here, so adding
a button to one place and forgetting the other stays a red test.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import ContentSwitcher

from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.widgets.toolbar_button import ToolbarButton

_SCREEN = Path(__file__).resolve().parents[3] / "pentool" / "tui" / "screens" / "intruder" / "screen.py"

#: Buttons handled inline in ``_on_toolbar_pressed`` before the dispatch dict —
#: they are global (tab-independent) and created literally in ``compose``.
_GLOBAL_IDS = {"btn-new-tab", "btn-close-tab", "btn-start", "btn-stop", "btn-pause"}


def _dispatch_keys() -> set[str]:
    """Base ids from the ``dispatch = {...}`` dict in ``_on_toolbar_pressed``."""
    tree = ast.parse(_SCREEN.read_text(encoding="utf-8"))
    handler = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_on_toolbar_pressed"
    )
    for node in ast.walk(handler):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if keys:
                return keys
    raise AssertionError("dispatch dict not found in _on_toolbar_pressed")


class _App(App):
    def compose(self) -> ComposeResult:
        with ContentSwitcher():
            yield IntruderScreen()


async def _mounted(pilot):
    await pilot.pause()
    screen = pilot.app.query_one(IntruderScreen)
    panel = screen._tc_panel
    tid = panel.active_tab_id
    return screen, tid, panel.tabs_content.get_pane(tid)


class TestDispatchTableHasWidgets:
    async def test_every_per_tab_dispatch_key_has_a_button(self) -> None:
        """A dispatch key exists either per-tab (suffixed) or globally."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            screen, tid, pane = await _mounted(pilot)
            missing = [
                key
                for key in _dispatch_keys()
                if not len(pane.query(f"#{key}-{tid}")) and not len(screen.query(f"#{key}"))
            ]
            assert not missing, (
                "these buttons are in the dispatch table but no widget carries their id — "
                f"the handler can never run: {sorted(missing)}"
            )

    async def test_the_two_buttons_cb11bfd_dropped_are_back(self) -> None:
        """The exact regression: handlers without widgets for five weeks."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = pilot.app.query_one(IntruderScreen)
            for btn_id in ("btn-clear-results", "btn-export-csv"):
                found = screen.query(f"#{btn_id}")
                assert len(found) == 1, f"#{btn_id} is dispatched but not in the global toolbar"
                assert isinstance(found.first(), ToolbarButton)

    async def test_navigation_buttons_exist_and_are_unique(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = pilot.app.query_one(IntruderScreen)
            for btn_id in sorted(_GLOBAL_IDS - {"btn-start", "btn-stop", "btn-pause"}):
                assert len(screen.query(f"#{btn_id}")) == 1, f"#{btn_id} missing or duplicated"


class TestLayoutPiecesSurviveTheTabPort:
    """The pre-multitab layout had two drag handles; the port kept only one."""

    async def test_positions_and_payloads_can_be_resized(self) -> None:
        from pentool.tui.widgets.resize_handle import ResizeHandle

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            _, tid, pane = await _mounted(pilot)
            handles = list(pane.query(ResizeHandle))
            assert len(handles) == 3, (
                f"expected Positions|Payloads, top|results and request|response handles, got {len(handles)}"
            )
            # The horizontal one is the Positions|Payloads split.
            assert any(not h.has_class("-vertical") for h in handles), "the Positions|Payloads handle is gone"

    async def test_payload_counter_sits_above_the_list(self) -> None:
        """Pre-multitab order; below the list it scrolls out of sight mid-load."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            _, tid, pane = await _mounted(pilot)
            panel = pane.query_one(f"#payloads-panel-{tid}")
            order = [child.id for child in panel.children]
            counter = f"payload-count-label-{tid}"
            listing = f"payload-list-{tid}"
            assert order.index(counter) < order.index(listing), f"payload counter must be above the list, got {order}"


class TestRestoredTabShowsItsData:
    """A tab restored from the DB must be painted with the data it came with.

    The port left three holes here, and all of them were silent:

    * ``TabbedContentPanel.action_new_tab(state=...)`` never assigned the new
      ``tab_id`` to the caller's state, so the body mounted under one id while
      every lookup used another (``""``), and the pane stayed an empty
      placeholder forever;
    * the attack-type button and its description were literals ("Sniper ▼"),
      so a restored ``battering_ram`` tab lied about its own mode;
    * the content load was queued in the same ``call_after_refresh`` batch as
      the mount, so ``_refresh_payload_list`` ran before the ``ListView``
      existed, swallowed the ``NoMatches`` and left the list empty until the
      user clicked something.

    One more hole showed up while testing the fix: the batch restore in
    ``_do_load_tabs_from_db`` creates every tab up front, so only the last one
    is active when the bodies finish mounting. ``TabCreated`` alone can never
    paint the others — ``TabActivated`` has to do it.
    """

    async def test_a_tab_created_with_payloads_shows_them_immediately(self) -> None:
        from pentool.api.intruder_api import CharPayloadSource

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = pilot.app.query_one(IntruderScreen)
            panel = screen._tc_panel

            state = _restored_state()
            state.payload_sources = [CharPayloadSource("abc", 1, 3)]
            panel.action_new_tab(state=state)
            await _settle(pilot, lambda: _row_count(screen, state.tab_id) > 0)

            listing = screen.query_one(f"#payload-list-{state.tab_id}")
            assert len(listing.children) == 39, (
                f"restored tab painted {len(listing.children)} payload rows, expected 39"
            )
            counter = screen.query_one(f"#payload-count-label-{state.tab_id}")
            assert "39 value(s)" in str(counter.render())

    async def test_every_tab_of_a_batch_restore_shows_its_own_payloads(self) -> None:
        """The DB restore path creates tabs back to back, and the last wins.

        ``_do_load_tabs_from_db`` calls ``action_new_tab(state=…)`` in a loop,
        and each call makes its tab active — so a body that finishes mounting
        later finds a *different* tab active. Loading straight from there
        would either paint one tab's payloads into another or hit
        ``NoMatches``; the data of a non-active tab therefore arrives on
        ``TabActivated``, when the user opens it.
        """
        from pentool.api.intruder_api import CharPayloadSource

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = pilot.app.query_one(IntruderScreen)
            panel = screen._tc_panel

            first = _restored_state()
            first.payload_sources = [CharPayloadSource("ab", 1, 1)]
            second = _restored_state()
            second.tab_uid = "restored-uid-2"
            second.payload_sources = [CharPayloadSource("abc", 1, 3)]
            panel.action_new_tab(state=first)
            panel.action_new_tab(state=second)

            await _settle(pilot, lambda: _row_count(screen, second.tab_id) > 0)
            assert _row_count(screen, second.tab_id) == 39, "the last tab of the batch is active and must be painted"

            panel.switch_to(first.tab_id)
            await _settle(pilot, lambda: _row_count(screen, first.tab_id) > 0)
            assert _row_count(screen, first.tab_id) == 2, (
                "the first tab of the batch must load its own 2 payloads when opened, "
                f"got {_row_count(screen, first.tab_id)}"
            )

    async def test_the_attack_type_comes_from_the_state(self) -> None:
        from pentool.api.intruder_api import AttackType

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = pilot.app.query_one(IntruderScreen)
            state = _restored_state()
            state.attack_type = AttackType.BATTERING_RAM
            screen._tc_panel.action_new_tab(state=state)
            await _settle(pilot, lambda: len(screen.query(f"#btn-attack-type-{state.tab_id}")) == 1)

            button = screen.query_one(f"#btn-attack-type-{state.tab_id}", ToolbarButton)
            assert "Battering Ram" in button.label, f"the button still advertises the default mode: {button.label}"
            desc = screen.query_one(f"#attack-type-desc-{state.tab_id}")
            assert "One payload set" in str(desc.render())


def _restored_state():
    """A state shaped like one out of the DB: no tab_id, a persisted uid."""
    from pentool.tui.screens.intruder.screen import _IntruderTabState

    return _IntruderTabState(
        tab_id="",
        tab_uid="restored-uid",
        name="Restored",
        target_url="http://x/",
        template_text="POST / HTTP/1.1\nHost: a\n\nx=§1§",
    )


def _row_count(screen, tab_id: str) -> int:
    """Rows in the tab's payload list — 0 while the list does not exist yet."""
    found = screen.query(f"#payload-list-{tab_id}")
    return len(found.first().children) if found else 0


async def _settle(pilot, ready, *, cycles: int = 5) -> None:
    """Let the refresh batches run until ``ready()`` is true, or give up.

    A tab is built across several refresh batches by design: ``add_pane``
    first, then ``TabCreated``, then ``_mount_tab_body``, which awaits the
    mount and only then loads the tab's data. One ``pause()`` covers one
    batch, so a single pause makes the test a race. This waits for the
    condition with a hard bound — if the content never arrives, the assert
    after it fails with the real symptom instead of a timeout.
    """
    for _ in range(cycles):
        if ready():
            return
        await pilot.pause()
    # One extra pause: ``ready()`` may have become true during the last one.
    await pilot.pause()


def test_query_never_returns_none_is_not_an_assertion() -> None:
    """Pin the reason the old test was toothless, so nobody copies it back."""
    source = Path(__file__).resolve().parent.joinpath("test_intruder_tabs.py").read_text(encoding="utf-8")
    toothless = re.findall(r"= pane\.query\(.*\)\s*\n\s*assert \w+ is not None", source)
    assert not toothless, (
        "pane.query() returns a DOMQuery, which is never None — assert on query_one() "
        "or len(query()) instead; these lines assert nothing:\n  " + "\n  ".join(toothless)
    )
