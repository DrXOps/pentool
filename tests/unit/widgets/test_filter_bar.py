"""Unit tests for pentool/tui/widgets/filter_bar.py."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from pentool.tui.widgets.filter_bar import (
    _COLOR_DOTS,
    _METHODS,
    ColorFilterCycler,
    MethodCycler,
    ScopeToggle,
)


def _make_cycler(cls) -> object:
    """Build bare widget without live app."""
    with patch("textual.widget.Widget.__init__", return_value=None):
        w = cls.__new__(cls)
    w._classes = set()
    w.styles = MagicMock()
    return w


class TestConstants:
    def test_methods(self) -> None:
        assert _METHODS[0] == "Any"
        assert "GET" in _METHODS
        assert "POST" in _METHODS

    def test_color_dots(self) -> None:
        assert len(_COLOR_DOTS) == 6
        for dot, color in _COLOR_DOTS:
            assert dot
            assert color


class TestMethodCycler:
    def test_initial_value_any(self) -> None:
        m = _make_cycler(MethodCycler)
        m._idx = 0
        assert m.value == "Any"

    def test_reset(self) -> None:
        m = _make_cycler(MethodCycler)
        m._idx = 3
        m.update = MagicMock()
        m.reset()
        assert m._idx == 0
        assert m.value == "Any"
        m.update.assert_called_once_with("Any ▼")

    def test_on_click_cycles(self) -> None:
        m = _make_cycler(MethodCycler)
        m._idx = 0
        m.update = MagicMock()
        m.post_message = MagicMock()
        m.on_click()
        assert m._idx == 1
        assert m.value == "GET"
        m.post_message.assert_called_once()
        msg = m.post_message.call_args[0][0]
        assert isinstance(msg, MethodCycler.Changed)
        assert msg.method == "GET"

    def test_on_click_wraps_after_last(self) -> None:
        m = _make_cycler(MethodCycler)
        m._idx = len(_METHODS) - 1
        m.update = MagicMock()
        m.post_message = MagicMock()
        m.on_click()
        assert m._idx == 0
        assert m.value == "Any"


class TestScopeToggle:
    def test_initial_inactive(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._active = False
        s._scope_empty = True
        assert s.active is False

    def test_set_scope_empty_adds_disabled(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._active = True
        s._scope_empty = False
        s.add_class = MagicMock()
        s.remove_class = MagicMock()
        s.update = MagicMock()
        s.set_scope_empty(True)
        s.add_class.assert_called_once_with("disabled")
        assert s.active is False
        s.remove_class.assert_called_once_with("-active")
        s.update.assert_called_once_with("★ Scope")

    def test_set_scope_empty_removes_class(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._active = False
        s._scope_empty = True
        s.add_class = MagicMock()
        s.remove_class = MagicMock()
        s.set_scope_empty(False)
        s.remove_class.assert_called_once_with("disabled")

    def test_on_click_ignored_when_scope_empty(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._active = False
        s._scope_empty = True
        s.post_message = MagicMock()
        s.on_click()
        s.post_message.assert_not_called()
        assert s._active is False

    def test_on_click_activates(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._scope_empty = False
        s._active = False
        s.add_class = MagicMock()
        s.remove_class = MagicMock()
        s.update = MagicMock()
        s.post_message = MagicMock()
        s.on_click()
        assert s._active is True
        s.add_class.assert_called_once_with("-active")
        msg = s.post_message.call_args[0][0]
        assert isinstance(msg, ScopeToggle.Toggled)
        assert msg.active is True

    def test_on_click_deactivates(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._scope_empty = False
        s._active = True
        s.add_class = MagicMock()
        s.remove_class = MagicMock()
        s.update = MagicMock()
        s.post_message = MagicMock()
        s.on_click()
        assert s._active is False

    def test_reset(self) -> None:
        s = _make_cycler(ScopeToggle)
        s._active = True
        s.remove_class = MagicMock()
        s.update = MagicMock()
        s.reset()
        assert s._active is False
        s.update.assert_called_with("★ Scope")


class TestColorFilterCycler:
    def test_initial_value_empty(self) -> None:
        c = _make_cycler(ColorFilterCycler)
        c._idx = 0
        assert c.value == ""

    def test_reset(self) -> None:
        c = _make_cycler(ColorFilterCycler)
        c._idx = 3
        c._update_label = MagicMock()
        c.reset()
        assert c._idx == 0
        assert c.value == ""

    def test_on_click_cycles(self) -> None:
        c = _make_cycler(ColorFilterCycler)
        c._idx = 0
        c._update_label = MagicMock()
        c.post_message = MagicMock()
        c.on_click()
        assert c._idx == 1
        assert c.value == _COLOR_DOTS[0][1]
        msg = c.post_message.call_args[0][0]
        assert isinstance(msg, ColorFilterCycler.Changed)

    def test_on_click_wraps(self) -> None:
        c = _make_cycler(ColorFilterCycler)
        c._idx = len(_COLOR_DOTS)  # last color
        c._update_label = MagicMock()
        c.post_message = MagicMock()
        c.on_click()
        assert c._idx == 0
        assert c.value == ""

    def test_update_label_any(self) -> None:
        c = _make_cycler(ColorFilterCycler)
        c._idx = 0
        c.update = MagicMock()
        c._update_label()
        c.update.assert_called_once_with("Any ▼")

    def test_update_label_color(self) -> None:
        c = _make_cycler(ColorFilterCycler)
        c._idx = 2
        c.update = MagicMock()
        c._update_label()
        dot = _COLOR_DOTS[1][0]
        c.update.assert_called_once_with(f"{dot} ▼")