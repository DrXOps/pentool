"""F-026: внешний текст не должен разбираться как Rich-разметка.

``RichLog(markup=True)`` и ``Static`` (у него ``markup=True`` по умолчанию)
превращают строку в разметку. Всё, что приходит извне — тело HTTP-ответа,
URL из трафика, имя файла, host из карты сайта, stderr внешней утилиты —
попадает туда как данные, и разметка делает с ним одно из двух:

* **падает**: ``RichLog.write("[/]")`` → ``MarkupError`` прямо в писателе.
  В ``except Exception`` экрана это тихая потеря целой строки лога;
* **съедает**: ``a[b]c`` разбирается как тег ``[b]`` и рисуется как ``ac``.
  Пользователь видит не то, что пришло (а ``[link=javascript:…]`` ещё и
  становится кликабельной ссылкой в HTML-отчётах).

Тесты идут через настоящие виджеты, поэтому ловят именно то, что видит
пользователь: пропавший кусок URL и исключение при записи строки.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import RichLog, Static

from pentool.tui.markup import esc
from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.screens.dashboard.screen import DashboardScreen
from pentool.tui.screens.target.screen import TargetScreen
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.diff_panel import DiffPanel
from pentool.tui.widgets.inspector_panel import InspectorPanel


def _log_lines(log: RichLog) -> list[str]:
    """Текст, который реально отрисован в RichLog."""
    return [strip.text for strip in log.lines]


class _PanelHost(App):
    def compose(self) -> ComposeResult:
        yield ContentPanel("Panel", widget_type="richlog", id="panel")


class _DiffHost(App):
    def compose(self) -> ComposeResult:
        yield DiffPanel()


class _ComparerHost(App):
    def compose(self) -> ComposeResult:
        yield ComparerScreen()


class _DashboardHost(App):
    def compose(self) -> ComposeResult:
        yield DashboardScreen()


class _TargetHost(App):
    def compose(self) -> ComposeResult:
        yield TargetScreen()


class TestEscHelper:
    def test_closing_tag_is_text_not_a_parse_error(self) -> None:
        assert esc("[/]") == "\\[/]"

    def test_link_markup_loses_its_power(self) -> None:
        from rich.text import Text

        rendered = Text.from_markup(esc("[link=javascript:alert(1)]click[/link]"))
        assert rendered.spans == [], "escaped text still produced a link span"
        assert "[link=javascript" in rendered.plain

    def test_non_string_values_are_stringified(self) -> None:
        assert esc(42) == "42"
        assert esc(None) == "None"


class TestContentPanelTitle:
    """Заголовок панели — текст: там имя файла и метка ``[html]``."""

    async def test_language_badge_survives_in_the_title(self) -> None:
        """Response-viewer показывает язык ответа как ``[html]`` — и он виден.

        Без экранирования Rich считает ``[html]`` тегом: в заголовке остаётся
        дырка, а пользователь не знает, что за тело ему показали.
        """
        app = _PanelHost()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            panel = app.query_one("#panel", ContentPanel)
            panel.set_title("Response  ·  200 OK  ·  1 KB  [html]")
            await pilot.pause()

            title = str(panel.query_one(".cp-title > Static", Static).render())
            assert "[html]" in title, f"the language badge vanished from the title: {title!r}"

    async def test_filename_with_brackets_stays_readable(self) -> None:
        app = _PanelHost()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            panel = app.query_one("#panel", ContentPanel)
            panel.set_title("report[1]final.json")
            await pilot.pause()

            title = str(panel.query_one(".cp-title > Static", Static).render())
            assert title == "┌─ report[1]final.json ─", f"the title lost characters or the frame: {title!r}"


class TestComparerDiffLog:
    async def test_diff_lines_with_brackets_reach_the_log(self) -> None:
        """Строка дифа приходит из сравниваемых тел — она не разметка."""
        app = _ComparerHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            screen = app.query_one(ComparerScreen)
            screen.load_left("payload=[a]\nsecond", "left")
            screen.load_right("payload=[b]\nsecond", "right")
            screen.action_compare()
            await pilot.pause()

            log = screen.query_one("#cmp-diff-area ContentPanel", ContentPanel).content_widget
            written = "\n".join(_log_lines(log))
            assert "payload=[a]" in written, f"diff line lost its brackets: {written!r}"
            assert "payload=[b]" in written


class TestDiffPanelLog:
    async def test_repeater_diff_survives_markup_in_the_body(self) -> None:
        app = _DiffHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            panel = app.query_one(DiffPanel)
            # RichLog откладывает записи до первого известного размера, а панель
            # по умолчанию скрыта — показываем её, как это делает toggle().
            panel.toggle()
            await pilot.pause()
            panel.show_diff("[/]\nplain", "[bold]\nplain")
            await pilot.pause()

            log = panel.query_one("#diff-panel-log", RichLog)
            written = "\n".join(_log_lines(log))
            assert "[/]" in written, f"the diff panel swallowed a markup-looking body: {written!r}"
            assert "[bold]" in written


class TestDashboardFeed:
    async def test_activity_with_markup_in_the_message_is_shown_as_is(self) -> None:
        app = _DashboardHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            screen = app.query_one(DashboardScreen)
            screen.log_activity("host a[b]c rejected")
            await pilot.pause()

            log = screen.query_one("#feed-log", RichLog)
            written = "\n".join(_log_lines(log))
            assert "a[b]c" in written, f"feed line lost the bracketed host: {written!r}"

    async def test_a_request_url_with_closing_tag_does_not_break_the_feed(self) -> None:
        """``[/]`` в URL раньше ронял запись строки (MarkupError в писателе)."""
        app = _DashboardHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            screen = app.query_one(DashboardScreen)
            screen.push_request("GET", "http://h/path[/]x", 200)
            await pilot.pause()

            written = "\n".join(_log_lines(screen.query_one("#feed-log", RichLog)))
            assert "path[/]x" in written, f"the URL never made it into the feed: {written!r}"


class TestTargetTree:
    """Подписи дерева: host и сегменты пути приходят из трафика."""

    async def test_host_in_scope_keeps_its_brackets(self) -> None:
        app = _TargetHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            screen = app.query_one(TargetScreen)
            screen._build_tree({"a[b]c": []})
            await pilot.pause()

            tree = screen.query_one("#site-tree")
            labels = [child.label.plain for child in tree.root.children]
            assert any("a[b]c" in label for label in labels), f"host label lost the brackets: {labels!r}"

    async def test_path_segments_are_escaped_in_the_labels(self) -> None:
        """``/a[b]c/users`` — сегменты пути приходят из трафика, не из кода."""
        from pentool.api.target_api import SiteNode

        app = _TargetHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            screen = app.query_one(TargetScreen)
            tree = screen.query_one("#site-tree")
            host_node = tree.root.add("h", data={"type": "host", "host": "h"})
            screen._add_path_node_tree(
                host_node,
                "h",
                SiteNode(host="h", path="/a[b]c/users", methods={"GET"}, request_count=1),
            )
            await pilot.pause()

            # /a[b]c/users → dir "a[b]c" → leaf "users  [GET] (1)"
            dir_label = host_node.children[-1].label.plain
            dir_node = host_node.children[-1]
            leaf = dir_node.children[-1].label.plain
            assert dir_label == "a[b]c", f"a directory segment lost its brackets: {dir_label!r}"
            assert leaf.startswith("users"), f"leaf label mangled: {leaf!r}"


class TestInspectorRows:
    def test_header_values_are_rendered_literally(self) -> None:
        widgets: list = []
        InspectorPanel._add_section(widgets, "Headers", {"X-Test[a]": "va[l]ue"})
        row = widgets[-1]
        rendered = str(row.render())
        assert "X-Test[a]" in rendered, f"header name lost characters: {rendered!r}"
        assert "va[l]ue" in rendered, f"header value lost characters: {rendered!r}"
