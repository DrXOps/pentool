"""Unit: ComparerScreen — ContentPanel интеграция, copy/paste, public API.

Проверяем что после миграции TextArea → ContentPanel:
- compose не падает
- cmp-left-panel и cmp-right-panel суть ContentPanel с TextArea внутри
- CopyRequested / PasteRequested обрабатываются
- set_title() работает
- public API (load_left/load_right/load_smart/action_clear) работает
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.widgets.content_panel import ContentPanel


class ComparerTestApp(App):
    """Минимальное приложение с ComparerScreen для тестов."""

    ALLOW_SELECTOR_MATCH = True

    def compose(self) -> ComposeResult:
        yield ComparerScreen()


def _left_panel(app: ComparerTestApp) -> ContentPanel:
    return app.query_one("#cmp-left-panel", ContentPanel)


def _right_panel(app: ComparerTestApp) -> ContentPanel:
    return app.query_one("#cmp-right-panel", ContentPanel)


def _diff_panel(app: ComparerTestApp) -> ContentPanel:
    # cmp-diff-area — Vertical; ContentPanel внутри без id, ищем по типу внутри него
    area = app.query_one("#cmp-diff-area")
    return area.query_one(ContentPanel)


def _cmp_screen(app: ComparerTestApp) -> ComparerScreen:
    return app.query_one(ComparerScreen)


# =============================================================================
# compose
# =============================================================================


class TestComparerCompose:
    async def test_compose_does_not_crash(self) -> None:
        """Создание ComparerScreen не падает."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _cmp_screen(app) is not None

    async def test_left_panel_exists(self) -> None:
        """cmp-left-panel — ContentPanel с TextArea."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import TextArea

            panel = _left_panel(app)
            assert panel.id == "cmp-left-panel"
            assert isinstance(panel.content_widget, TextArea)

    async def test_right_panel_exists(self) -> None:
        """cmp-right-panel — ContentPanel с TextArea."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import TextArea

            panel = _right_panel(app)
            assert panel.id == "cmp-right-panel"
            assert isinstance(panel.content_widget, TextArea)

    async def test_left_panel_has_copy_paste(self) -> None:
        """Левая панель имеет кнопки copy и paste."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(list(_left_panel(app).query("#cp-btn-copy"))) == 1
            assert len(list(_left_panel(app).query("#cp-btn-paste"))) == 1

    async def test_right_panel_has_copy_paste(self) -> None:
        """Правая панель имеет кнопки copy и paste."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(list(_right_panel(app).query("#cp-btn-copy"))) == 1
            assert len(list(_right_panel(app).query("#cp-btn-paste"))) == 1

    async def test_diff_panel_exists(self) -> None:
        """cmp-diff-area — ContentPanel с RichLog или TextArea."""
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
        """По умолчанию заголовок Left."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _left_panel(app)._panel_title == "Left"

    async def test_right_title_default(self) -> None:
        """По умолчанию заголовок Right."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _right_panel(app)._panel_title == "Right"

    async def test_set_title_left(self) -> None:
        """set_title() обновляет заголовок левой панели."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _left_panel(app).set_title("test.txt")
            await pilot.pause()
            assert _left_panel(app)._panel_title == "test.txt"

    async def test_set_title_right(self) -> None:
        """set_title() обновляет заголовок правой панели."""
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
    """Copy/paste через кнопки ContentPanel — проверяем эффект, не «не упало».

    Раньше здесь было четыре теста без единого assert (F-034): хендлеры
    миксина вообще не регистрировались, поэтому кнопки были no-op, и тесты
    при этом оставались зелёными. Теперь буфер подменяется, а результат
    проверяется по содержимому TextArea и по аргументу copy_to_clipboard.
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
        """load_left() загружает текст и меняет заголовок."""
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
        """load_right() загружает текст и меняет заголовок."""
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
        """load_smart() когда левая пуста — загружает в левую."""
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
        """load_smart() когда левая не пуста — загружает в правую."""
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
        """action_clear() очищает оба поля и сбрасывает заголовки."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # заполняем
            _cmp_screen(app).load_left("left text", label="a.txt")
            _cmp_screen(app).load_right("right text", label="b.txt")
            await pilot.pause()
            # очищаем
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
        """load_left() без label ставит 'Left'."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("test")
            await pilot.pause()
            assert _left_panel(app)._panel_title == "Left"

    async def test_load_right_default_label(self) -> None:
        """load_right() без label ставит 'Right'."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_right("test")
            await pilot.pause()
            assert _right_panel(app)._panel_title == "Right"

    async def test_action_compare_empty(self) -> None:
        """Сравнение пустых полей не падает."""
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
        """set_title() меняет _panel_title."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = _left_panel(app)
            panel.set_title("New Title")
            await pilot.pause()
            assert panel._panel_title == "New Title"

    async def test_set_title_cleared_after_clear(self) -> None:
        """После action_clear заголовки возвращаются к Left/Right."""
        app = ComparerTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            _cmp_screen(app).load_left("data", label="myfile.txt")
            await pilot.pause()
            assert _left_panel(app)._panel_title == "myfile.txt"
            _cmp_screen(app).action_clear()
            await pilot.pause()
            assert _left_panel(app)._panel_title == "Left"
