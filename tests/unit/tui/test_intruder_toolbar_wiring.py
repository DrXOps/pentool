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
            assert (
                len(handles) == 3
            ), f"expected Positions|Payloads, top|results and request|response handles, got {len(handles)}"
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


def test_query_never_returns_none_is_not_an_assertion() -> None:
    """Pin the reason the old test was toothless, so nobody copies it back."""
    source = Path(__file__).resolve().parent.joinpath("test_intruder_tabs.py").read_text(encoding="utf-8")
    toothless = re.findall(r"= pane\.query\(.*\)\s*\n\s*assert \w+ is not None", source)
    assert not toothless, (
        "pane.query() returns a DOMQuery, which is never None — assert on query_one() "
        "or len(query()) instead; these lines assert nothing:\n  " + "\n  ".join(toothless)
    )
