"""Unit tests: modules/target.py + api/target_api.py (Stage 9.5).

Covers: SiteNode, SiteMap (add_request, scope, tree, save/load),
           TargetAPI, JSON export.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio

from pentool.modules.target import SiteMap, SiteNode
from pentool.utils.parser import ParsedRequest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sitemap(test_db: str):
    sm = SiteMap(db_path=test_db)
    try:
        yield sm
    finally:
        await sm.close()


def make_req(url: str, method: str = "GET") -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers={"Host": "example.com"}, body="")


# ─── TestSiteNode ─────────────────────────────────────────────────────────────

class TestSiteNode:
    def test_to_dict_and_from_dict(self) -> None:
        node = SiteNode(
            host="example.com",
            path="/api/users",
            methods={"GET", "POST"},
            request_count=5,
        )
        d = node.to_dict()
        restored = SiteNode.from_dict(d)
        assert restored.host == "example.com"
        assert restored.path == "/api/users"
        assert "GET" in restored.methods
        assert restored.request_count == 5

    def test_from_dict_bad_timestamp(self) -> None:
        d = {
            "id": "x", "host": "h", "path": "/",
            "methods": [], "request_count": 0, "last_seen": "bad",
        }
        node = SiteNode.from_dict(d)
        assert isinstance(node.last_seen, datetime)


# ─── TestSiteMap ──────────────────────────────────────────────────────────────

class TestSiteMap:
    def test_add_request_creates_host(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://example.com/api"))
        assert "example.com" in sitemap.get_hosts()

    def test_add_request_creates_path(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://example.com/api/users"))
        nodes = sitemap.get_paths("example.com")
        paths = [n.path for n in nodes]
        assert "/api/users" in paths

    def test_add_request_increments_count(self, sitemap: SiteMap) -> None:
        url = "http://example.com/login"
        sitemap.add_request(make_req(url, "GET"))
        sitemap.add_request(make_req(url, "POST"))
        sitemap.add_request(make_req(url, "POST"))
        nodes = sitemap.get_paths("example.com")
        node = next(n for n in nodes if n.path == "/login")
        assert node.request_count == 3

    def test_add_request_collects_methods(self, sitemap: SiteMap) -> None:
        url = "http://example.com/form"
        sitemap.add_request(make_req(url, "GET"))
        sitemap.add_request(make_req(url, "POST"))
        node = sitemap.get_paths("example.com")[0]
        assert "GET" in node.methods
        assert "POST" in node.methods

    def test_get_tree_structure(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://a.com/page1"))
        sitemap.add_request(make_req("http://b.com/page2"))
        tree = sitemap.get_tree()
        assert "a.com" in tree
        assert "b.com" in tree

    def test_set_in_scope(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://example.com/"))
        sitemap.set_in_scope("example.com", True)
        assert sitemap.is_in_scope("example.com")

    def test_get_scope_returns_in_scope_hosts(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://a.com/"))
        sitemap.add_request(make_req("http://b.com/"))
        sitemap.set_in_scope("a.com", True)
        scope = sitemap.get_scope()
        assert "a.com" in scope
        assert "b.com" not in scope

    def test_set_in_scope_before_any_traffic(self, sitemap: SiteMap) -> None:
        """Scope added for a host with no traffic yet must not be a no-op.

        Regression test: previously set_in_scope() only flagged existing
        nodes, so a host added to scope from Proxy before Target had seen
        any matching traffic silently lost the scope flag.
        """
        sitemap.set_in_scope("not-seen-yet.com", True)
        assert sitemap.is_in_scope("not-seen-yet.com")
        # Traffic arriving afterwards must inherit the scope flag.
        sitemap.add_request(make_req("http://not-seen-yet.com/api"))
        node = sitemap.get_paths("not-seen-yet.com")[0]
        assert node.in_scope is True
        assert "not-seen-yet.com" in sitemap.get_scope()

    def test_set_in_scope_ignores_port_mismatch(self, sitemap: SiteMap) -> None:
        """A host:port node must be recognized as in-scope by its bare host.

        Regression test: SiteMap keys nodes by netloc (host:port), while
        Proxy/the Scope dialog compare port-less host names — previously
        this mismatch made set_in_scope() a silent no-op for such hosts.
        """
        sitemap.add_request(make_req("http://example.com:8443/api"))
        sitemap.set_in_scope("example.com", True)
        assert sitemap.is_in_scope("example.com:8443")
        node = sitemap.get_paths("example.com:8443")[0]
        assert node.in_scope is True

    def test_clear(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://example.com/"))
        sitemap.clear()
        assert sitemap.get_hosts() == []

    def test_get_request_count(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://example.com/a"))
        sitemap.add_request(make_req("http://example.com/b"))
        assert sitemap.get_request_count("example.com") == 2

    def test_add_request_invalid_url(self, sitemap: SiteMap) -> None:
        # Should not crash on bad URL
        req = ParsedRequest(method="GET", url="not-a-url", headers={}, body="")
        sitemap.add_request(req)  # no exception

    @pytest.mark.asyncio
    async def test_save_and_load(self, test_db: str) -> None:
        sm = SiteMap(db_path=test_db)
        sm.add_request(make_req("http://saved.com/api"))
        sm.set_in_scope("saved.com", True)
        try:
            await sm.save()

            sm2 = SiteMap(db_path=test_db)
            try:
                await sm2.load()
                assert "saved.com" in sm2.get_hosts()
                assert sm2.is_in_scope("saved.com")
            finally:
                await sm2.close()
        finally:
            await sm.close()

    def test_export_json(self, sitemap: SiteMap) -> None:
        sitemap.add_request(make_req("http://example.com/api"))
        data = sitemap.export_json()
        assert "example.com" in data
        assert isinstance(data["example.com"], list)


# ─── TestTargetAPI ────────────────────────────────────────────────────────────

class TestTargetAPI:
    def test_get_tree(self, test_db: str) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path=test_db)
        api.add_request(make_req("http://example.com/test"))
        tree = api.get_tree()
        assert "example.com" in tree

    def test_set_in_scope(self, test_db: str) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path=test_db)
        api.add_request(make_req("http://example.com/"))
        api.set_in_scope("example.com", True)
        scope = api.get_scope()
        assert "example.com" in scope

    def test_clear(self, test_db: str) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path=test_db)
        api.add_request(make_req("http://example.com/"))
        api.clear()
        tree = api.get_tree()
        assert tree == {}

    def test_export_json(self, test_db: str, tmp_path: "Path") -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path=test_db)
        api.add_request(make_req("http://example.com/export"))
        path = str(tmp_path / "sitemap.json")
        api.export_json(path)
        data = json.loads(Path(path).read_text())
        assert "example.com" in data

    @pytest.mark.asyncio
    async def test_get_paths(self, test_db: str) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path=test_db)
        api.add_request(make_req("http://example.com/a"))
        api.add_request(make_req("http://example.com/b"))
        paths = api.get_paths("example.com")
        path_strs = [n.path for n in paths]
        assert "/a" in path_strs
        assert "/b" in path_strs
