"""Unit tests for pentool/tui/widgets/context_menu.py.

Tests that need no live Textual app — bypass property access by
testing logic directly through mock-patched instances.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from textual.events import Key
from textual.widgets import Static

from pentool.tui.widgets.context_menu import ContextMenu


@pytest.fixture
def menu():
    """Build a bare ContextMenu with mocked Widget.__init__."""
    with patch("textual.widget.Widget.__init__", return_value=None):
        m = ContextMenu.__new__(ContextMenu)
    m._items = [("a", "A"), ("b", "B")]
    m._callback = None
    m._action_items = []
    m._focused_idx = 0
    m._menu_x = 0
    m._menu_y = 0
    m.styles = MagicMock()
    return m


class TestInit:
    def test_stores_items(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            m = ContextMenu.__new__(ContextMenu)
        m._items = [("x", "X")]
        m._callback = None
        m._action_items = []
        m._focused_idx = 0
        m._menu_x = 0
        m._menu_y = 0
        m.styles = MagicMock()
        assert m._items == [("x", "X")]

    def test_can_focus(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            m = ContextMenu.__new__(ContextMenu)
        assert m.can_focus is True


class TestCompose:
    def test_separator(self, menu: ContextMenu) -> None:
        menu._items = [("a", "A"), ("-", ""), ("b", "B")]
        results = list(menu.compose())
        assert len(results) == 3
        assert isinstance(results[1], Static)
        assert "ctx-sep" in results[1].classes

    def test_all_items_static(self, menu: ContextMenu) -> None:
        results = list(menu.compose())
        assert all(isinstance(r, Static) for r in results)
        assert all("ctx-item" in r.classes for r in results)

    def test_populates_action_items(self, menu: ContextMenu) -> None:
        list(menu.compose())
        assert [a for a, _ in menu._action_items] == ["a", "b"]

    def test_item_stores_action(self, menu: ContextMenu) -> None:
        results = list(menu.compose())
        assert results[0]._ctx_action == "a"  # type: ignore[attr-defined]


class TestHighlight:
    def test_adds_class(self, menu: ContextMenu) -> None:
        w = Static("A")
        menu._action_items = [("a", w)]
        menu._highlight(0)
        assert w.has_class("-focused")

    def test_removes_old(self, menu: ContextMenu) -> None:
        w0, w1 = Static("A"), Static("B")
        menu._action_items = [("a", w0), ("b", w1)]
        w0.add_class("-focused")
        menu._highlight(1)
        assert not w0.has_class("-focused")
        assert w1.has_class("-focused")


class TestSelect:
    pass


class TestDismiss:
    def test_dismiss_runs_remove(self, menu: ContextMenu) -> None:
        removed = []
        menu.remove = lambda: removed.append(True)  # type: ignore[method-assign]
        menu._dismiss()
        assert removed == [True]


class TestFixPosition:
    def test_no_crash_on_bad_size(self, menu: ContextMenu) -> None:
        menu._fix_position()


class TestKeyNavigation:
    """Test _highlight / _select calls triggered by on_key."""

    @pytest.fixture
    def nav_menu(self, menu: ContextMenu):
        menu._action_items = [("a", None), ("b", None)]  # type: ignore[list-item]
        return menu

    def test_up_calls_highlight(self, nav_menu: ContextMenu) -> None:
        h = []
        nav_menu._highlight = lambda i: h.append(i)  # type: ignore[method-assign]
        nav_menu._focused_idx = 1
        nav_menu.on_key(Key(key="up", character=""))
        assert h == [0]

    def test_up_wraps(self, nav_menu: ContextMenu) -> None:
        h = []
        nav_menu._highlight = lambda i: h.append(i)  # type: ignore[method-assign]
        nav_menu._focused_idx = 0
        nav_menu.on_key(Key(key="up", character=""))
        assert h == [1]

    def test_down_calls_highlight(self, nav_menu: ContextMenu) -> None:
        h = []
        nav_menu._highlight = lambda i: h.append(i)  # type: ignore[method-assign]
        nav_menu._focused_idx = 0
        nav_menu.on_key(Key(key="down", character=""))
        assert h == [1]

    def test_down_wraps(self, nav_menu: ContextMenu) -> None:
        h = []
        nav_menu._highlight = lambda i: h.append(i)  # type: ignore[method-assign]
        nav_menu._focused_idx = 1
        nav_menu.on_key(Key(key="down", character=""))
        assert h == [0]

    def test_k_maps_up(self, nav_menu: ContextMenu) -> None:
        h = []
        nav_menu._highlight = lambda i: h.append(i)  # type: ignore[method-assign]
        nav_menu._focused_idx = 1
        nav_menu.on_key(Key(key="k", character="k"))
        assert h == [0]

    def test_j_maps_down(self, nav_menu: ContextMenu) -> None:
        h = []
        nav_menu._highlight = lambda i: h.append(i)  # type: ignore[method-assign]
        nav_menu._focused_idx = 0
        nav_menu.on_key(Key(key="j", character="j"))
        assert h == [1]

    def test_escape_calls_dismiss(self, nav_menu: ContextMenu) -> None:
        nav_menu._dismiss = Mock()  # type: ignore[method-assign]
        nav_menu.on_key(Key(key="escape", character=""))
        nav_menu._dismiss.assert_called_once()

    def test_enter_selects_focused(self, nav_menu: ContextMenu) -> None:
        selected = []
        nav_menu._select = lambda a: selected.append(a)  # type: ignore[method-assign]
        nav_menu._focused_idx = 1
        nav_menu.on_key(Key(key="enter", character=""))
        assert selected == ["b"]

    def test_space_selects_focused(self, nav_menu: ContextMenu) -> None:
        selected = []
        nav_menu._select = lambda a: selected.append(a)  # type: ignore[method-assign]
        nav_menu._focused_idx = 0
        nav_menu.on_key(Key(key="space", character=" "))
        assert selected == ["a"]


class TestMessage:
    def test_item_selected_has_action(self) -> None:
        msg = ContextMenu.ItemSelected("delete")
        assert msg.action == "delete"