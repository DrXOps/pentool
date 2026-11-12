"""The Hotkeys settings tab must show the real table and must not pretend to save.

Two defects are pinned here, both F-035:

* ``HotkeySettingsScreen`` used to render a hand-typed ``DEFAULT_HOTKEYS`` dict
  that disagreed with ``defaults.py`` — ``send_to_intruder: ctrl+i`` and
  ``repeater_send: ctrl+space`` are keys no terminal produces (F-052). A second
  copy of a table is a copy that drifts.
* its Save button called a method whose whole body was
  ``self.app.notify("Hotkeys saved (restart required for some bindings)")``.
  Nothing was persisted and nothing was rebound — the user was told a setting
  had been applied when there was no setting.

The tab is now a read-only view of the registry. These tests fail if either
behaviour comes back.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Input

from pentool.tui.hotkeys import registry
from pentool.tui.screens.settings import hotkeys as hotkeys_module
from pentool.tui.screens.settings.hotkeys import HotkeySettingsScreen


class _App(App):
    def compose(self) -> ComposeResult:
        yield HotkeySettingsScreen()


async def _rows() -> list[tuple]:
    """Rows of the table, read from a mounted screen."""
    app = _App()
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        table = pilot.app.query_one("#hotkey-table", DataTable)
        return [tuple(table.get_row_at(index)) for index in range(table.row_count)]


class TestTheTableIsTheRegistry:
    async def test_every_registered_entry_has_a_row(self) -> None:
        """The table is derived from the registry, not typed beside it.

        A group registered in ``defaults.py`` and missing from the screen is
        exactly the drift this test exists to catch, so the expected set comes
        from the registry — the screen may not keep its own list of groups.
        """
        rows = await _rows()
        shown = {(row[0], row[1], row[2]) for row in rows}
        expected = {
            (group, entry.keys, entry.action) for group in registry.groups() for entry in registry.get_entries(group)
        }
        assert shown == expected

    async def test_the_table_is_not_empty(self) -> None:
        """Guard the guard: an empty registry would make the test above vacuous."""
        assert await _rows()


class TestTheScreenDoesNotClaimToSave:
    def test_no_save_button(self) -> None:
        assert not _buttons_in_compose()

    def test_no_editable_input(self) -> None:
        assert not _inputs_in_compose()

    def test_the_module_has_no_default_hotkey_table(self) -> None:
        """A second copy of the table is what drifted; it must not come back."""
        assert not hasattr(hotkeys_module, "DEFAULT_HOTKEYS")

    def test_the_module_does_not_touch_the_notify_api(self) -> None:
        """Nothing here may tell the user something was saved.

        AST, not a substring search: the docstring above mentions the old
        ``notify("Hotkeys saved …")`` call on purpose, and prose is not a call.
        """
        assert not _attribute_calls("notify"), "a settings screen that saves nothing must not say it saved"
        assert not _attribute_calls("rebind"), "rebind is not implemented; a call to it would fail at runtime"


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(hotkeys_module))


def _attribute_calls(name: str) -> list[int]:
    """Line numbers of ``….name(…)`` calls anywhere in the module."""
    return [
        node.lineno
        for node in ast.walk(_module_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name
    ]


def _widgets_in_compose(widget_type: type) -> list[str]:
    """Class names of *widget_type* yielded by ``HotkeySettingsScreen.compose``.

    AST rather than a live mount: the point is that the widget is not even
    constructed, and a ``compose`` that yields it conditionally would slip past
    a query on a mounted screen.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(HotkeySettingsScreen.compose)))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == widget_type.__name__:
                names.append(node.func.id)
    return names


def _buttons_in_compose() -> list[str]:
    return _widgets_in_compose(Button)


def _inputs_in_compose() -> list[str]:
    return _widgets_in_compose(Input)
