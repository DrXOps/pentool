"""Tests for pentool/api/spider_api.py — auto session-discovery for crawling."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pentool.api.spider_api import SpiderAPI, SpiderConfig
from pentool.modules.spider import SpiderResult
from pentool.storage.http_storage import HttpStorage
from pentool.utils.parser import ParsedRequest


@pytest.fixture
async def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


async def _seed_request(db_path: str, url: str, headers: dict) -> None:
    """Insert one request row into a project DB, as Proxy would."""
    storage = HttpStorage()
    await storage.init_db(db_path)
    try:
        req = ParsedRequest(method="GET", url=url, headers=headers, body="")
        await storage.add_request(req)
    finally:
        await storage.close()


class TestDiscoverAuthHeaders:
    async def test_no_db_path_returns_empty(self):
        api = SpiderAPI()
        result = await api._discover_auth_headers("https://example.com/", "")
        assert result == {}

    async def test_no_matching_host_returns_empty(self, db_path):
        await _seed_request(
            db_path, "https://other.com/", {"Cookie": "sid=1", "Host": "other.com"}
        )
        api = SpiderAPI()
        result = await api._discover_auth_headers("https://example.com/", db_path)
        assert result == {}

    async def test_finds_cookie_for_matching_host(self, db_path):
        await _seed_request(
            db_path,
            "https://dvwa.local:7474/vulnerabilities/xss_r/",
            {"Cookie": "PHPSESSID=abc123; security=low", "Host": "dvwa.local:7474"},
        )
        api = SpiderAPI()
        result = await api._discover_auth_headers("https://dvwa.local:7474/", db_path)
        assert result.get("Cookie") == "PHPSESSID=abc123; security=low"

    async def test_matches_regardless_of_port(self, db_path):
        """Host matching ignores :port, mirroring Proxy/Target scope convention."""
        await _seed_request(
            db_path,
            "http://dvwa.local:7474/login.php",
            {"Cookie": "sid=xyz"},
        )
        api = SpiderAPI()
        result = await api._discover_auth_headers("http://dvwa.local/", db_path)
        assert result.get("Cookie") == "sid=xyz"

    async def test_ignores_non_auth_headers(self, db_path):
        await _seed_request(
            db_path,
            "https://example.com/",
            {"Accept": "text/html", "User-Agent": "curl/8.0"},
        )
        api = SpiderAPI()
        result = await api._discover_auth_headers("https://example.com/", db_path)
        assert result == {}

    async def test_uses_most_recent_row_for_host(self, db_path):
        await _seed_request(db_path, "https://example.com/a", {"Cookie": "old=1"})
        await _seed_request(db_path, "https://example.com/b", {"Cookie": "new=2"})
        api = SpiderAPI()
        result = await api._discover_auth_headers("https://example.com/", db_path)
        assert result.get("Cookie") == "new=2"

    async def test_nonexistent_db_path_returns_empty_no_raise(self):
        api = SpiderAPI()
        result = await api._discover_auth_headers(
            "https://example.com/", "/nonexistent/path/does/not/exist.db"
        )
        assert result == {}

    async def test_url_without_host_returns_empty(self, db_path):
        api = SpiderAPI()
        result = await api._discover_auth_headers("not-a-url", db_path)
        assert result == {}


class TestCrawlPassesDiscoveredHeaders:
    async def test_crawl_merges_discovered_headers_into_spider(self, db_path):
        await _seed_request(
            db_path,
            "https://dvwa.local/vulnerabilities/xss_r/",
            {"Cookie": "PHPSESSID=abc"},
        )
        api = SpiderAPI(config=SpiderConfig())
        with patch("pentool.api.spider_api.AsyncSpider") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.crawl = AsyncMock(
                return_value=SpiderResult(base_url="https://dvwa.local/")
            )
            await api.crawl("https://dvwa.local/", db_path=db_path)
            _, kwargs = mock_cls.call_args
            assert kwargs["extra_headers"].get("Cookie") == "PHPSESSID=abc"

    async def test_explicit_extra_headers_win_over_discovered(self, db_path):
        await _seed_request(
            db_path,
            "https://dvwa.local/vulnerabilities/xss_r/",
            {"Cookie": "PHPSESSID=discovered"},
        )
        api = SpiderAPI(config=SpiderConfig())
        with patch("pentool.api.spider_api.AsyncSpider") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.crawl = AsyncMock(
                return_value=SpiderResult(base_url="https://dvwa.local/")
            )
            await api.crawl(
                "https://dvwa.local/",
                extra_headers={"Cookie": "PHPSESSID=explicit"},
                db_path=db_path,
            )
            _, kwargs = mock_cls.call_args
            assert kwargs["extra_headers"].get("Cookie") == "PHPSESSID=explicit"

    async def test_crawl_without_db_path_has_no_discovered_headers(self):
        api = SpiderAPI(config=SpiderConfig())
        with patch("pentool.api.spider_api.AsyncSpider") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.crawl = AsyncMock(
                return_value=SpiderResult(base_url="https://example.com/")
            )
            await api.crawl("https://example.com/")
            _, kwargs = mock_cls.call_args
            assert kwargs["extra_headers"] == {}
