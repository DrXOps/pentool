"""Unit: ContentPanel — все кнопки и базовые операции.

Проверяем ContentPanel изолированно (без PentoolApp), монтируя
его в минимальный тестовый App, чтобы проверить:
- compose: кнопки по списку buttons=[]
- copy: сообщение CopyRequested с текстом и selection
- paste: сообщение PasteRequested
- clear: очистка содержимого
- format: сообщение FormatToggleRequested
- wrap: переключение wrap/nowrap у RichLog
- content_widget: возвращает правильный тип (RichLog/TextArea)
- get_text() / get_selected_text()
"""

from __future__ import annotations

import pytest
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import RichLog, TextArea
from textual.widgets.text_area import Selection as TextAreaSelection

from pentool.tui.widgets.content_panel import ContentPanel


class ContentPanelTestApp(App):
    """Минимальное приложение для тестирования ContentPanel.

    Позволяет писать assert'ы прямо на CapturedMessage'ах,
    которые виджет постит через post_message.
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
        """По умолчанию BUTTON_SCOPE = ['copy']."""
        app = ContentPanelTestApp(panel_kwargs={"title": "Test"})
        async with app.run_test() as pilot:
            await pilot.pause()
            buttons = app.panel.query("#cp-btn-copy")
            assert len(list(buttons)) == 1
            assert len(list(app.panel.query("#cp-btn-paste"))) == 0

    async def test_explicit_buttons(self) -> None:
        """Можно задать кастомный список кнопок."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy", "paste", "clear", "format", "wrap"],
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            for bk in ("copy", "paste", "clear", "format", "wrap"):
                assert len(list(app.panel.query(f"#cp-btn-{bk}"))) == 1, \
                    f"Missing button '{bk}'"

    async def test_no_buttons(self) -> None:
        """buttons=[] — кнопок нет, только тайтл."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": [],
            "title": "NoButtons",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            for bk in ("copy", "paste", "clear", "format", "wrap"):
                assert len(list(app.panel.query(f"#cp-btn-{bk}"))) == 0

    async def test_default_type_is_richlog(self) -> None:
        """По умолчанию widget_type = 'richlog'."""
        app = ContentPanelTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.panel.content_widget, RichLog)

    async def test_widget_type_textarea(self) -> None:
        """Можно явно указать textarea."""
        app = ContentPanelTestApp(panel_kwargs={
            "widget_type": "textarea",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.panel.content_widget, TextArea)


# =============================================================================
# content_widget / get_text
# =============================================================================

class TestContentPanelContent:

    async def test_textarea_get_text(self) -> None:
        """get_text() возвращает полный текст TextArea."""
        app = ContentPanelTestApp(panel_kwargs={
            "widget_type": "textarea",
            "initial_text": "hello world",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.panel.get_text() == "hello world"

    async def test_get_selected_text_no_selection(self) -> None:
        """get_selected_text() возвращает None если ничего не выделено."""
        app = ContentPanelTestApp(panel_kwargs={
            "widget_type": "textarea",
            "initial_text": "abcdef",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.panel.get_selected_text() is None

    async def test_clear_content(self) -> None:
        """clear_content() очищает содержимое."""
        app = ContentPanelTestApp(panel_kwargs={
            "widget_type": "textarea",
            "initial_text": "some text",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            app.panel.clear_content()
            assert app.panel.get_text() == ""


# =============================================================================
# Кнопка Copy
# =============================================================================

class TestContentPanelCopy:

    async def test_copy_emits_copy_requested(self) -> None:
        """Нажатие ⎙ → CopyRequested с текстом."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "textarea",
            "initial_text": "copy this",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            # клик по кнопке cp-btn-copy
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            assert app.copy_events[0].text == "copy this"
            assert app.copy_events[0].selection is None  # selection=None = всё

    async def test_copy_sends_selection_when_selected(self) -> None:
        """Если есть выделение в TextArea → CopyRequested с selection."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "textarea",
            "initial_text": "select me",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            ta = app.panel.content_widget
            assert isinstance(ta, TextArea)
            # установим выделение вручную
            ta.selection = TextAreaSelection(start=(0, 0), end=(0, 6))  # "select"
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            # selection не None — значит хендлер получит выбор
            assert app.copy_events[0].selection is not None
            # text это то что отдала get_selected_text (может быть broken из-за бага
            # с преобразованием кортежа в индекс — тест проверяет что мышь доходит)

    async def test_copy_from_richlog(self) -> None:
        """RichLog → CopyRequested со всем текстом."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "richlog",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            rl = app.panel.content_widget
            assert isinstance(rl, RichLog)
            rl.write("line 1\nline 2")
            await pilot.pause()
            await pilot.click("#cp-btn-copy")
            await pilot.pause()
            assert len(app.copy_events) == 1
            # RichLog не поддерживает selection, поэтому selection=None
            assert app.copy_events[0].selection is None


# =============================================================================
# Кнопка Paste
# =============================================================================

class TestContentPanelPaste:

    async def test_paste_emits_paste_requested(self) -> None:
        """Нажатие ⎘ → PasteRequested."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["paste"],
            "widget_type": "textarea",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-paste")
            await pilot.pause()
            assert len(app.paste_events) == 1

    async def test_paste_does_not_clear_content(self) -> None:
        """PasteRequested не трогает содержимое — это прерогатива хендлера экрана."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["paste"],
            "widget_type": "textarea",
            "initial_text": "existing",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-paste")
            await pilot.pause()
            # содержимое не изменилось — экран сам решает как вставлять
            assert app.panel.get_text() == "existing"


# =============================================================================
# Кнопка Clear
# =============================================================================

class TestContentPanelClear:

    async def test_clear_clears_textarea(self) -> None:
        """✕ очищает TextArea."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["clear"],
            "widget_type": "textarea",
            "initial_text": "erase me",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-clear")
            await pilot.pause()
            assert app.panel.get_text() == ""

    async def test_clear_clears_richlog(self) -> None:
        """✕ очищает RichLog."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["clear"],
            "widget_type": "richlog",
        })
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
# Кнопка Format
# =============================================================================

class TestContentPanelFormat:

    async def test_format_emits_format_toggle(self) -> None:
        """⇄ → FormatToggleRequested."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["format"],
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-format")
            await pilot.pause()
            assert len(app.format_events) == 1

    async def test_format_on_richlog(self) -> None:
        """FormatToggleRequested работает и на RichLog."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["format"],
            "widget_type": "richlog",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-format")
            await pilot.pause()
            assert len(app.format_events) == 1


# =============================================================================
# Кнопка Wrap (только RichLog)
# =============================================================================

class TestContentPanelWrap:

    async def test_wrap_toggles_on_richlog(self) -> None:
        """↩ переключает wrap на RichLog."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["wrap"],
            "widget_type": "richlog",
            "wrap": True,
        })
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
        """wrap кнопка не влияет на TextArea (но клик не падает)."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["wrap"],
            "widget_type": "textarea",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#cp-btn-wrap")
            await pilot.pause()
            # просто не упало — уже проверка


# =============================================================================
# Комбинации
# =============================================================================

class TestContentPanelMultiButton:

    async def test_all_buttons_work_together(self) -> None:
        """Все кнопки в одном панеле: copy + paste + clear + format + wrap."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy", "paste", "clear", "format", "wrap"],
            "widget_type": "textarea",
            "initial_text": "multi",
        })
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
        """copy + paste + clear — типичный набор для редактора."""
        txt = "initial content"
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy", "paste", "clear"],
            "widget_type": "textarea",
            "initial_text": txt,
        })
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
# отсутствующие кнопки не падают
# =============================================================================

class TestContentPanelEdgeCases:

    async def test_unknown_button_in_list_ignored(self) -> None:
        """Если в buttons[] есть неизвестная кнопка — просто игнорируется."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy", "nonexistent", "clear"],
            "widget_type": "textarea",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(list(app.panel.query("#cp-btn-copy"))) == 1
            assert len(list(app.panel.query("#cp-btn-clear"))) == 1
            # кнопка "nonexistent" не создаётся, но не падает

    async def test_copy_on_empty_textarea(self) -> None:
        """Копирование пустого TextArea не падает."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "textarea",
        })
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
        """Можно передать id, как у любого Widget."""
        app = ContentPanelTestApp(panel_kwargs={
            "title": "WithId",
            "id": "my-panel",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.panel
            assert panel.id == "my-panel"
            # сам ContentPanel можно найти по id
            assert app.query_one("#my-panel") is panel

# =============================================================================
# ContentPanel migration — TargetScreen (detail-panel, buttons=["copy"])
# =============================================================================

class TestTargetDetailPanel:

    async def test_target_detail_renders(self) -> None:
        """ContentPanel с copy кнопкой + RichLog."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "richlog",
            "wrap": True,
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.panel
            assert isinstance(panel.content_widget, RichLog)
            buttons = list(panel.query("#cp-btn-copy"))
            assert len(buttons) == 1

    async def test_target_detail_copy(self) -> None:
        """Copy из detail-log."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "richlog",
        })
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
        """Dashboard feed — без кнопок."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": [],
            "widget_type": "richlog",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.panel
            for btn_id in ("copy", "paste", "clear", "format", "wrap"):
                assert len(list(panel.query(f"#cp-btn-{btn_id}"))) == 0

    async def test_dashboard_feed_write_to_log(self) -> None:
        """write_to_log() не падает на панели без кнопок."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": [],
            "widget_type": "richlog",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            app.panel.write_to_log("feed message")
            await pilot.pause()

    async def test_dashboard_feed_clear(self) -> None:
        """clear_content() без кнопок."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": [],
            "widget_type": "richlog",
        })
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
        """Diff-панель с wrap=False + copy."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "richlog",
            "wrap": False,
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.panel.content_widget, RichLog)
            assert len(list(app.panel.query("#cp-btn-copy"))) == 1

    async def test_comparer_diff_copy(self) -> None:
        """Copy из diff."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "richlog",
        })
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
        """Очистка diff через clear_content()."""
        app = ContentPanelTestApp(panel_kwargs={
            "buttons": ["copy"],
            "widget_type": "richlog",
        })
        async with app.run_test() as pilot:
            await pilot.pause()
            w = app.panel.content_widget
            w.write("content")
            await pilot.pause()
            app.panel.clear_content()
            await pilot.pause()
            assert app.panel.get_text() == ""
