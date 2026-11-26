"""The history reload must wait for its table instead of failing silently (P1).

Reported: switching Proxy sub-tabs back and forth emptied the history until a filter was
applied. Cause: `_reload_table` cached the rows, then queried `#request-list`; on a rebuilt
tab the widget mounts a frame later, the query raised `NoMatches`, the broad handler logged and
the table stayed empty.

The mechanism is tested directly: a container whose child appears after a delay, and the
helper must find it (and time out with a warning when the child never comes).
"""

from __future__ import annotations

import pytest
from textual.widgets import DataTable

from pentool.tui.screens.proxy.screen import ProxyScreen


class _Host(ProxyScreen):
    """ProxyScreen with only the helper under test (no compose, no project)."""

    def __init__(self) -> None:  # noqa: D401 - test double
        self._children: list = []

    def query_one(self, selector, cls=None):  # type: ignore[override]
        for child in self._children:
            if getattr(child, "id", None) == selector.lstrip("#"):
                return child
        from textual.css.query import NoMatches

        raise NoMatches(f"No nodes match {selector!r}")


@pytest.mark.asyncio
async def test_helper_waits_until_the_table_appears() -> None:
    host = _Host()
    table = DataTable(id="request-list")

    # The table appears after ~60 ms, like a lazily mounted sub-tab body.
    import asyncio

    async def mount_later() -> None:
        await asyncio.sleep(0.06)
        host._children.append(table)

    task = asyncio.create_task(mount_later())
    found = await host._table_or_wait("#request-list", timeout=1.0)
    await task

    assert found is table, "перезагрузка истории должна дождаться таблицы, а не падать"


@pytest.mark.asyncio
async def test_helper_gives_up_loudly_when_the_table_never_mounts() -> None:
    host = _Host()
    assert await host._table_or_wait("#request-list", timeout=0.1) is None
