"""Unit tests for pentool/modules/scanner/checks/xxe.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): XXECheck is a
scan()-pipeline, body-level check. Its scan() is content-type driven —
XML body -> classic payloads, JSON body -> JSON-as-XML attempt, and an SVG
upload fallback. We pin the current detection behavior before any
structural migration.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.xxe import (
    XXECheck,
    _CLASSIC_PAYLOADS,
    _SVG_PAYLOADS,
    _XINCLUDE_PAYLOADS,
    _check_xxe_response,
    _is_json_request,
    _is_xml_request,
    _json_to_xml_simple,
)
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest, ParsedResponse

# Linux /etc/passwd-style root line — matches _XXE_SIGNATURES[0]
PASSWD_BODY = "root:x:0:0:root:/root:/bin/bash\n"


def _post_request(body: str, content_type: str | None = None) -> ParsedRequest:
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    return ParsedRequest(method="POST", url="http://target/upload", headers=headers, body=body)


def _send_client(**kwargs) -> MagicMock:
    client = MagicMock()
    client.send = AsyncMock(return_value=kwargs.get("body", ParsedResponse(200, "OK", {}, PASSWD_BODY)))
    return client


class TestMeta:
    def test_name(self):
        assert XXECheck.name == "xxe"

    def test_uses_scan_pipeline(self):
        assert XXECheck.uses_scan_pipeline is True


class TestHelpers:
    def test_check_xxe_response(self):
        found, desc = _check_xxe_response(PASSWD_BODY)
        assert found
        assert "passwd" in desc
        found2, _ = _check_xxe_response("<html>ok</html>")
        assert not found2

    def test_is_xml_request_header(self):
        assert _is_xml_request(_post_request("x", "application/xml"))
        assert _is_xml_request(_post_request("x", "image/svg+xml"))

    def test_is_xml_request_body(self):
        assert _is_xml_request(_post_request("<?xml version=\"1.0\"?><root/>"))

    def test_is_json_request(self):
        assert _is_json_request(_post_request('{"k": "v"}', "application/json"))
        assert not _is_json_request(_post_request("<root/>", "application/xml"))

    def test_json_to_xml_simple(self):
        xml = _json_to_xml_simple('{"a": "1", "b": "2"}')
        assert xml == '<?xml version="1.0"?><root><a>1</a><b>2</b></root>'


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_finding_on_passwd(self):
        check = XXECheck()
        req = _post_request("xml")
        mutated = _post_request(_CLASSIC_PAYLOADS[0], "application/xml")
        point = InjectionPoint(kind="post", name="body", original_value="")
        resp = ParsedResponse(200, "OK", {}, PASSWD_BODY)
        finding = await check.analyze(req, mutated, point, _CLASSIC_PAYLOADS[0], resp)
        assert finding is not None
        assert finding.type == "xxe"
        assert finding.parameter == "body"

    @pytest.mark.asyncio
    async def test_analyze_none_on_clean(self):
        check = XXECheck()
        req = _post_request("xml")
        point = InjectionPoint(kind="post", name="body", original_value="")
        resp = ParsedResponse(200, "OK", {}, "<html>ok</html>")
        finding = await check.analyze(req, req, point, _CLASSIC_PAYLOADS[0], resp)
        assert finding is None


class TestScanCase1XmlBody:
    @pytest.mark.asyncio
    async def test_xml_body_detects_xxe(self):
        check = XXECheck()
        req = _post_request("<?xml version=\"1.0\"?><root/>")  # XML-shaped body
        client = _send_client()  # returns PASSWD_BODY on every send
        findings = await check.scan(req, None, client)
        assert any(f.type == "xxe" for f in findings)

    @pytest.mark.asyncio
    async def test_non_xml_non_json_get_skips(self):
        # Case guards require POST/PUT/PATCH (or XML/JSON detection).
        check = XXECheck()
        req = ParsedRequest(method="GET", url="http://target/", headers={}, body="")
        client = _send_client()
        findings = await check.scan(req, None, client)
        assert findings == []


class TestScanCase2JsonBody:
    @pytest.mark.asyncio
    async def test_json_body_submitted_as_xml(self):
        check = XXECheck()
        req = _post_request('{"k": "v"}', "application/json")
        client = _send_client()  # returns PASSWD_BODY, status 200 < 500
        findings = await check.scan(req, None, client)
        assert any(f.type == "xxe" for f in findings)


class TestScanNoFinding:
    @pytest.mark.asyncio
    async def test_clean_response_no_finding(self):
        check = XXECheck()
        req = _post_request("<?xml version=\"1.0\"?><root/>")
        client = MagicMock()
        client.send = AsyncMock(return_value=ParsedResponse(200, "OK", {}, "<html>ok</html>"))
        findings = await check.scan(req, None, client)
        assert findings == []


class TestEngineIntegration:
    """End-to-end through ScanEngine — XXE found via the scan()-pipeline."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_xxe_from_xml_body(self):
        from pentool.modules.scanner.engine import ScanEngine

        # XXE only runs when the fingerprint decides the stack "accepts XML"
        # (allows_check('xxe') = accepts_xml or has_xml_response, fingerprint.py
        # :62-63). Serve an XML Content-Type on get() so the check isn't
        # skipped; send() returns an XXE-readable body to trigger a finding.
        class FakeClient:
            async def send(self, request):
                return ParsedResponse(200, "OK", {}, PASSWD_BODY)

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {"Content-Type": "application/xml"}, "<root/>")

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(XXECheck())
        req = _post_request("<?xml version=\"1.0\"?><root/>")
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "xxe" for f in findings)
