"""Unit tests for pentool/tui/widgets/diff_panel.py."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

from pentool.tui.widgets.diff_panel import DiffPanel


def _make_panel() -> DiffPanel:
    """Build a bare DiffPanel with mocked __init__."""
    with patch("textual.widget.Widget.__init__", return_value=None):
        p = DiffPanel.__new__(DiffPanel)
    p.styles = MagicMock()
    p._classes = set()  # needed for classes/has_class descriptors
    return p


def _with_classes(p: DiffPanel, cls_set: set[str]) -> None:
    """Replace the 'classes' property with a static frozenset for testing."""
    p._classes_fake = frozenset(cls_set)  # type: ignore[attr-defined]
    p.has_class = lambda c: c in p._classes_fake  # type: ignore[method-assign, misc]

    def add_class(c: str) -> None:
        p._classes_fake = frozenset(set(p._classes_fake) | {c})  # type: ignore[attr-defined, misc]

    def remove_class(c: str) -> None:
        p._classes_fake = frozenset(set(p._classes_fake) - {c})  # type: ignore[attr-defined, misc]

    def classes() -> frozenset:
        return p._classes_fake

    p.add_class = add_class  # type: ignore[method-assign]
    p.remove_class = remove_class  # type: ignore[method-assign]


class TestInit:
    def test_css_loaded(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            p = DiffPanel.__new__(DiffPanel)
        assert len(p.DEFAULT_CSS) > 0


class TestShowDiff:
    def test_calls_compare_and_updates_widgets(self) -> None:
        p = _make_panel()
        log = MagicMock()
        title = MagicMock()
        p.query_one = lambda sel, cls=None: {  # type: ignore[method-assign, assignment]
            "#diff-panel-log": log,
            "#diff-panel-title": title,
        }.get(sel)

        mock_result = MagicMock()
        mock_result.lines = []
        mock_result.stats.added_lines = 1
        mock_result.stats.removed_lines = 2
        mock_result.stats.changed_lines = 3

        with patch("pentool.api.comparer_api.compare", return_value=mock_result):
            p.show_diff("old", "new")

        log.clear.assert_called_once()
        assert "+1" in title.update.call_args[0][0]
        assert "-2" in title.update.call_args[0][0]

    def test_renders_insert_as_green(self) -> None:
        p = _make_panel()
        log = MagicMock()
        title = MagicMock()
        p.query_one = lambda sel, cls=None: {  # type: ignore[method-assign, assignment]
            "#diff-panel-log": log,
            "#diff-panel-title": title,
        }.get(sel)

        mock_result = MagicMock()
        insert = MagicMock()
        insert.tag = "insert"
        insert.right = "new content"
        mock_result.lines = [insert]
        mock_result.stats = MagicMock(added_lines=1, removed_lines=0, changed_lines=0)

        with patch("pentool.api.comparer_api.compare", return_value=mock_result):
            p.show_diff("", "new content")

        assert any("[green]" in c[0][0] for c in log.write.call_args_list)

    def test_renders_delete_as_red(self) -> None:
        p = _make_panel()
        log = MagicMock()
        title = MagicMock()
        p.query_one = lambda sel, cls=None: {  # type: ignore[method-assign, assignment]
            "#diff-panel-log": log,
            "#diff-panel-title": title,
        }.get(sel)

        mock_result = MagicMock()
        dl = MagicMock()
        dl.tag = "delete"
        dl.left = "old content"
        mock_result.lines = [dl]
        mock_result.stats = MagicMock(added_lines=0, removed_lines=1, changed_lines=0)

        with patch("pentool.api.comparer_api.compare", return_value=mock_result):
            p.show_diff("old content", "")

        assert any("[red]" in c[0][0] for c in log.write.call_args_list)

    def test_handles_exception_gracefully(self) -> None:
        p = _make_panel()
        p.query_one = MagicMock()  # type: ignore[method-assign]
        with patch("pentool.api.comparer_api.compare", side_effect=ValueError("boom")):
            p.show_diff("old", "new")


class TestClear:
    def test_clear_clears_log_and_resets_title(self) -> None:
        p = _make_panel()
        log = MagicMock()
        title = MagicMock()
        p.query_one = lambda sel, cls=None: {  # type: ignore[method-assign, assignment]
            "#diff-panel-log": log,
            "#diff-panel-title": title,
        }.get(sel)

        p.clear()
        log.clear.assert_called_once()
        title.update.assert_called_once_with("Diff vs. last sent")

    def test_clear_handles_exception(self) -> None:
        p = _make_panel()
        p.query_one = Mock(side_effect=Exception("boom"))  # type: ignore[method-assign]
        p.clear()


