"""Site Map tree: selecting a node must not crash the application.

Defect found: `on_tree_node_selected` took `#detail-panel` as a `Vertical`
and called `log.clear()`. `Vertical` has no such method → `AttributeError` when
selecting **any** tree node, i.e. a crash on the very first click. Two other
places also looked up `#detail-panel` as a `ContentPanel`, but in reality it was
a wrapper container, so they raised `NoMatches` as well.

Now `#detail-panel` is the `ContentPanel` itself, and writing goes through its
API (`clear_content` / `write_to_log`).
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.utils.parser import ParsedRequest


async def _settle(pilot, cycles: int = 15) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def _open_target_with_requests(pilot):
    app = pilot.app
    await _settle(pilot)
    app.action_switch_module("target")
    await _settle(pilot, 25)
    screen = app.query_one("TargetScreen")
    for path in ("/", "/admin"):
        screen.add_request_from_proxy(
            ParsedRequest(method="GET", url=f"http://tree.example{path}", headers={"Host": "tree.example"})
        )
    screen._refresh_tree()
    await _settle(pilot, 20)
    return screen


@pytest.mark.asyncio
async def test_detail_panel_is_a_content_panel() -> None:
    """Otherwise `clear_content`/`write_to_log` from other places will miss again."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_target_with_requests(pilot)
        panel = screen.query_one("#detail-panel", ContentPanel)
        assert isinstance(panel, ContentPanel)


@pytest.mark.asyncio
async def test_selecting_a_host_node_does_not_crash_and_fills_details() -> None:
    from textual.widgets import Tree

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_target_with_requests(pilot)
        tree = screen.query_one("#site-tree", Tree)
        hosts = list(tree.root.children)
        assert hosts, "карта сайта пуста — тест не проверит выбор узла"

        tree.select_node(hosts[0])  # this exact call used to crash with AttributeError
        await _settle(pilot, 15)

        panel = screen.query_one("#detail-panel", ContentPanel)
        text = panel.get_text()
        assert "tree.example" in text, f"детали узла не заполнились: {text!r}"


@pytest.mark.asyncio
async def test_selecting_a_path_node_fills_details() -> None:
    from textual.widgets import Tree

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_target_with_requests(pilot)
        tree = screen.query_one("#site-tree", Tree)
        host = list(tree.root.children)[0]
        host.expand()
        await _settle(pilot, 15)

        paths = list(host.children)
        assert paths, "у хоста нет путей в дереве"

        tree.select_node(paths[0])
        await _settle(pilot, 15)
        text = screen.query_one("#detail-panel", ContentPanel).get_text()
        assert "Methods:" in text, f"детали пути не заполнились: {text!r}"
