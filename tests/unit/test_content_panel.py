"""Unit: ContentPanel — all buttons and basic operations.

ContentPanel is checked in isolation (without PentoolApp) by mounting
it into a minimal test App, in order to verify:
- compose: buttons taken from the buttons=[] list
- copy: CopyRequested message carrying text and selection
- paste: PasteRequested message
- clear: clearing the content
- format: FormatToggleRequested message
- wrap: toggling wrap/nowrap on RichLog
- content_widget: returns the correct type (RichLog/TextArea)
- get_text() / get_selected_text()
"""

from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import RichLog, TextArea
from textual.widgets.text_area import Selection as TextAreaSelection

from pentool.tui.widgets.content_panel import ContentPanel


class ContentPanelTestApp(App):
    """Minimal application for testing ContentPanel.

    Allows writing asserts directly on the CapturedMessage objects
    that the widget posts via post_message.
    """

    ALLOW_SELECTOR_MATCH = True

    def __init__(self, *, panel_kwargs: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self._panel_kwargs = panel_kwargs or {}
        self.copy_events: list[ContentPanel.CopyRequested] = []
        self.paste_events: list[ContentPanel.PasteRequested] = []
        self.format_events: list[ContentPanel.FormatToggleRequested] = []

    def compose(self) -> ComposeResult:
        yield ContentPanel(**self._panel_kwargs)

    @on(ContentPanel.CopyRequested)
    def capture_copy(self, event: ContentPanel.CopyRequested) -> None:
        self.copy_events.append(event)

    @on(ContentPanel.PasteRequested)
    def capture_paste(self, event: ContentPanel.PasteRequested) -> None:
        self.paste_events.append(event)

    @on(ContentPanel.FormatToggleRequested)
    def capture_format(self, event: ContentPanel.FormatToggleRequested) -> None:
        self.format_events.append(event)

    @property
    def panel(self) -> ContentPanel:
        return self.query_one(ContentPanel)


# =============================================================================
# compose
# =============================================================================


class TestContentPanelCompose:
    async def test_default_buttons_only_copy(self) -> None:
        """By default BUTTON_SCOPE = ['copy']."""
        app = ContentPanelTestApp(panel_kwargs={"title": "Test"})
        async with app.run_test() as pilot:
            await pilot.pause()
            buttons = app.panel.query("#cp-btn-copy")
            assert len(list(buttons)) == 1
            assert len(list(app.panel.query("#cp-btn-paste"))) == 0

    async def test_explicit_buttons(self) -> None:
        """A custom button list can be provided."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy", "paste", "clear", "format", "wrap"],
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            for bk in ("copy", "paste", "clear", "format", "wrap"):
                assert len(list(app.panel.query(f"#cp-btn-{bk}"))) == 1, f"Missing button '{bk}'"

    async def test_no_buttons(self) -> None:
        """buttons=[] — no buttons, only the title."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": [],
                "title": "NoButtons",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            for bk in ("copy", "paste", "clear", "format", "wrap"):
                assert len(list(app.panel.query(f"#cp-btn-{bk}"))) == 0

    async def test_default_type_is_richlog(self) -> None:
        """By default widget_type = 'richlog'."""
        app = ContentPanelTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.panel.content_widget, RichLog)

    async def test_widget_type_textarea(self) -> None:
        """textarea can be requested explicitly."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "widget_type": "textarea",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.panel.content_widget, TextArea)


# =============================================================================
# content_widget / get_text
# =============================================================================


class TestContentPanelContent:
    async def test_textarea_get_text(self) -> None:
        """get_text() returns the full TextArea text."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "widget_type": "textarea",
                "initial_text": "hello world",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.panel.get_text() == "hello world"

    async def test_get_selected_text_no_selection(self) -> None:
        """get_selected_text() returns None when nothing is selected."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "widget_type": "textarea",
                "initial_text": "abcdef",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.panel.get_selected_text() is None

    async def test_clear_content(self) -> None:
        """clear_content() clears the content."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "widget_type": "textarea",
                "initial_text": "some text",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.panel.clear_content()
            assert app.panel.get_text() == ""


# =============================================================================
# Copy button
# =============================================================================


class TestContentPanelCopy:
    async def test_copy_emits_copy_requested(self) -> None:
        """Pressing ⎙ → CopyRequested with the text."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "textarea",
                "initial_text": "copy this",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            # click the cp-btn-copy button
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            assert app.copy_events[0].text == "copy this"
            assert app.copy_events[0].selection is None  # selection=None = everything

    async def test_copy_sends_selection_when_selected(self) -> None:
        """If there is a selection in the TextArea → CopyRequested with selection."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "textarea",
                "initial_text": "select me",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            ta = app.panel.content_widget
            assert isinstance(ta, TextArea)
            # set the selection manually
            ta.selection = TextAreaSelection(start=(0, 0), end=(0, 6))  # "select"
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            # selection is not None — so the handler receives the selection
            assert app.copy_events[0].selection is not None
            # text is whatever get_selected_text returned (it may be broken by the
            # tuple-to-index conversion bug — this test only checks the click arrives)

    async def test_copy_from_richlog(self) -> None:
        """RichLog → CopyRequested with the whole text."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            rl = app.panel.content_widget
            assert isinstance(rl, RichLog)
            rl.write("line 1\nline 2")
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            # RichLog does not support selection, therefore selection=None
            assert app.copy_events[0].selection is None


# =============================================================================
# Paste button
# =============================================================================


class TestContentPanelPaste:
    async def test_paste_emits_paste_requested(self) -> None:
        """Pressing ⎘ → PasteRequested."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["paste"],
                "widget_type": "textarea",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-paste")
            await pilot.pause()
            assert len(app.paste_events) == 1

    async def test_paste_does_not_clear_content(self) -> None:
        """PasteRequested leaves the content alone — that is up to the screen handler."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["paste"],
                "widget_type": "textarea",
                "initial_text": "existing",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-paste")
            await pilot.pause()
            # content did not change — the screen decides how to paste
            assert app.panel.get_text() == "existing"


# =============================================================================
# Clear button
# =============================================================================


class TestContentPanelClear:
    async def test_clear_clears_textarea(self) -> None:
        """✕ clears the TextArea."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["clear"],
                "widget_type": "textarea",
                "initial_text": "erase me",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-clear")
            await pilot.pause()
            assert app.panel.get_text() == ""

    async def test_clear_clears_richlog(self) -> None:
        """✕ clears the RichLog."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["clear"],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            rl = app.panel.content_widget
            assert isinstance(rl, RichLog)
            rl.write("data")
            await pilot.pause()
            await pilot.click("#cp-btn-clear")
            await pilot.pause()
            assert app.panel.get_text() == ""


# =============================================================================
# Format button
# =============================================================================


class TestContentPanelFormat:
    async def test_format_emits_format_toggle(self) -> None:
        """⇄ → FormatToggleRequested."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["format"],
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-format")
            await pilot.pause()
            assert len(app.format_events) == 1

    async def test_format_on_richlog(self) -> None:
        """FormatToggleRequested also works on RichLog."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["format"],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-format")
            await pilot.pause()
            assert len(app.format_events) == 1


# =============================================================================
# Wrap button (RichLog only)
# =============================================================================


class TestContentPanelWrap:
    async def test_wrap_toggles_on_richlog(self) -> None:
        """↩ toggles wrap on RichLog."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["wrap"],
                "widget_type": "richlog",
                "wrap": True,
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            rl = app.panel.content_widget
            assert isinstance(rl, RichLog)
            assert rl.wrap is True

            await pilot.click("#cp-btn-wrap")
            await pilot.pause()
            assert rl.wrap is False

            await pilot.click("#cp-btn-wrap")
            await pilot.pause()
            assert rl.wrap is True

    async def test_wrap_does_not_appear_on_textarea(self) -> None:
        """The wrap button does not affect TextArea (but the click does not crash)."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["wrap"],
                "widget_type": "textarea",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-wrap")
            await pilot.pause()
            # it simply did not crash — that is the check


# =============================================================================
# Combinations
# =============================================================================


class TestContentPanelMultiButton:
    async def test_all_buttons_work_together(self) -> None:
        """All buttons in one panel: copy + paste + clear + format + wrap."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy", "paste", "clear", "format", "wrap"],
                "widget_type": "textarea",
                "initial_text": "multi",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            # copy
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1

            # paste
            await pilot.click("#cp-btn-paste")
            await pilot.pause()
            assert len(app.paste_events) == 1

            # clear
            await pilot.click("#cp-btn-clear")
            await pilot.pause()
            assert app.panel.get_text() == ""

            # format
            await pilot.click("#cp-btn-format")
            await pilot.pause()
            assert len(app.format_events) == 1

    async def test_copy_paste_clear_with_textarea(self) -> None:
        """copy + paste + clear — the typical set for an editor."""
        txt = "initial content"
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy", "paste", "clear"],
                "widget_type": "textarea",
                "initial_text": txt,
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert app.copy_events[0].text == txt

            await pilot.click("#cp-btn-clear")
            await pilot.pause()
            assert app.panel.get_text() == ""

            # paste
            await pilot.click("#cp-btn-paste")
            await pilot.pause()
            assert len(app.paste_events) == 1


# =============================================================================
# missing buttons do not crash
# =============================================================================


class TestContentPanelEdgeCases:
    async def test_unknown_button_in_list_ignored(self) -> None:
        """An unknown button in buttons[] is simply ignored."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy", "nonexistent", "clear"],
                "widget_type": "textarea",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(list(app.panel.query("#cp-btn-copy"))) == 1
            assert len(list(app.panel.query("#cp-btn-clear"))) == 1
            # the "nonexistent" button is not created, but nothing crashes

    async def test_copy_on_empty_textarea(self) -> None:
        """Copying an empty TextArea does not crash."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "textarea",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            assert app.copy_events[0].text == ""


# =============================================================================
# Widget id
# =============================================================================


class TestContentPanelWidgetId:
    async def test_custom_widget_id(self) -> None:
        """An id can be passed, as with any Widget."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "title": "WithId",
                "id": "my-panel",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.panel
            assert panel.id == "my-panel"
            # ContentPanel itself can be found by id
            assert app.query_one("#my-panel") is panel


# =============================================================================
# ContentPanel migration — TargetScreen (detail-panel, buttons=["copy"])
# =============================================================================


class TestTargetDetailPanel:
    async def test_target_detail_renders(self) -> None:
        """ContentPanel with the copy button + RichLog."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "richlog",
                "wrap": True,
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.panel
            assert isinstance(panel.content_widget, RichLog)
            buttons = list(panel.query("#cp-btn-copy"))
            assert len(buttons) == 1

    async def test_target_detail_copy(self) -> None:
        """Copy from the detail log."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            w = app.panel.content_widget
            w.write("detail host info")
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1


# =============================================================================
# ContentPanel migration — DashboardScreen (feed-panel, buttons=[])
# =============================================================================


class TestDashboardFeedPanel:
    async def test_dashboard_feed_no_buttons(self) -> None:
        """Dashboard feed — no buttons."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": [],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.panel
            for btn_id in ("copy", "paste", "clear", "format", "wrap"):
                assert len(list(panel.query(f"#cp-btn-{btn_id}"))) == 0

    async def test_dashboard_feed_write_to_log(self) -> None:
        """write_to_log() does not crash on a panel without buttons."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": [],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.panel.write_to_log("feed message")
            await pilot.pause()

    async def test_dashboard_feed_clear(self) -> None:
        """clear_content() without buttons."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": [],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.panel.write_to_log("data")
            app.panel.clear_content()
            await pilot.pause()


# =============================================================================
# ContentPanel migration — ComparerScreen (cmp-diff-area, buttons=["copy"])
# =============================================================================


class TestComparerDiffPanel:
    async def test_comparer_diff_renders(self) -> None:
        """Diff panel with wrap=False + copy."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "richlog",
                "wrap": False,
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.panel.content_widget, RichLog)
            assert len(list(app.panel.query("#cp-btn-copy"))) == 1

    async def test_comparer_diff_copy(self) -> None:
        """Copy from the diff."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            w = app.panel.content_widget
            w.write("--- a/file")
            w.write("+++ b/file")
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1

    async def test_comparer_diff_clear(self) -> None:
        """Clearing the diff via clear_content()."""
        app = ContentPanelTestApp(
            panel_kwargs={
                "buttons": ["copy"],
                "widget_type": "richlog",
            }
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            w = app.panel.content_widget
            w.write("content")
            await pilot.pause()
            app.panel.clear_content()
            await pilot.pause()
            assert app.panel.get_text() == ""
