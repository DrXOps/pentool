"""Resizing the terminal changes the layout, never the user's preference (F-027).

The old ``on_resize`` was the only responsive behaviour in the TUI and it was
the wrong kind: below 80 columns it called ``ProxyScreen.action_toggle_inspector()``,
which flips ``_inspector_visible``. Widening the terminal again did not bring
the inspector back, because nothing set the flag back — a layout reaction had
silently rewritten a user choice (ADR-7).

Now ``on_resize`` only toggles the ``narrow`` class on the Screen and CSS
decides what a narrow terminal hides. These tests run the real app and resize
the real terminal twice, so they pin both halves: the class follows the width,
and the preference outlives the round trip.
"""

from __future__ import annotations

import inspect

from textual.screen import ModalScreen
from textual.widgets import ContentSwitcher

from pentool.tui.app import PentoolApp
from pentool.tui.screens.proxy.screen import ProxyScreen


async def _open_proxy(pilot) -> ProxyScreen:
    await pilot.pause()
    await pilot.press("P")
    await pilot.pause()
    await pilot.pause()
    return pilot.app.query_one(ProxyScreen)


def _app() -> PentoolApp:
    app = PentoolApp()
    app._skip_project_guard = True
    return app


class TestNarrowLayout:
    async def test_narrow_class_follows_width(self) -> None:
        app = _app()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            base = app.screen_stack[0]
            assert base.has_class("narrow") is False

            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            assert base.has_class("narrow") is True, "narrow class did not follow the width"

            await pilot.resize_terminal(120, 30)
            await pilot.pause()
            assert base.has_class("narrow") is False, "narrow class stuck after widening"

    async def test_an_open_dialog_does_not_steal_the_class(self) -> None:
        """The class belongs to the base screen, not to whatever is on top.

        Putting it on ``self.screen`` would paint it onto a modal: closing the
        dialog would take the narrow flag with it, and the module underneath
        would keep the wide layout in a 60-column terminal.
        """
        app = _app()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            base = app.screen_stack[0]
            app.push_screen(ModalScreen())
            await pilot.pause()
            assert app.screen is not base

            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            assert base.has_class("narrow") is True, "the class went to the modal, not the base screen"
            app.pop_screen()
            await pilot.pause()
            assert app.screen.has_class("narrow") is True, "the base screen lost the narrow class on pop"

    async def test_user_preference_survives_a_resize_round_trip(self) -> None:
        """The bug F-027 described: the inspector never came back on widening."""
        app = _app()
        async with app.run_test(size=(120, 30)) as pilot:
            screen = await _open_proxy(pilot)
            screen.action_toggle_inspector()
            await pilot.pause()
            assert screen._inspector_visible is True
            panel = screen.query_one("#inspector-panel")
            assert panel.styles.display == "block"

            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            assert screen._inspector_visible is True, (
                "resizing must not flip the user's preference — that is the F-027 bug"
            )
            assert panel.styles.display == "none", "a narrow terminal should hide the inspector"

            await pilot.resize_terminal(120, 30)
            await pilot.pause()
            assert panel.styles.display == "block", "the inspector did not come back after widening"

    async def test_narrow_terminal_keeps_the_proxy_screen_usable(self) -> None:
        app = _app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _open_proxy(pilot)
            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            assert pilot.app.query_one(ContentSwitcher).current == "screen-proxy"


class TestNoStateMutationOnResize:
    def test_on_resize_calls_no_screen_actions(self) -> None:
        """Guard at the source: parse the handler, ignore its docstring.

        The docstring *names* the old bug (``action_toggle_inspector``), so a
        substring check on the source would fail on correct code — walk the
        AST instead and look at what is actually called.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parents[3] / "pentool" / "tui" / "app.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        handler = next(
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "on_resize"
        )
        called = {
            node.func.attr
            for node in ast.walk(handler)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        forbidden = {"action_toggle_inspector", "action_hide_detail"}
        assert not (called & forbidden), (
            f"on_resize calls {sorted(called & forbidden)} — a layout reaction must not "
            "overwrite a user preference (F-027/ADR-7)"
        )
        touched = {
            node.attr
            for node in ast.walk(handler)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
        }
        assert "_inspector_visible" not in touched
        assert "set_class" in called

    def test_breakpoint_is_named_and_used_once(self) -> None:
        assert PentoolApp.NARROW_BREAKPOINT == 80
        from pentool.tui import app as app_module

        src = inspect.getsource(app_module)
        assert "< 80" not in src, "hard-coded 80 left behind — use NARROW_BREAKPOINT"
