"""Unit tests: registry of Repeater tabs (`repeater_tabs`).

`repeater_entries` is the send history — one row per send, append-only. The set
of open tabs is a separate table keyed by `tab_uid`, exactly like
`scanner_tabs` and `intruder_state`. The split matters because F-053 was
exactly the confusion between the two: the tab set was derived from the last
rows of the history, so a closed tab came back after a restart, and closing a
tab (correctly) did not touch the log.

Covered here: upsert by uid, rename keeping one row, ordering, deletion of one
tab, and the invariant that deletion leaves the history alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest_asyncio.fixture
async def repeater(tmp_path: Path):
    from pentool.core.db_schema import init_db
    from pentool.modules.repeater import Repeater

    db_path = str(tmp_path / "tabs.db")
    await init_db(db_path)
    rp = Repeater(db_path=db_path)
    try:
        yield rp
    finally:
        await rp.close()


@pytest.mark.asyncio
async def test_no_tabs_initially(repeater) -> None:
    assert await repeater.get_tabs() == []


@pytest.mark.asyncio
async def test_save_and_read_back(repeater) -> None:
    await repeater.save_tab("uid-a", "Tab 1", "GET /a HTTP/1.1\r\nHost: a\r\n\r\n")
    tabs = await repeater.get_tabs()
    assert len(tabs) == 1
    assert tabs[0]["tab_uid"] == "uid-a"
    assert tabs[0]["tab_name"] == "Tab 1"
    assert "GET /a" in tabs[0]["request_text"]


@pytest.mark.asyncio
async def test_saving_the_same_uid_updates_instead_of_duplicating(repeater) -> None:
    await repeater.save_tab("uid-a", "Tab 1", "GET /one HTTP/1.1\r\n\r\n")
    await repeater.save_tab("uid-a", "Tab 1", "GET /two HTTP/1.1\r\n\r\n")

    tabs = await repeater.get_tabs()
    assert len(tabs) == 1, "вкладка продублировалась: upsert по tab_uid не сработал"
    assert "GET /two" in tabs[0]["request_text"]


@pytest.mark.asyncio
async def test_rename_keeps_one_row(repeater) -> None:
    """The name is cosmetic: a rename must not spawn a new tab."""
    await repeater.save_tab("uid-a", "Tab 1", "GET /a HTTP/1.1\r\n\r\n")
    await repeater.save_tab("uid-a", "Login", "GET /a HTTP/1.1\r\n\r\n")

    tabs = await repeater.get_tabs()
    assert len(tabs) == 1
    assert tabs[0]["tab_name"] == "Login"


@pytest.mark.asyncio
async def test_tabs_keep_their_order(repeater) -> None:
    await repeater.save_tab("uid-b", "B", "GET /b HTTP/1.1\r\n\r\n", sort_order=1)
    await repeater.save_tab("uid-a", "A", "GET /a HTTP/1.1\r\n\r\n", sort_order=0)

    assert [t["tab_uid"] for t in await repeater.get_tabs()] == ["uid-a", "uid-b"]


@pytest.mark.asyncio
async def test_delete_removes_only_that_tab(repeater) -> None:
    await repeater.save_tab("uid-a", "A", "GET /a HTTP/1.1\r\n\r\n", sort_order=0)
    await repeater.save_tab("uid-b", "B", "GET /b HTTP/1.1\r\n\r\n", sort_order=1)

    await repeater.delete_tab("uid-a")

    assert [t["tab_uid"] for t in await repeater.get_tabs()] == ["uid-b"]


@pytest.mark.asyncio
async def test_delete_does_not_touch_the_send_history(repeater) -> None:
    """Closing a tab is not deleting the send log (F-053)."""
    req = ParsedRequest(method="GET", url="http://example.com/", headers={})
    resp = ParsedResponse(status=200, reason="OK", body="OK")
    await repeater.save_to_history(req, resp, tab_name="Tab 1")
    await repeater.save_tab("uid-a", "Tab 1", "GET / HTTP/1.1\r\n\r\n")

    await repeater.delete_tab("uid-a")

    assert await repeater.get_tabs() == [], "строка вкладки осталась"
    history = await repeater.get_history()
    assert len(history) == 1, "удаление вкладки стёрло историю отправок"


@pytest.mark.asyncio
async def test_empty_uid_is_ignored(repeater) -> None:
    """Without a uid there is nothing to match the row against — a no-op beats an orphan row."""
    await repeater.save_tab("", "Tab 1", "GET / HTTP/1.1\r\n\r\n")
    assert await repeater.get_tabs() == []


@pytest.mark.asyncio
async def test_seed_builds_the_registry_from_history_once(repeater) -> None:
    """Migration of an old project: tabs are built from history exactly once."""
    req = ParsedRequest(method="GET", url="http://example.com/a", headers={})
    resp = ParsedResponse(status=200, reason="OK", body="OK")
    await repeater.save_to_history(req, resp, tab_name="Login")
    await repeater.save_to_history(req, resp, tab_name="Search")
    # The later entry under the same name must win.
    req_new = ParsedRequest(method="PUT", url="http://example.com/login2", headers={})
    await repeater.save_to_history(req_new, resp, tab_name="Login")

    seeded = await repeater.seed_tabs_from_history()

    assert [t["tab_name"] for t in seeded] == ["Login", "Search"]
    assert "PUT" in seeded[0]["request_text"], "взята не самая свежая запись имени"
    assert all(t["tab_uid"] for t in seeded), "у собранных вкладок нет uid"

    before = [t["tab_uid"] for t in seeded]
    again = await repeater.seed_tabs_from_history()
    assert [t["tab_uid"] for t in again] == before, "повторная миграция пересобрала реестр"


@pytest.mark.asyncio
async def test_seed_does_nothing_without_history(repeater) -> None:
    assert await repeater.seed_tabs_from_history() == []
    assert await repeater.get_tabs() == []


@pytest.mark.asyncio
async def test_seed_does_not_override_an_existing_registry(repeater) -> None:
    req = ParsedRequest(method="GET", url="http://example.com/a", headers={})
    resp = ParsedResponse(status=200, reason="OK", body="OK")
    await repeater.save_to_history(req, resp, tab_name="FromHistory")
    await repeater.save_tab("uid-a", "Mine", "GET /mine HTTP/1.1\r\n\r\n")

    tabs = await repeater.seed_tabs_from_history()

    assert [t["tab_name"] for t in tabs] == ["Mine"], "миграция перезаписала живой реестр"
