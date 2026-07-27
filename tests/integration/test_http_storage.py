"""Integration tests: HttpStorage — SQLite storage for HTTP requests/responses."""

from __future__ import annotations

import pytest
import pytest_asyncio
from pathlib import Path

from pentool.storage.http_storage import HttpStorage
from pentool.utils.parser import ParsedRequest, ParsedResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_req(
    url: str = "http://example.com/path",
    method: str = "GET",
    headers: dict | None = None,
    body: str = "",
) -> ParsedRequest:
    return ParsedRequest(
        method=method,
        url=url,
        headers=headers or {"Host": "example.com", "User-Agent": "test/1.0"},
        body=body,
    )


def _make_resp(
    status: int = 200,
    body: str = "OK",
    content_type: str = "text/html",
) -> ParsedResponse:
    return ParsedResponse(
        status=status,
        reason="OK",
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
        body=body,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def storage(tmp_path: Path) -> HttpStorage:
    s = HttpStorage()
    await s.init_db(str(tmp_path / "history.db"))
    yield s
    await s.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestHttpStorageInit:

    async def test_init_db_creates_table(self, tmp_path: Path) -> None:
        """init_db создаёт таблицу requests."""
        import aiosqlite
        db_path = str(tmp_path / "init_test.db")
        s = HttpStorage()
        await s.init_db(db_path)

        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='requests'"
            ) as cur:
                row = await cur.fetchone()
        await s.close()

        assert row is not None
        assert row[0] == "requests"


@pytest.mark.integration
class TestHttpStorageAddRequest:

    async def test_add_request_returns_int(self, storage: HttpStorage) -> None:
        """add_request возвращает int row_id."""
        row_id = await storage.add_request(_make_req())
        assert isinstance(row_id, int)
        assert row_id >= 1

    async def test_add_request_multiple_increments(self, storage: HttpStorage) -> None:
        """Последовательные вставки дают разные row_id."""
        id1 = await storage.add_request(_make_req())
        id2 = await storage.add_request(_make_req())
        assert id2 > id1

    async def test_add_request_with_response_saves_status(self, storage: HttpStorage) -> None:
        """add_request с ответом сохраняет status_code."""
        req = _make_req()
        resp = _make_resp(status=404, body="Not Found", content_type="text/html")
        row_id = await storage.add_request(req, resp)

        entry = await storage.get_full_entry(row_id)
        assert entry is not None
        assert entry["status_code"] == 404

    async def test_add_request_with_response_saves_length(self, storage: HttpStorage) -> None:
        """add_request с ответом сохраняет length."""
        body = "Hello World"
        req = _make_req()
        resp = _make_resp(status=200, body=body)
        row_id = await storage.add_request(req, resp)

        entry = await storage.get_full_entry(row_id)
        assert entry is not None
        assert entry["length"] == len(body)

    async def test_add_request_with_response_saves_mime_type(self, storage: HttpStorage) -> None:
        """add_request с ответом сохраняет mime_type."""
        req = _make_req()
        resp = _make_resp(status=200, content_type="application/json")
        row_id = await storage.add_request(req, resp)

        entry = await storage.get_full_entry(row_id)
        assert entry is not None
        assert entry["mime_type"] == "application/json"

    async def test_add_request_websocket_flag(self, storage: HttpStorage) -> None:
        """add_request с is_websocket=True сохраняет флаг."""
        row_id = await storage.add_request(_make_req(), is_websocket=True)
        entry = await storage.get_full_entry(row_id)
        assert entry is not None
        assert entry["is_websocket"] == 1


@pytest.mark.integration
class TestHttpStorageGetMetadataBatch:

    async def test_get_metadata_batch_returns_list_of_dicts(self, storage: HttpStorage) -> None:
        """get_metadata_batch возвращает список dict."""
        await storage.add_request(_make_req())
        rows = await storage.get_metadata_batch()
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert isinstance(rows[0], dict)

    async def test_get_metadata_batch_filter_host(self, storage: HttpStorage) -> None:
        """get_metadata_batch фильтрует по host."""
        await storage.add_request(_make_req("http://example.com/a"))
        await storage.add_request(_make_req("http://other.org/b"))

        rows = await storage.get_metadata_batch(filters={"host": "example.com"})
        assert all("example.com" in r["host"] for r in rows)
        hosts = {r["host"] for r in rows}
        assert "other.org" not in hosts

    async def test_get_metadata_batch_filter_method(self, storage: HttpStorage) -> None:
        """get_metadata_batch фильтрует по method."""
        await storage.add_request(_make_req(method="GET"))
        await storage.add_request(_make_req(method="POST"))

        rows = await storage.get_metadata_batch(filters={"method": "POST"})
        assert all(r["method"] == "POST" for r in rows)

    async def test_get_metadata_batch_filter_status_code_range(self, storage: HttpStorage) -> None:
        """get_metadata_batch фильтрует по диапазону status_code."""
        await storage.add_request(_make_req(), _make_resp(status=200))
        await storage.add_request(_make_req(), _make_resp(status=301))
        await storage.add_request(_make_req(), _make_resp(status=404))

        rows = await storage.get_metadata_batch(filters={"status_code": [300, 399]})
        assert all(300 <= r["status_code"] <= 399 for r in rows)


@pytest.mark.integration
class TestHttpStorageGetFullEntry:

    async def test_get_full_entry_returns_dict(self, storage: HttpStorage) -> None:
        """get_full_entry возвращает dict."""
        row_id = await storage.add_request(_make_req())
        entry = await storage.get_full_entry(row_id)
        assert isinstance(entry, dict)

    async def test_get_full_entry_request_headers_as_dict(self, storage: HttpStorage) -> None:
        """get_full_entry возвращает request_headers как dict, не JSON-строку."""
        headers = {"Host": "example.com", "X-Custom": "value"}
        row_id = await storage.add_request(_make_req(headers=headers))
        entry = await storage.get_full_entry(row_id)
        assert isinstance(entry["request_headers"], dict)
        assert entry["request_headers"].get("Host") == "example.com"

    async def test_get_full_entry_response_headers_as_dict(self, storage: HttpStorage) -> None:
        """get_full_entry возвращает response_headers как dict."""
        row_id = await storage.add_request(_make_req(), _make_resp())
        entry = await storage.get_full_entry(row_id)
        assert isinstance(entry["response_headers"], dict)

    async def test_get_full_entry_missing_returns_none(self, storage: HttpStorage) -> None:
        """get_full_entry возвращает None для несуществующего id."""
        result = await storage.get_full_entry(99999)
        assert result is None


@pytest.mark.integration
class TestHttpStorageDelete:

    async def test_delete_removes_record(self, storage: HttpStorage) -> None:
        """delete удаляет запись."""
        row_id = await storage.add_request(_make_req())
        await storage.delete(row_id)
        result = await storage.get_full_entry(row_id)
        assert result is None

    async def test_delete_does_not_affect_other_records(self, storage: HttpStorage) -> None:
        """delete не затрагивает другие записи."""
        id1 = await storage.add_request(_make_req())
        id2 = await storage.add_request(_make_req())
        await storage.delete(id1)
        assert await storage.get_full_entry(id2) is not None


@pytest.mark.integration
class TestHttpStorageCount:

    async def test_count_returns_correct_number(self, storage: HttpStorage) -> None:
        """count возвращает правильное число."""
        for _ in range(3):
            await storage.add_request(_make_req())
        n = await storage.count()
        assert n == 3

    async def test_count_with_filter(self, storage: HttpStorage) -> None:
        """count с фильтром считает только подходящие записи."""
        await storage.add_request(_make_req(method="GET"))
        await storage.add_request(_make_req(method="POST"))
        n = await storage.count(filters={"method": "GET"})
        assert n == 1

    async def test_count_distinct_hosts(self, storage: HttpStorage) -> None:
        """count_distinct_hosts возвращает число уникальных хостов."""
        await storage.add_request(_make_req("http://alpha.com/a"))
        await storage.add_request(_make_req("http://alpha.com/b"))
        await storage.add_request(_make_req("http://beta.com/c"))
        n = await storage.count_distinct_hosts()
        assert n == 2


@pytest.mark.integration
class TestHttpStorageSearch:

    async def test_search_fulltext(self, storage: HttpStorage) -> None:
        """search выполняет полнотекстовый поиск."""
        await storage.add_request(_make_req("http://example.com/secretpage"))
        await storage.add_request(_make_req("http://other.org/notsecret"))
        results = await storage.search("secretpage")
        assert len(results) >= 1
        assert any("secretpage" in r["url"] for r in results)

    async def test_search_no_results(self, storage: HttpStorage) -> None:
        """search возвращает пустой список при отсутствии совпадений."""
        await storage.add_request(_make_req("http://example.com/hello"))
        results = await storage.search("zzznomatch999")
        assert results == []


@pytest.mark.integration
class TestHttpStorageClearAll:

    async def test_clear_all_empties_table(self, storage: HttpStorage) -> None:
        """clear_all очищает таблицу."""
        for _ in range(5):
            await storage.add_request(_make_req())
        await storage.clear_all()
        n = await storage.count()
        assert n == 0


@pytest.mark.integration
class TestHttpStorageSwitchDb:

    async def test_switch_db(self, tmp_path: Path) -> None:
        """switch_db переключает базу данных."""
        s = HttpStorage()
        db1 = str(tmp_path / "db1.db")
        db2 = str(tmp_path / "db2.db")
        await s.init_db(db1)

        await s.add_request(_make_req("http://db1host.com/"))
        n1 = await s.count()
        assert n1 == 1

        await s.switch_db(db2)
        n2 = await s.count()
        assert n2 == 0  # новая БД пустая

        await s.close()


@pytest.mark.integration
class TestHttpStorageWebsocket:

    async def test_is_websocket_filter_false(self, storage: HttpStorage) -> None:
        """is_websocket фильтр возвращает только не-WS записи."""
        await storage.add_request(_make_req(), is_websocket=False)
        await storage.add_request(_make_req(), is_websocket=True)

        rows = await storage.get_metadata_batch(filters={"is_websocket": False})
        assert all(r.get("id") is not None for r in rows)
        # Проверяем через get_full_entry что в результатах нет WS-записей
        for r in rows:
            entry = await storage.get_full_entry(r["id"])
            assert entry["is_websocket"] == 0

    async def test_is_websocket_filter_true(self, storage: HttpStorage) -> None:
        """is_websocket фильтр возвращает только WS-записи."""
        await storage.add_request(_make_req(), is_websocket=False)
        ws_id = await storage.add_request(_make_req(), is_websocket=True)

        rows = await storage.get_metadata_batch(filters={"is_websocket": True})
        ids = {r["id"] for r in rows}
        assert ws_id in ids


@pytest.mark.integration
class TestHttpStorageGetRequestById:

    async def test_get_request_by_id_alias(self, storage: HttpStorage) -> None:
        """get_request_by_id является алиасом get_full_entry."""
        row_id = await storage.add_request(_make_req())
        entry_via_full = await storage.get_full_entry(row_id)
        entry_via_alias = await storage.get_request_by_id(row_id)
        assert entry_via_full == entry_via_alias

    async def test_get_request_by_id_missing_returns_none(self, storage: HttpStorage) -> None:
        """get_request_by_id возвращает None для несуществующего id."""
        result = await storage.get_request_by_id(99999)
        assert result is None
