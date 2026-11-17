"""ExtensionsScreen — the one screen with no tests at all (F-040).

``screens/extensions/`` is a placeholder (25 lines): it says plugins will be
loadable and renders a box. That is exactly why it needs a smoke test — a
placeholder is never exercised by hand, so a broken ``compose`` or a stylesheet
that no longer parses would stay broken until someone opened the tab.

The test is deliberately about observable behaviour (the tree that mounts, the
CSS that applies, the id the app switches to), not about the text, which is
placeholder copy that will change.
"""

from __future__ import annotations

import asyncio

from textual.app import App

from pentool.tui.screen_registry import SCREEN_MAP
from pentool.tui.screens.extensions.screen import ExtensionsScreen


class _Host(App[None]):
    def compose(self):
        yield ExtensionsScreen(id="screen-extensions")


def _mounted() -> dict:
    async def _run() -> dict:
        app = _Host()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.query_one("#screen-extensions", ExtensionsScreen)
            box = screen.query_one("#box")
            return {
                "box_border": box.styles.border_top[0],
                "box_padding": (box.styles.padding.top, box.styles.padding.left),
                "title_styled": screen.query_one(".title").styles.text_style.bold,
                "statics": len(list(screen.query(".title"))) + len(list(screen.query(".desc"))),
                "labels": sorted({str(s.render()) for s in screen.query("Static")}),
            }

    return asyncio.run(_run())


def test_screen_composes_inside_its_box() -> None:
    state = _mounted()
    assert state["statics"] == 2, "title + description must both render"
    assert any("Extensions" in label for label in state["labels"]), "title text missing"


def test_stylesheet_actually_applies() -> None:
    """Assert the *declarations*, not the size.

    ``#box`` is capped by the terminal width and ``Static`` fills anyway, so a
    size assertion passes even when the rule that gives it that size is
    deleted — verified by mutating the selector and watching a size-only test
    stay green. Border and padding only come from ``screen.tcss``.
    """
    state = _mounted()
    assert state["box_border"] == "double", "#box rule did not apply (screen.tcss selector vs DOM)"
    assert state["box_padding"] == (2, 4), "#box padding did not apply"
    assert state["title_styled"] is True, ".title rule did not apply"


def test_screen_is_registered_under_its_module_id() -> None:
    assert SCREEN_MAP["extensions"] is ExtensionsScreen, (
        "app switches to '#screen-' + module_id; the id and the registry entry must stay in sync"
    )
