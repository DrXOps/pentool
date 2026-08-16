"""Unit tests for pentool/modules/scanner/checks/graphql.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): GraphQLCheck is a
global scan()-pipeline check (uses_scan_pipeline=False) that sends two
probes via http_client.send(): an introspection query and a field-suggestion
query. We pin the current detection behavior before any structural
migration.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.graphql import (
    GraphQLCheck,
    _FIELD_SUGGEST_QUERY,
    _INTROSPECTION_QUERY,
    _is_graphql,
)
from pentool.utils.parser import ParsedRequest, ParsedResponse


def _graphql_request() -> ParsedRequest:
    return ParsedRequest(
        method="POST",
        url="http://target/graphql",
        headers={"Content-Type": "application/json"},
        body='{"query":"{users{id}}"}',
    )


def _plain_request() -> ParsedRequest:
    return ParsedRequest(method="GET", url="http://target/health", headers={}, body="")


class TestMeta:
    def test_name(self):
        assert GraphQLCheck.name == "graphql"

    def test_uses_scan_pipeline_false(self):
        assert GraphQLCheck.uses_scan_pipeline is False

    def test_applicable_techs(self):
        assert "graphql" in GraphQLCheck.applicable_techs


class TestIsGraphql:
    def test_path_match(self):
        assert _is_graphql(_graphql_request())

    def test_non_graphql_path(self):
        assert not _is_graphql(_plain_request())


class TestScanIntrospection:
    @pytest.mark.asyncio
    async def test_introspection_enabled_detected(self):
        check = GraphQLCheck()
        req = _graphql_request()

        async def send(r):
            # Introspection probe -> body with __schema; suggestion probe -> clean.
            if "__schema" in (r.body or ""):
                return ParsedResponse(200, "OK", {}, '{"data":{"__schema":{"types":[]}}}')
            return ParsedResponse(200, "OK", {}, '{"data":{"users":[]}}')

        client = MagicMock()
        client.send = AsyncMock(side_effect=send)

        findings = await check.scan(req, None, client)
        assert any(f.type == "graphql" for f in findings)
        assert any("Introspection" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_field_suggestion_detected(self):
        check = GraphQLCheck()
        req = _graphql_request()

        async def send(r):
            if "passwrd" in (r.body or ""):
                return ParsedResponse(200, "OK", {}, '{"errors":[{"message":"Did you mean \\"password\\"?"}]}')
            return ParsedResponse(200, "OK", {}, '{"data":{}}')

        client = MagicMock()
        client.send = AsyncMock(side_effect=send)

        findings = await check.scan(req, None, client)
        assert any(f.type == "graphql" for f in findings)
        assert any("Suggestion" in f.name for f in findings)


class TestScanNoGraphql:
    @pytest.mark.asyncio
    async def test_non_graphql_returns_empty(self):
        check = GraphQLCheck()
        req = _plain_request()
        client = MagicMock()
        client.send = AsyncMock(return_value=ParsedResponse(200, "OK", {}, "{}"))
        findings = await check.scan(req, None, client)
        assert findings == []


class TestScanNoFinding:
    @pytest.mark.asyncio
    async def test_clean_responses_no_finding(self):
        check = GraphQLCheck()
        req = _graphql_request()
        client = MagicMock()
        client.send = AsyncMock(return_value=ParsedResponse(200, "OK", {}, '{"data":{}}'))
        findings = await check.scan(req, None, client)
        assert findings == []


class TestEngineIntegration:
    """End-to-end through ScanEngine — GraphQL introspection surfaced."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_graphql_introspection(self):
        from pentool.modules.scanner.engine import ScanEngine

        class FakeClient:
            async def send(self, request):
                if "__schema" in (request.body or ""):
                    return ParsedResponse(200, "OK", {}, '{"data":{"__schema":{"types":[]}}}')
                return ParsedResponse(200, "OK", {}, '{"data":{}}')

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, "hello")

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(GraphQLCheck())
        req = _graphql_request()
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "graphql" for f in findings)
