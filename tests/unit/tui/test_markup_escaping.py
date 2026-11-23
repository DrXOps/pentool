"""F-026: external text must not be parsed as Rich markup.

``RichLog(markup=True)`` and ``Static`` (which has ``markup=True`` by default)
turn a string into markup. Everything that comes from outside — an HTTP response
body, a URL from traffic, a file name, a host from the site map, stderr of an
external utility — gets in there as data, and markup does one of two things
to it:

* **crashes**: ``RichLog.write("[/]")`` → ``MarkupError`` right in the writer.
  Inside the screen's ``except Exception`` that silently drops a whole log line;
* **eats it**: ``a[b]c`` is parsed as the ``[b]`` tag and drawn as ``ac``.
  The user sees something other than what arrived (and ``[link=javascript:…]``
  even becomes a clickable link in HTML reports).

The tests go through real widgets, so they catch exactly what the user sees:
a missing piece of a URL and an exception while writing a line.
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
    """The text actually rendered in the RichLog."""
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
    """The panel title is text: it carries a file name and the ``[html]`` badge."""

    async def test_language_badge_survives_in_the_title(self) -> None:
        """The response viewer shows the body language as ``[html]`` — and it stays visible.

        Without escaping Rich treats ``[html]`` as a tag: the title keeps a
        hole, and the user has no idea which body was shown.
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
        """A diff line comes from the compared bodies — it is not markup."""
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
            # RichLog defers writes until it knows its size, and the panel is
            # hidden by default — so show it, the way toggle() does.
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
        """``[/]`` in a URL used to crash writing the line (MarkupError in the writer)."""
        app = _DashboardHost()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            screen = app.query_one(DashboardScreen)
            screen.push_request("GET", "http://h/path[/]x", 200)
            await pilot.pause()

            written = "\n".join(_log_lines(screen.query_one("#feed-log", RichLog)))
            assert "path[/]x" in written, f"the URL never made it into the feed: {written!r}"


class TestTargetTree:
    """Tree labels: the host and the path segments come from traffic."""

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
        """``/a[b]c/users`` — path segments come from traffic, not from code."""
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
