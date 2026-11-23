"""Unit: ComparerScreen — ContentPanel integration, copy/paste, public API.

Verifies that after the TextArea → ContentPanel migration:
- compose does not crash
- cmp-left-panel and cmp-right-panel are ContentPanel with a TextArea inside
- CopyRequested / PasteRequested are handled
- set_title() works
- public API (load_left/load_right/load_smart/action_clear) works
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.widgets.content_panel import ContentPanel


class ComparerTestApp(App):
    """Minimal app with ComparerScreen for tests."""

    ALLOW_SELECTOR_MATCH = True

    def compose(self) -> ComposeResult:
        yield ComparerScreen()


def _left_panel(app: ComparerTestApp) -> ContentPanel:
    return app.query_one("#cmp-left-panel", ContentPanel)


def _right_panel(app: ComparerTestApp) -> ContentPanel:
    return app.query_one("#cmp-right-panel", ContentPanel)


def _diff_panel(app: ComparerTestApp) -> ContentPanel:
    # cmp-diff-area — Vertical; the ContentPanel inside has no id, find it by type
    area = app.query_one("#cmp-diff-area")
    return area.query_one(ContentPanel)


def _cmp_screen(app: ComparerTestApp) -> ComparerScreen:
    return app.query_one(ComparerScreen)


# =============================================================================
# compose
# =============================================================================


class TestComparerCompose:
    async def test_compose_does_not_crash(self) -> None:
        """Creating a ComparerScreen does not crash."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _cmp_screen(app) is not None

    async def test_left_panel_exists(self) -> None:
        """cmp-left-panel — a ContentPanel with a TextArea."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import TextArea

            panel = _left_panel(app)
            assert panel.id == "cmp-left-panel"
            assert isinstance(panel.content_widget, TextArea)

    async def test_right_panel_exists(self) -> None:
        """cmp-right-panel — a ContentPanel with a TextArea."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import TextArea

            panel = _right_panel(app)
            assert panel.id == "cmp-right-panel"
            assert isinstance(panel.content_widget, TextArea)

    async def test_left_panel_has_copy_paste(self) -> None:
        """The left panel has copy and paste buttons."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(list(_left_panel(app).query("#cp-btn-copy"))) == 1
            assert len(list(_left_panel(app).query("#cp-btn-paste"))) == 1

    async def test_right_panel_has_copy_paste(self) -> None:
        """The right panel has copy and paste buttons."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(list(_right_panel(app).query("#cp-btn-copy"))) == 1
            assert len(list(_right_panel(app).query("#cp-btn-paste"))) == 1

    async def test_diff_panel_exists(self) -> None:
        """cmp-diff-area — a ContentPanel with RichLog or TextArea."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = _diff_panel(app)
            from textual.widgets import RichLog, TextArea

            assert isinstance(panel.content_widget, (RichLog, TextArea))


# =============================================================================
# set_title
# =============================================================================


class TestComparerTitle:
    async def test_left_title_default(self) -> None:
        """By default the title is Left."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _left_panel(app)._panel_title == "Left"

    async def test_right_title_default(self) -> None:
        """By default the title is Right."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _right_panel(app)._panel_title == "Right"

    async def test_set_title_left(self) -> None:
        """set_title() updates the left panel title."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _left_panel(app).set_title("test.txt")
            await pilot.pause()
            assert _left_panel(app)._panel_title == "test.txt"

    async def test_set_title_right(self) -> None:
        """set_title() updates the right panel title."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _right_panel(app).set_title("other.txt")
            await pilot.pause()
            assert _right_panel(app)._panel_title == "other.txt"


# =============================================================================
# copy / paste
# =============================================================================


class TestComparerCopyPaste:
    """Copy/paste via the ContentPanel buttons — we check the effect, not just no crash.

    Previously there were four tests here without a single assert (F-034): the
    mixin handlers were never registered at all, so the buttons were no-ops, and
    the tests still stayed green. Now the clipboard is replaced, and the result
    is checked against the TextArea contents and the copy_to_clipboard argument.
    """

    @pytest.fixture
    def clipboard(self, monkeypatch: pytest.MonkeyPatch):
        state = {"copied": [], "text": "CLIP"}

        def _copy(text: str) -> bool:
            state["copied"].append(text)
            return True

        monkeypatch.setattr("pentool.utils.copy_as.copy_to_clipboard", _copy)
        monkeypatch.setattr("pentool.utils.copy_as.paste_from_clipboard", lambda: state["text"])
        return state

    async def test_left_copy_sends_text_to_clipboard(self, clipboard) -> None:
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("left content")
            await pilot.pause()
            await pilot.click("#cmp-left-panel #cp-btn-copy")
            await pilot.pause()
            assert clipboard["copied"] == ["left content"]

    async def test_right_copy_sends_text_to_clipboard(self, clipboard) -> None:
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_right("right content")
            await pilot.pause()
            await pilot.click("#cmp-right-panel #cp-btn-copy")
            await pilot.pause()
            assert clipboard["copied"] == ["right content"]

    async def test_left_paste_inserts_clipboard_text(self, clipboard) -> None:
        from textual.widgets import TextArea

        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cmp-left-panel #cp-btn-paste")
            await pilot.pause()
            area = _left_panel(app).content_widget
            assert isinstance(area, TextArea)
            assert "CLIP" in area.text

    async def test_right_paste_inserts_clipboard_text(self, clipboard) -> None:
        from textual.widgets import TextArea

        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cmp-right-panel #cp-btn-paste")
            await pilot.pause()
            area = _right_panel(app).content_widget
            assert isinstance(area, TextArea)
            assert "CLIP" in area.text


# =============================================================================
# public API
# =============================================================================


class TestComparerPublicAPI:
    async def test_load_left(self) -> None:
        """load_left() loads the text and changes the title."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("hello", label="greeting.txt")
            await pilot.pause()
            from textual.widgets import TextArea

            ta = _left_panel(app).content_widget
            assert isinstance(ta, TextArea)
            assert ta.text == "hello"
            assert _left_panel(app)._panel_title == "greeting.txt"

    async def test_load_right(self) -> None:
        """load_right() loads the text and changes the title."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_right("world", label="data.txt")
            await pilot.pause()
            from textual.widgets import TextArea

            ta = _right_panel(app).content_widget
            assert isinstance(ta, TextArea)
            assert ta.text == "world"
            assert _right_panel(app)._panel_title == "data.txt"

    async def test_load_smart_empty_left(self) -> None:
        """load_smart() when the left panel is empty — loads into the left one."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_smart("first text", label="file1.txt")
            await pilot.pause()
            from textual.widgets import TextArea

            ta = _left_panel(app).content_widget
            assert isinstance(ta, TextArea)
            assert ta.text == "first text"
            assert _left_panel(app)._panel_title == "file1.txt"

    async def test_load_smart_filled_left(self) -> None:
        """load_smart() when the left panel is not empty — loads into the right one."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("existing", label="left.txt")
            await pilot.pause()
            _cmp_screen(app).load_smart("second text", label="file2.txt")
            await pilot.pause()
            from textual.widgets import TextArea

            right_ta = _right_panel(app).content_widget
            assert isinstance(right_ta, TextArea)
            assert right_ta.text == "second text"
            assert _right_panel(app)._panel_title == "file2.txt"

    async def test_action_clear(self) -> None:
        """action_clear() clears both fields and resets the titles."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # fill in
            _cmp_screen(app).load_left("left text", label="a.txt")
            _cmp_screen(app).load_right("right text", label="b.txt")
            await pilot.pause()
            # clear
            _cmp_screen(app).action_clear()
            await pilot.pause()
            from textual.widgets import TextArea

            left_ta = _left_panel(app).content_widget
            right_ta = _right_panel(app).content_widget
            assert isinstance(left_ta, TextArea)
            assert isinstance(right_ta, TextArea)
            assert left_ta.text == ""
            assert right_ta.text == ""
            assert _left_panel(app)._panel_title == "Left"
            assert _right_panel(app)._panel_title == "Right"

    async def test_load_left_default_label(self) -> None:
        """load_left() without label sets 'Left'."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("test")
            await pilot.pause()
            assert _left_panel(app)._panel_title == "Left"

    async def test_load_right_default_label(self) -> None:
        """load_right() without label sets 'Right'."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_right("test")
            await pilot.pause()
            assert _right_panel(app)._panel_title == "Right"

    async def test_action_compare_empty(self) -> None:
        """Comparing empty fields does not crash."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).action_compare()
            await pilot.pause()


# =============================================================================
# ContentPanel set_title (core feature used by Comparer)
# =============================================================================


class TestContentPanelSetTitle:
    async def test_set_title_updates_query(self) -> None:
        """set_title() changes _panel_title."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = _left_panel(app)
            panel.set_title("New Title")
            await pilot.pause()
            assert panel._panel_title == "New Title"

    async def test_set_title_cleared_after_clear(self) -> None:
        """After action_clear the titles return to Left/Right."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("data", label="myfile.txt")
            await pilot.pause()
            assert _left_panel(app)._panel_title == "myfile.txt"
            _cmp_screen(app).action_clear()
            await pilot.pause()
            assert _left_panel(app)._panel_title == "Left"
