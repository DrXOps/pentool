"""Unit tests for pentool/modules/scanner/checks/xss.py."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── Helpers ────────────────────────────────────────────────────────────────────

class TestMakeMarker:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _make_marker, _extract_marker
        self.make = _make_marker
        self.extract = _extract_marker

    def test_marker_in_alert_payload(self):
        marker, tagged = self.make("<img src=x onerror=alert(1)>")
        assert marker in tagged

    def test_marker_extracted(self):
        marker, tagged = self.make("<svg onload=alert(1)>")
        extracted = self.extract(tagged)
        assert extracted == marker

    def test_fallback_comment_marker(self):
        marker, tagged = self.make("<custom>")
        assert marker in tagged

    def test_extract_none_when_no_marker(self):
        from pentool.modules.scanner.checks.xss import _extract_marker
        assert _extract_marker("no marker here") is None


class TestMarkerInBody:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _marker_in_body, _make_marker
        self.check = _marker_in_body
        self.make = _make_marker

    def test_marker_found(self):
        marker, tagged = self.make("<img src=x onerror=alert(1)>")
        assert self.check(tagged, f"response body {marker} end") is True

    def test_marker_not_found(self):
        _, tagged = self.make("<img src=x onerror=alert(1)>")
        assert self.check(tagged, "no reflection here") is False


class TestNormalizeHtmlEntities:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _normalize_html_entities
        self.fn = _normalize_html_entities

    def test_apos(self):
        assert self.fn("&apos;") == "'"

    def test_quot(self):
        assert self.fn("&quot;") == '"'

    def test_lt_gt(self):
        assert self.fn("&lt;x&gt;") == "<x>"

    def test_numeric_entities(self):
        assert self.fn("&#39;") == "'"
        assert self.fn("&#34;") == '"'


class TestDetectContext:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _detect_context
        self.fn = _detect_context

    def test_html_body(self):
        ctx = self.fn("PROBE", ">PROBE<")
        assert ctx == "html_body"

    def test_attr_double(self):
        # attr_double pattern: ="PROBE" — but js_string_double matches first
        ctx = self.fn("PROBE", 'value="PROBE" data-x="y"')
        assert ctx in ("attr_double", "js_string_double")

    def test_attr_single(self):
        ctx = self.fn("PROBE", "value='PROBE' data-x='y'")
        assert ctx in ("attr_single", "js_string_single")

    def test_js_string_double(self):
        ctx = self.fn("PROBE", '"PROBE"')
        assert ctx == "js_string_double"

    def test_js_string_single(self):
        ctx = self.fn("PROBE", "'PROBE'")
        assert ctx == "js_string_single"

    def test_none_context(self):
        ctx = self.fn("PROBE", "no reflection")
        assert ctx == "none"

    def test_entity_context(self):
        ctx = self.fn("PROBE", "='&apos;PROBE&apos;'")
        assert "_entity" in ctx or ctx != "none"


class TestFingerprintFilters:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _fingerprint_filters
        self.fn = _fingerprint_filters

    def test_no_filters(self):
        result = self.fn("x", "<\"'`{{<!--script alert")
        assert result["angle_brackets"] is False
        assert result["double_quote"] is False

    def test_angle_brackets_filtered(self):
        result = self.fn("x", "no angle brackets here")
        assert result["angle_brackets"] is True

    def test_script_filtered(self):
        result = self.fn("x", "no s-c-r-i-p-t keyword")
        assert result["script_keyword"] is True


class TestPayloadsForContext:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _payloads_for_context
        self.fn = _payloads_for_context

    def test_html_body_returns_list(self):
        payloads = self.fn("html_body", {})
        assert len(payloads) > 0

    def test_attr_double_returns_list(self):
        payloads = self.fn("attr_double", {})
        assert len(payloads) > 0

    def test_none_context_returns_list(self):
        payloads = self.fn("none", {})
        assert len(payloads) > 0

    def test_html_body_angle_filtered(self):
        payloads = self.fn("html_body", {"angle_brackets": True})
        assert any("&#60;" in p or "&#x3C;" in p for p in payloads)

    def test_entity_context(self):
        payloads = self.fn("js_string_single_entity", {})
        assert len(payloads) > 0


class TestApplyBypassTransforms:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _apply_bypass_transforms
        self.fn = _apply_bypass_transforms

    def test_returns_variants(self):
        variants = self.fn("<img src=x onerror=alert(1)>")
        assert len(variants) > 0

    def test_no_duplicates(self):
        variants = self.fn("<svg onload=alert(1)>")
        assert len(variants) == len(set(variants))

    def test_javascript_bypass(self):
        variants = self.fn("javascript:alert(1)")
        assert any("javascript" in v.lower() for v in variants)

    def test_space_substitution(self):
        variants = self.fn("<img src=x onerror=alert(1)>")
        assert any("/**/" in v for v in variants)


class TestAnalyzeCsp:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import _analyze_csp
        self.fn = _analyze_csp

    def test_no_csp_returns_empty(self):
        assert self.fn({}) == []

    def test_unsafe_inline(self):
        issues = self.fn({"content-security-policy": "script-src 'unsafe-inline'"})
        assert any("unsafe-inline" in i for i in issues)

    def test_unsafe_eval(self):
        issues = self.fn({"Content-Security-Policy": "script-src 'unsafe-eval'"})
        assert any("unsafe-eval" in i for i in issues)

    def test_data_uri(self):
        issues = self.fn({"content-security-policy": "script-src data:"})
        assert any("data:" in i for i in issues)

    def test_clean_csp(self):
        issues = self.fn({"content-security-policy": "default-src 'self'"})
        assert issues == []


class TestXSSCheckClass:
    def setup_method(self):
        from pentool.modules.scanner.checks.xss import XSSCheck
        self.check = XSSCheck()

    def test_name(self):
        assert self.check.name == "xss"

    def test_get_payloads(self):
        payloads = self.check.get_payloads()
        assert len(payloads) > 0

    def test_uses_scan_pipeline(self):
        assert self.check.uses_scan_pipeline is True

    @pytest.mark.asyncio
    async def test_analyze_no_reflection(self):
        from pentool.utils.parser import ParsedRequest, ParsedResponse
        from pentool.modules.scanner.checks.xss import _make_marker

        marker, tagged = _make_marker("<img src=x onerror=alert(1)>")
        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={}, body="no reflection")
        point = MagicMock()
        point.kind = "get"
        point.name = "q"

        result = await self.check.analyze(req, req, point, tagged, resp)
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_with_reflection(self):
        from pentool.utils.parser import ParsedRequest, ParsedResponse
        from pentool.modules.scanner.checks.xss import _make_marker

        marker, tagged = _make_marker("<img src=x onerror=alert(1)>")
        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={}, body=f"<html>{marker}</html>")
        point = MagicMock()
        point.kind = "get"
        point.name = "q"

        result = await self.check.analyze(req, req, point, tagged, resp)
        assert result is not None
        assert result.type == "xss"

    @pytest.mark.asyncio
    async def test_passive_scan_weak_csp(self):
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(
            status=200,
            headers={"content-security-policy": "script-src 'unsafe-inline'"},
            body="",
        )
        findings = await self.check.passive_scan(req, resp, MagicMock())
        assert len(findings) > 0
        assert findings[0].severity == "low"

    @pytest.mark.asyncio
    async def test_passive_scan_no_csp(self):
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={}, body="")
        findings = await self.check.passive_scan(req, resp, MagicMock())
        assert findings == []
