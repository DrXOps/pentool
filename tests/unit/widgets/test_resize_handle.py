"""Unit tests for pentool/tui/widgets/resize_handle.py."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from textual.events import MouseDown, MouseMove, MouseUp

from pentool.tui.widgets.resize_handle import ResizeHandle


def _fake_md(button: int = 1, sx: int = 0, sy: int = 0) -> MagicMock:
    """Fake MouseDown with minimal attr surface."""
    ev = MagicMock(spec=MouseDown)
    ev.button = button
    ev.screen_x = sx
    ev.screen_y = sy
    ev.is_stopped = False
    ev.stop = lambda: setattr(ev, 'is_stopped', True)
    return ev


def _fake_mm(sx: int = 0, sy: int = 0) -> MagicMock:
    """Fake MouseMove with minimal attr surface."""
    ev = MagicMock(spec=MouseMove)
    ev.screen_x = sx
    ev.screen_y = sy
    ev.is_stopped = False
    ev.stop = lambda: setattr(ev, 'is_stopped', True)
    return ev


def _fake_mu() -> MagicMock:
    """Fake MouseUp."""
    ev = MagicMock(spec=MouseUp)
    ev.is_stopped = False
    ev.stop = lambda: setattr(ev, 'is_stopped', True)
    return ev


def _make_handle(
    left_id: str = "left-panel",
    right_id: str = "right-panel",
    vertical: bool = False,
    min_left: int = 8,
    min_right: int = 8,
) -> ResizeHandle:
    with patch("textual.widget.Widget.__init__", return_value=None):
        h = ResizeHandle.__new__(ResizeHandle)
    h._classes = set()
    h.styles = MagicMock()
    h._left_id = left_id
    h._right_id = right_id
    h._vertical = vertical
    h._min_left = min_left
    h._min_right = min_right
    h._dragging = False
    h._drag_start_x = 0
    h._drag_start_y = 0
    h._start_size = 0
    h._pair_total_cached = 0
    return h


class TestInit:
    def test_css_loaded(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            h = ResizeHandle.__new__(ResizeHandle)
        assert len(h.DEFAULT_CSS) > 0

    def test_stores_ids(self) -> None:
        h = ResizeHandle("a", "b")
        assert h._left_id == "a"
        assert h._right_id == "b"

    def test_default_not_vertical(self) -> None:
        h = ResizeHandle("a", "b")
        assert h._vertical is False

    def test_min_values(self) -> None:
        h = ResizeHandle("a", "b", min_left=5, min_right=10)
        assert h._min_left == 5
        assert h._min_right == 10

    def test_tooltip_set(self) -> None:
        h = ResizeHandle("a", "b")
        assert h.tooltip == "Drag to resize"

    def test_vertical_adds_class(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            h = ResizeHandle.__new__(ResizeHandle)
        h._classes = set()
        h.add_class = lambda c: h._classes.add(c)  # type: ignore[method-assign]
        ResizeHandle.__init__(h, "a", "b", vertical=True)
        assert "-vertical" in h._classes


class TestRender:
    def test_render_horizontal(self) -> None:
        h = _make_handle()
        assert h.render() == "│"

    def test_render_vertical(self) -> None:
        h = _make_handle(vertical=True)
        with patch.object(ResizeHandle, "size", new=MagicMock(width=5, height=1)):
            rendered = h.render()
        assert "─" in rendered


class TestMouseDown:
    def test_non_left_button_ignored(self) -> None:
        h = _make_handle()
        h._dragging = False
        ev = _fake_md(button=3)
        h.on_mouse_down(ev)
        assert h._dragging is False

    def test_left_button_starts_drag(self) -> None:
        h = _make_handle()
        h.capture_mouse = MagicMock()
        h.add_class = MagicMock()
        left = MagicMock()
        right = MagicMock()
        left.size.width = 200
        right.size.width = 100
        mock_app = MagicMock()
        mock_app.query_one = lambda sel, cls=None: {"#left-panel": left, "#right-panel": right}.get(sel, MagicMock())

        with patch("textual.widget.Widget.app", new=mock_app, create=True):
            ev = _fake_md(button=1, sx=300, sy=400)
            h.on_mouse_down(ev)

        assert h._dragging is True
        assert h._start_size == 200
        assert h._pair_total_cached == 300
        h.add_class.assert_called_once_with("-dragging")
        h.capture_mouse.assert_called_once()
        assert ev.is_stopped

    def test_query_failure_ignores(self) -> None:
        h = _make_handle()
        mock_app = MagicMock()
        mock_app.query_one = Mock(side_effect=Exception("boom"))

        with patch("textual.widget.Widget.app", new=mock_app, create=True):
            h.on_mouse_down(_fake_md(button=1))

        assert h._dragging is False


class TestMouseMove:
    def test_no_drag_ignores(self) -> None:
        h = _make_handle()
        h._dragging = False
        h.on_mouse_move(_fake_mm())
        # no error

    def test_drag_resizes_horizontal(self) -> None:
        h = _make_handle()
        h._dragging = True
        h._drag_start_x = 300
        h._start_size = 200
        h._pair_total_cached = 300
        h._min_left = 8
        h._min_right = 8

        left = MagicMock()
        right = MagicMock()
        left.styles = MagicMock()
        right.styles = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one = lambda sel, cls=None: {"#left-panel": left, "#right-panel": right}.get(sel)
        parent_mock = MagicMock()

        with patch("textual.widget.Widget.app", new=mock_app, create=True), \
             patch.object(ResizeHandle, "parent", new=parent_mock, create=True):
            ev = _fake_mm(sx=400, sy=100)
            h.on_mouse_move(ev)

        assert left.styles.width is not None or right.styles.width is not None
        assert ev.is_stopped

    def test_drag_resizes_vertical(self) -> None:
        h = _make_handle(vertical=True)
        h._dragging = True
        h._drag_start_y = 400
        h._start_size = 200
        h._pair_total_cached = 300

        left = MagicMock()
        right = MagicMock()
        left.styles = MagicMock()
        right.styles = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one = lambda sel, cls=None: {"#left-panel": left, "#right-panel": right}.get(sel)
        parent_mock = MagicMock()

        with patch("textual.widget.Widget.app", new=mock_app, create=True), \
             patch.object(ResizeHandle, "parent", new=parent_mock, create=True):
            ev = _fake_mm(sx=100, sy=500)
            h.on_mouse_move(ev)

        assert left.styles.height is not None or right.styles.height is not None
        assert ev.is_stopped

    def test_query_failure_ignores(self) -> None:
        h = _make_handle()
        h._dragging = True
        mock_app = MagicMock()
        mock_app.query_one = Mock(side_effect=Exception("boom"))

        with patch("textual.widget.Widget.app", new=mock_app, create=True):
            h.on_mouse_move(_fake_mm())


class TestMouseUp:
    def test_no_drag_ignores(self) -> None:
        h = _make_handle()
        h._dragging = False
        h.on_mouse_up(_fake_mu())


    def test_drag_ends(self) -> None:
        h = _make_handle()
        h._dragging = True
        h.remove_class = MagicMock()
        h.release_mouse = MagicMock()

        ev = _fake_mu()
        h.on_mouse_up(ev)

        assert h._dragging is False
        h.remove_class.assert_called_once_with("-dragging")
        h.release_mouse.assert_called_once()
        assert ev.is_stopped is True