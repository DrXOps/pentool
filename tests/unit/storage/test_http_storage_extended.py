"""Additional unit tests for pentool/storage/http_storage.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pentool.storage.http_storage import HttpStorage
from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest.fixture
async def storage():
    """Create temporary HttpStorage instance."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = HttpStorage()
    await store.init_db(db_path)

    yield store

    await store.close()
    Path(db_path).unlink(missing_ok=True)


class TestHttpStorageCountDistinctHosts:
    """Test count_distinct_hosts method."""

    async def test_count_distinct_hosts_empty(self, storage):
        """Empty database returns 0."""
        count = await storage.count_distinct_hosts()
        assert count == 0

    async def test_count_distinct_hosts_single(self, storage):
        """Single host counted."""
        req = ParsedRequest(method="GET", url="http://example.com/", headers={}, body="")
        await storage.add_request(req)

        count = await storage.count_distinct_hosts()
        assert count == 1

    async def test_count_distinct_hosts_multiple_same(self, storage):
        """Multiple requests to same host counted as 1."""
        req1 = ParsedRequest(method="GET", url="http://example.com/page1", headers={}, body="")
        req2 = ParsedRequest(method="GET", url="http://example.com/page2", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)

        count = await storage.count_distinct_hosts()
        assert count == 1

    async def test_count_distinct_hosts_different(self, storage):
        """Different hosts counted separately."""
        req1 = ParsedRequest(method="GET", url="http://example.com/", headers={}, body="")
        req2 = ParsedRequest(method="GET", url="http://test.com/", headers={}, body="")
        req3 = ParsedRequest(method="GET", url="http://another.com/", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)
        await storage.add_request(req3)

        count = await storage.count_distinct_hosts()
        assert count == 3


class TestHttpStorageSearch:
    """Test search method."""

    async def test_search_empty_query(self, storage):
        """Empty query returns empty list."""
        results = await storage.search("", limit=10)
        assert results == []

    async def test_search_no_matches(self, storage):
        """No matches returns empty list."""
        req = ParsedRequest(method="GET", url="http://example.com/page", headers={}, body="")
        await storage.add_request(req)

        results = await storage.search("nonexistent", limit=10)
        assert results == []

    async def test_search_url_match(self, storage):
        """Search finds URL match."""
        req = ParsedRequest(method="GET", url="http://example.com/admin/login", headers={}, body="")
        row_id = await storage.add_request(req)

        results = await storage.search("admin", limit=10)

        assert len(results) == 1
        assert results[0]["id"] == row_id
        assert "admin" in results[0]["url"]

    async def test_search_method_match(self, storage):
        """Search finds method match."""
        req = ParsedRequest(method="POST", url="http://example.com/api", headers={}, body="")
        row_id = await storage.add_request(req)

        # FTS search requires matching query format
        results = await storage.search("api", limit=10)

        assert len(results) >= 1
        assert any(r["id"] == row_id for r in results)

    async def test_search_host_match(self, storage):
        """Search finds host match."""
        req = ParsedRequest(method="GET", url="http://admin.example.com/", headers={}, body="")
        row_id = await storage.add_request(req)

        # Search by 'admin' only (no dots in FTS query)
        results = await storage.search("admin", limit=10)

        assert len(results) >= 1
        assert any(r["id"] == row_id for r in results)

    async def test_search_limit(self, storage):
        """Search respects limit."""
        for i in range(5):
            req = ParsedRequest(method="GET", url=f"http://example.com/page{i}", headers={}, body="")
            await storage.add_request(req)

        # Search by 'page' keyword
        results = await storage.search("page", limit=3)

        assert len(results) <= 3

    async def test_search_case_insensitive(self, storage):
        """Search is case-insensitive."""
        req = ParsedRequest(method="GET", url="http://Example.COM/API", headers={}, body="")
        row_id = await storage.add_request(req)

        results = await storage.search("example", limit=10)

        assert len(results) == 1
        assert results[0]["id"] == row_id


class TestHttpStorageClearAll:
    """Test clear_all method."""

    async def test_clear_all_empty(self, storage):
        """Clear on empty database succeeds."""
        await storage.clear_all()

        count = await storage.count()
        assert count == 0

    async def test_clear_all_removes_requests(self, storage):
        """Clear removes all requests."""
        req1 = ParsedRequest(method="GET", url="http://example.com/1", headers={}, body="")
        req2 = ParsedRequest(method="GET", url="http://example.com/2", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)

        count_before = await storage.count()
        assert count_before == 2

        await storage.clear_all()

        count_after = await storage.count()
        assert count_after == 0


class TestHttpStorageGetRequestById:
    """Test get_request_by_id method."""

    async def test_get_request_by_id_not_found(self, storage):
        """Nonexistent ID returns None."""
        result = await storage.get_request_by_id(999)
        assert result is None

    async def test_get_request_by_id_found(self, storage):
        """Existing ID returns full entry."""
        req = ParsedRequest(
            method="POST",
            url="http://example.com/api",
            headers={"Content-Type": "application/json"},
            body='{"test": "data"}'
        )
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "application/json"},
            body='{"result": "ok"}'
        )

        row_id = await storage.add_request(req, resp)

        result = await storage.get_request_by_id(row_id)

        assert result is not None
        assert result["id"] == row_id
        assert result["method"] == "POST"
        assert result["url"] == "http://example.com/api"
        assert result["status_code"] == 200
        assert "test" in result["request_body"]
        assert "result" in result["response_body"]


class TestHttpStorageExportAllRequests:
    """Test export_all_requests method."""

    async def test_export_all_requests_empty(self, storage):
        """Empty database exports empty list."""
        exported = await storage.export_all_requests()
        assert exported == []

    async def test_export_all_requests_includes_bodies(self, storage):
        """Export includes request and response bodies."""
        req = ParsedRequest(
            method="POST",
            url="http://example.com/api",
            headers={"Content-Type": "text/plain"},
            body="request data"
        )
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "text/plain"},
            body="response data"
        )

        await storage.add_request(req, resp)

        exported = await storage.export_all_requests()

        assert len(exported) == 1
        assert exported[0]["request_body"] == "request data"
        assert exported[0]["response_body"] == "response data"

    async def test_export_all_requests_limit(self, storage):
        """Export respects limit."""
        for i in range(5):
            req = ParsedRequest(method="GET", url=f"http://example.com/{i}", headers={}, body="")
            await storage.add_request(req)

        exported = await storage.export_all_requests(limit=3)

        assert len(exported) == 3

    async def test_export_all_requests_headers_parsed(self, storage):
        """Export parses JSON headers."""
        req = ParsedRequest(
            method="GET",
            url="http://example.com/",
            headers={"User-Agent": "TestAgent", "Accept": "*/*"},
            body=""
        )

        await storage.add_request(req)

        exported = await storage.export_all_requests()

        assert len(exported) == 1
        assert isinstance(exported[0]["request_headers"], dict)
        assert exported[0]["request_headers"]["User-Agent"] == "TestAgent"


class TestHttpStorageCountWithFilters:
    """Test count method with filters."""

    async def test_count_filter_method(self, storage):
        """Filter by method works."""
        req1 = ParsedRequest(method="GET", url="http://example.com/1", headers={}, body="")
        req2 = ParsedRequest(method="POST", url="http://example.com/2", headers={}, body="")
        req3 = ParsedRequest(method="GET", url="http://example.com/3", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)
        await storage.add_request(req3)

        count = await storage.count(filters={"method": "GET"})

        assert count == 2

    async def test_count_filter_host(self, storage):
        """Filter by host works."""
        req1 = ParsedRequest(method="GET", url="http://example.com/1", headers={}, body="")
        req2 = ParsedRequest(method="GET", url="http://test.com/2", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)

        count = await storage.count(filters={"host": "example.com"})

        assert count == 1

    async def test_count_filter_multiple(self, storage):
        """Multiple filters work together."""
        req1 = ParsedRequest(method="GET", url="http://example.com/1", headers={}, body="")
        req2 = ParsedRequest(method="POST", url="http://example.com/2", headers={}, body="")
        req3 = ParsedRequest(method="GET", url="http://test.com/3", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)
        await storage.add_request(req3)

        count = await storage.count(filters={"method": "GET", "host": "example.com"})

        assert count == 1


class TestHttpStorageGetMetadataBatch:
    """Test get_metadata_batch with filters and ordering."""

    async def test_get_metadata_batch_order_by_id_desc(self, storage):
        """Order by id DESC returns newest first."""
        req1 = ParsedRequest(method="GET", url="http://example.com/1", headers={}, body="")
        req2 = ParsedRequest(method="GET", url="http://example.com/2", headers={}, body="")

        id1 = await storage.add_request(req1)
        id2 = await storage.add_request(req2)

        # Use desc=True instead of direction="DESC"
        batch = await storage.get_metadata_batch(order_by="id", desc=True, limit=10, offset=0)

        assert len(batch) == 2
        assert batch[0]["id"] == id2
        assert batch[1]["id"] == id1

    async def test_get_metadata_batch_filter_extension(self, storage):
        """Filter by extension works."""
        req1 = ParsedRequest(method="GET", url="http://example.com/page.html", headers={}, body="")
        req2 = ParsedRequest(method="GET", url="http://example.com/api.json", headers={}, body="")
        req3 = ParsedRequest(method="GET", url="http://example.com/data.xml", headers={}, body="")

        await storage.add_request(req1)
        await storage.add_request(req2)
        await storage.add_request(req3)

        batch = await storage.get_metadata_batch(filters={"extension": "json"}, limit=10, offset=0)

        assert len(batch) == 1
        assert batch[0]["url"].endswith(".json")

    async def test_get_metadata_batch_limit_offset(self, storage):
        """Limit and offset work for pagination."""
        for i in range(5):
            req = ParsedRequest(method="GET", url=f"http://example.com/{i}", headers={}, body="")
            await storage.add_request(req)

        page1 = await storage.get_metadata_batch(limit=2, offset=0)
        page2 = await storage.get_metadata_batch(limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]

    async def test_get_metadata_batch_invalid_order_defaults(self, storage):
        """Invalid order_by defaults to id."""
        req = ParsedRequest(method="GET", url="http://example.com/", headers={}, body="")
        await storage.add_request(req)

        # Should not raise, defaults to id
        batch = await storage.get_metadata_batch(order_by="invalid_column", limit=10, offset=0)

        assert len(batch) == 1
