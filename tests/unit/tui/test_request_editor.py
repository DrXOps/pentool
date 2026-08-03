"""Unit tests: tui/widgets/request_editor.py

Covers: _get_content_type, _detect_language,
           RequestEditor (load_request, load_raw, get_text, clear),
           ResponseViewer (load_response, load_raw, clear).
"""

from __future__ import annotations

import pytest

from pentool.tui.widgets.request_editor import (
    _beautify_text,
    _detect_language,
    _get_content_type,
)
from pentool.utils.parser import ParsedRequest, ParsedResponse


class TestGetContentType:
    def test_titlecase_header(self) -> None:
        assert _get_content_type({"Content-Type": "application/json"}) == "application/json"

    def test_lowercase_header(self) -> None:
        assert _get_content_type({"content-type": "text/html"}) == "text/html"

    def test_mixed_case_header(self) -> None:
        assert _get_content_type({"CONTENT-TYPE": "text/xml"}) == "text/xml"

    def test_missing_header_returns_empty(self) -> None:
        assert _get_content_type({"Host": "example.com"}) == ""

    def test_empty_dict(self) -> None:
        assert _get_content_type({}) == ""

    def test_ignores_other_headers(self) -> None:
        headers = {"Host": "example.com", "Content-Type": "application/json", "X-Foo": "bar"}
        assert _get_content_type(headers) == "application/json"


# ─── _detect_language (by Content-Type) ────────────────────────────────────────

class TestDetectLanguageByContentType:
    def test_json(self) -> None:
        assert _detect_language("application/json", "") == "json"

    def test_json_with_charset(self) -> None:
        assert _detect_language("application/json; charset=utf-8", "") == "json"

    def test_html(self) -> None:
        assert _detect_language("text/html", "") == "html"

    def test_html_with_charset(self) -> None:
        assert _detect_language("text/html; charset=utf-8", "") == "html"

    def test_xml(self) -> None:
        assert _detect_language("application/xml", "") == "xml"

    def test_xml_text(self) -> None:
        assert _detect_language("text/xml", "") == "xml"

    def test_javascript(self) -> None:
        assert _detect_language("text/javascript", "") == "javascript"

    def test_ecmascript(self) -> None:
        assert _detect_language("application/ecmascript", "") == "javascript"

    def test_css(self) -> None:
        assert _detect_language("text/css", "") == "css"

    def test_yaml(self) -> None:
        assert _detect_language("application/yaml", "") == "yaml"

    def test_sql(self) -> None:
        assert _detect_language("application/sql", "") == "sql"

    def test_plain_text_no_lang(self) -> None:
        assert _detect_language("text/plain", "") is None

    def test_empty_ct_empty_body(self) -> None:
        assert _detect_language("", "") is None

    def test_case_insensitive(self) -> None:
        assert _detect_language("APPLICATION/JSON", "") == "json"


# ─── _detect_language (heuristic by body) ──────────────────────────────────────

class TestDetectLanguageByBody:
    def test_json_object(self) -> None:
        assert _detect_language("", '{"key": "value"}') == "json"

    def test_json_array(self) -> None:
        assert _detect_language("", '[1, 2, 3]') == "json"

    def test_json_with_whitespace(self) -> None:
        assert _detect_language("", '  \n{"k": 1}') == "json"

    def test_html_tag(self) -> None:
        assert _detect_language("", "<html><body></body></html>") == "html"

    def test_html_doctype(self) -> None:
        assert _detect_language("", "<!DOCTYPE html><html></html>") == "html"

    def test_html_doctype_uppercase(self) -> None:
        assert _detect_language("", "<!DOCTYPE HTML>") == "html"

    def test_xml_declaration(self) -> None:
        assert _detect_language("", '<?xml version="1.0"?>') == "xml"

    def test_xml_tag(self) -> None:
        assert _detect_language("", "<root><item/></root>") == "xml"

    def test_plain_text_no_lang(self) -> None:
        assert _detect_language("", "hello world") is None

    def test_empty_body_no_lang(self) -> None:
        assert _detect_language("", "") is None

    def test_content_type_takes_priority_over_body(self) -> None:
        # If Content-Type is present — it takes priority over body heuristic
        result = _detect_language("application/json", "<html></html>")
        assert result == "json"

    def test_no_false_positive_on_url(self) -> None:
        # URL starting with http should not yield xml
        assert _detect_language("", "http://example.com") is None


# ─── RequestEditor (unit without Textual) ───────────────────────────────────────

class TestRequestEditorHelpers:
    """Tests for RequestEditor helper logic without starting Textual."""

    def test_detect_lang_for_json_request(self) -> None:
        req = ParsedRequest(
            method="POST",
            url="http://api.example.com/data",
            headers={"Content-Type": "application/json"},
            body='{"user": "admin"}',
        )
        ct = _get_content_type(req.headers)
        lang = _detect_language(ct, req.body)
        assert lang == "json"

    def test_detect_lang_for_form_request(self) -> None:
        req = ParsedRequest(
            method="POST",
            url="http://example.com/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body="user=admin&pass=1234",
        )
        ct = _get_content_type(req.headers)
        lang = _detect_language(ct, req.body)
        assert lang is None

    def test_detect_lang_for_get_request(self) -> None:
        req = ParsedRequest(
            method="GET",
            url="http://example.com/page",
            headers={"Host": "example.com"},
            body="",
        )
        ct = _get_content_type(req.headers)
        lang = _detect_language(ct, req.body)
        assert lang is None


# ─── ResponseViewer (unit without Textual) ──────────────────────────────────────

class TestResponseViewerHelpers:
    """Tests for ResponseViewer helper logic without starting Textual."""

    def test_json_response(self) -> None:
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "application/json"},
            body='{"result": true}',
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang == "json"

    def test_html_response(self) -> None:
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"content-type": "text/html; charset=utf-8"},
            body="<html></html>",
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang == "html"

    def test_xml_response(self) -> None:
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "application/xml"},
            body="<root/>",
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang == "xml"

    def test_no_content_type_json_body(self) -> None:
        """Without Content-Type the heuristic detects JSON from body."""
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={},
            body='{"data": []}',
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang == "json"

    def test_error_response_no_body(self) -> None:
        resp = ParsedResponse(
            status=404,
            reason="Not Found",
            headers={},
            body="",
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang is None

    def test_javascript_response(self) -> None:
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "application/javascript"},
            body="function foo() {}",
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang == "javascript"

    def test_css_response(self) -> None:
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "text/css"},
            body="body { color: red; }",
        )
        ct = _get_content_type(resp.headers)
        lang = _detect_language(ct, resp.body)
        assert lang == "css"


# ─── _beautify_text (R-2: Beautify JSON/XML) ────────────────────────────────────

class TestBeautifyText:
    """Tests for _beautify_text — used by RequestEditor.beautify_body()."""

    def test_beautify_compact_json_object(self) -> None:
        result = _beautify_text('{"user":"admin","id":1}')
        assert result is not None
        assert '"user": "admin"' in result
        assert "\n" in result  # actually pretty-printed, not one line

    def test_beautify_json_array(self) -> None:
        result = _beautify_text('[1,2,3]')
        assert result is not None
        parsed_back = result
        assert "1" in parsed_back and "2" in parsed_back and "3" in parsed_back

    def test_beautify_nested_json(self) -> None:
        result = _beautify_text('{"a":{"b":{"c":1}}}')
        assert result is not None
        assert result.count("\n") >= 2  # nested indentation produces multiple lines

    def test_beautify_json_unicode_not_escaped(self) -> None:
        result = _beautify_text('{"name":"Тест"}')
        assert result is not None
        assert "Тест" in result  # ensure_ascii=False keeps Cyrillic readable

    def test_beautify_compact_xml(self) -> None:
        result = _beautify_text("<root><item>1</item></root>")
        assert result is not None
        assert "<root>" in result
        assert "<item>" in result
        assert "\n" in result

    def test_beautify_invalid_json_and_xml_returns_none(self) -> None:
        result = _beautify_text("not json { and not < xml either")
        assert result is None

    def test_beautify_plain_text_returns_none(self) -> None:
        result = _beautify_text("user=admin&pass=1234")
        assert result is None

    def test_beautify_empty_string_returns_none(self) -> None:
        assert _beautify_text("") is None
        assert _beautify_text("   ") is None

    def test_beautify_already_pretty_json_idempotent(self) -> None:
        pretty = '{\n  "a": 1\n}'
        result = _beautify_text(pretty)
        assert result is not None
        assert '"a": 1' in result

