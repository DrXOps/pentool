"""Unit-тесты: storage/lru_cache.py и storage/http_storage.py

Покрывает: LRUCache (eviction, put, get), HttpStorage (CRUD, FTS5, фильтры).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse


class TestLRUCache:
    def test_put_and_get(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache(max_size=10)
        cache.put(1, {"data": "value"})
        assert cache.get(1) == {"data": "value"}

    def test_miss_returns_none(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache()
        assert cache.get(999) is None

    def test_evicts_least_recently_used(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache(max_size=2)
        cache.put(1, "a")
        cache.put(2, "b")
        cache.get(1)       # 1 — самый свежий
        cache.put(3, "c")  # 2 вытесняется
        assert cache.get(1) == "a"
        assert cache.get(2) is None
        assert cache.get(3) == "c"

    def test_update_moves_to_front(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache(max_size=2)
        cache.put(1, "old")
        cache.put(2, "b")
        cache.put(1, "new")  # обновляем 1 → 2 теперь самый старый
        cache.put(3, "c")    # 2 вытесняется
        assert cache.get(1) == "new"
        assert cache.get(2) is None

    def test_capacity_of_one(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache(max_size=1)
        cache.put(1, "a")
        cache.put(2, "b")
        assert cache.get(1) is None
        assert cache.get(2) == "b"

    def test_invalidate_removes_entry(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache()
        cache.put(1, "data")
        cache.invalidate(1)
        assert cache.get(1) is None

    def test_clear_empties_cache(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache()
        cache.put(1, "a")
        cache.put(2, "b")
        cache.clear()
        assert cache.get(1) is None
        assert cache.get(2) is None

    def test_many_items(self) -> None:
        from pentool.storage.lru_cache import LRUCache
        cache = LRUCache(max_size=100)
        for i in range(100):
            cache.put(i, f"value_{i}")
        for i in range(100):
            assert cache.get(i) == f"value_{i}"


class TestHttpStorage:
    @pytest.mark.asyncio
    async def test_init_creates_tables(self, tmp_path: Path) -> None:
        from pentool.storage.http_storage import HttpStorage
        storage = HttpStorage()
        await storage.init_db(str(tmp_path / "test.db"))
        count = await storage.count()
        assert count == 0
        await storage.close()

    @pytest.mark.asyncio
    async def test_add_request_returns_id(self, http_storage) -> None:
        req = ParsedRequest(
            method="GET",
            url="http://example.com/api",
            headers={"Host": "example.com"},
        )
        row_id = await http_storage.add_request(req)
        assert isinstance(row_id, int)
        assert row_id > 0

    @pytest.mark.asyncio
    async def test_add_request_with_response(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK", body="hello")
        row_id = await http_storage.add_request(req, resp)
        record = await http_storage.get_full_entry(row_id)
        assert record is not None
        assert record["status_code"] == 200

    @pytest.mark.asyncio
    async def test_count_increments(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        await http_storage.add_request(req)
        await http_storage.add_request(req)
        assert await http_storage.count() == 2

    @pytest.mark.asyncio
    async def test_get_request_fields(self, http_storage) -> None:
        req = ParsedRequest(
            method="POST",
            url="http://example.com/login",
            headers={"Host": "example.com", "Content-Type": "application/json"},
            body='{"user":"admin"}',
        )
        resp = ParsedResponse(status=302, reason="Found", headers={}, body="")
        row_id = await http_storage.add_request(req, resp)
        record = await http_storage.get_full_entry(row_id)
        assert record["method"] == "POST"
        assert record["host"] == "example.com"
        assert record["status_code"] == 302

    @pytest.mark.asyncio
    async def test_get_request_nonexistent_returns_none(self, http_storage) -> None:
        result = await http_storage.get_full_entry(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_metadata_batch_returns_list(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        await http_storage.add_request(req)
        rows = await http_storage.get_metadata_batch()
        assert isinstance(rows, list)
        assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_filter_by_method(self, http_storage) -> None:
        get_req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        post_req = ParsedRequest(method="POST", url="http://example.com/login", headers={})
        await http_storage.add_request(get_req)
        await http_storage.add_request(post_req)
        rows = await http_storage.get_metadata_batch(filters={"method": "POST"})
        assert all(r["method"] == "POST" for r in rows)

    @pytest.mark.asyncio
    async def test_filter_by_host(self, http_storage) -> None:
        req1 = ParsedRequest(method="GET", url="http://alpha.com/", headers={"Host": "alpha.com"})
        req2 = ParsedRequest(method="GET", url="http://beta.com/", headers={"Host": "beta.com"})
        await http_storage.add_request(req1)
        await http_storage.add_request(req2)
        rows = await http_storage.get_metadata_batch(filters={"host": "alpha.com"})
        assert all("alpha" in r["host"] for r in rows)

    @pytest.mark.asyncio
    async def test_filter_by_status(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp_200 = ParsedResponse(status=200, reason="OK")
        resp_404 = ParsedResponse(status=404, reason="Not Found")
        await http_storage.add_request(req, resp_200)
        await http_storage.add_request(req, resp_404)
        rows = await http_storage.get_metadata_batch(filters={"status_code": 404})
        assert all(r["status_code"] == 404 for r in rows)

    @pytest.mark.asyncio
    async def test_delete_request(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        row_id = await http_storage.add_request(req)
        await http_storage.delete(row_id)
        assert await http_storage.get_full_entry(row_id) is None
        assert await http_storage.count() == 0

    @pytest.mark.asyncio
    async def test_clear_all(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        await http_storage.add_request(req)
        await http_storage.add_request(req)
        await http_storage.clear_all()
        assert await http_storage.count() == 0

    @pytest.mark.asyncio
    async def test_fts_search_finds_url(self, http_storage) -> None:
        req = ParsedRequest(
            method="GET",
            url="http://example.com/secret-admin-panel",
            headers={"Host": "example.com"},
        )
        await http_storage.add_request(req)
        results = await http_storage.search("secret")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_fts_search_no_results(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        await http_storage.add_request(req)
        results = await http_storage.search("zzzzz_nonexistent_term_zzzzz")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_host_extracted_from_url(self, http_storage) -> None:
        req = ParsedRequest(
            method="GET",
            url="http://target.example.com/path",
            headers={},
        )
        row_id = await http_storage.add_request(req)
        rows = await http_storage.get_metadata_batch()
        matching = [r for r in rows if r["id"] == row_id]
        assert len(matching) == 1
        assert "example.com" in matching[0]["host"]

    @pytest.mark.asyncio
    async def test_has_params_detected(self, http_storage) -> None:
        req = ParsedRequest(
            method="GET",
            url="http://example.com/search?q=test&page=1",
            headers={},
        )
        row_id = await http_storage.add_request(req)
        record = await http_storage.get_full_entry(row_id)
        assert record["has_params"] == 1

    @pytest.mark.asyncio
    async def test_pagination(self, http_storage) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        for _ in range(10):
            await http_storage.add_request(req)
        page1 = await http_storage.get_metadata_batch(limit=5, offset=0)
        page2 = await http_storage.get_metadata_batch(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        ids1 = {r["id"] for r in page1}
        ids2 = {r["id"] for r in page2}
        assert ids1.isdisjoint(ids2)
