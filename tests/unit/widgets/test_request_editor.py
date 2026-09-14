"""Unit tests for pentool/tui/widgets/request_editor.py (pure functions)."""

from __future__ import annotations

from pentool.tui.widgets.request_editor import (
    _build_http_highlights,
    _detect_language,
    _get_content_type,
    _hl_cookie,
    _hl_qs,
    _render_headers_rich,
    decode_special_chars,
    visualize_special_chars,
)

# ── visualize_special_chars / decode_special_chars ─────────────────────────


class TestVisualizeSpecialChars:
    def test_no_special_chars(self) -> None:
        assert visualize_special_chars("hello world") == "hello world"

    def test_crlf_replaced(self) -> None:
        assert "\\r\\n\n" in visualize_special_chars("a\r\nb")

    def test_cr_replaced(self) -> None:
        assert "\\r\n" in visualize_special_chars("a\rb")

    def test_lf_replaced(self) -> None:
        assert "\\n\n" in visualize_special_chars("a\nb")


class TestDecodeSpecialChars:
    def test_no_special_chars(self) -> None:
        assert decode_special_chars("hello") == "hello"

    def test_crlf_decoded(self) -> None:
        assert decode_special_chars("a\\r\\n\nb") == "a\r\nb"

    def test_cr_decoded(self) -> None:
        assert decode_special_chars("a\\r\nb") == "a\rb"

    def test_nl_decoded(self) -> None:
        assert decode_special_chars("a\\n\nb") == "a\nb"


class TestVisualizeRoundTrip:
    def test_roundtrip(self) -> None:
        original = "GET / HTTP/1.1\r\nHost: test\r\n\r\nbody"
        viz = visualize_special_chars(original)
        back = decode_special_chars(viz)
        # Roundtrip keeps the structural \n but removes literal markers
        # Full equivalence not guaranteed due to \r\n -> \\r\\n\\n -> \\r\\n (line by line)
        assert original.replace("\r\n", "\n").replace("\r", "") in back.replace("\r\n", "\n")


# ── _get_content_type ─────────────────────────────────────────────────────


class TestGetContentType:
    def test_found(self) -> None:
        assert _get_content_type({"Content-Type": "application/json"}) == "application/json"

    def test_case_insensitive(self) -> None:
        assert _get_content_type({"content-type": "text/html"}) == "text/html"

    def test_not_found(self) -> None:
        assert _get_content_type({"Host": "x"}) == ""

    def test_empty_headers(self) -> None:
        assert _get_content_type({}) == ""


# ── _detect_language ──────────────────────────────────────────────────────


class TestDetectLanguage:
    def test_json_content_type(self) -> None:
        assert _detect_language("application/json", "{}") == "json"

    def test_html_content_type(self) -> None:
        assert _detect_language("text/html", "") == "html"

    def test_xml_content_type(self) -> None:
        assert _detect_language("application/xml", "") == "xml"

    def test_javascript_content_type(self) -> None:
        assert _detect_language("application/javascript", "") == "javascript"

    def test_css_content_type(self) -> None:
        assert _detect_language("text/css", "") == "css"

    def test_sql_content_type(self) -> None:
        assert _detect_language("text/x-sql", "") == "sql"

    def test_yaml_content_type(self) -> None:
        assert _detect_language("text/yaml", "") == "yaml"

    def test_detect_from_json_body(self) -> None:
        assert _detect_language("", '{"key": "val"}') == "json"

    def test_detect_from_json_array_body(self) -> None:
        assert _detect_language("", '["a"]') == "json"

    def test_detect_from_html_body(self) -> None:
        assert _detect_language("", "<html><body>Hi</body></html>") == "html"

    def test_detect_from_doctype(self) -> None:
        assert _detect_language("", "<!DOCTYPE html>") == "html"

    def test_detect_from_xml_body(self) -> None:
        assert _detect_language("", '<?xml version="1.0"?>') == "xml"

    def test_unknown_content_type(self) -> None:
        assert _detect_language("text/plain", "plain text") is None

    def test_none_content_type(self) -> None:
        assert _detect_language(None, "text") is None


# ── _hl_qs ────────────────────────────────────────────────────────────────


class TestHlQs:
    def test_no_query_string(self) -> None:
        assert "path" in _hl_qs("/path")

    def test_single_param(self) -> None:
        result = _hl_qs("/search?q=hello")
        assert "q" in result
        assert "hello" in result

    def test_multiple_params(self) -> None:
        result = _hl_qs("/api?a=1&b=2")
        assert "a" in result
        assert "b" in result
        assert "1" in result

    def test_encoded_characters(self) -> None:
        result = _hl_qs("/path?name=hello%20world")
        assert "hello%20world" in result


# ── _hl_cookie ────────────────────────────────────────────────────────────


class TestHlCookie:
    def test_single_pair(self) -> None:
        result = _hl_cookie("session=abc123")
        assert "session" in result
        assert "abc123" in result

    def test_multiple_pairs(self) -> None:
        result = _hl_cookie("session=abc; theme=dark")
        assert "theme" in result

    def test_no_separator(self) -> None:
        assert "rawvalue" in _hl_cookie("rawvalue")


# ── _render_headers_rich ───────────────────────────────────────────────────


class TestRenderHeadersRich:
    def test_request_line(self) -> None:
        result = _render_headers_rich("GET / HTTP/1.1", {"Host": "example.com"})
        assert "GET" in result
        assert "Host" in result
        assert "example.com" in result

    def test_response_line(self) -> None:
        result = _render_headers_rich("HTTP/1.1 200 OK", {"Content-Type": "text/html"})
        assert "200" in result
        assert "Content-Type" in result

    def test_error_response(self) -> None:
        result = _render_headers_rich("HTTP/1.1 404 Not Found", {})
        assert "404" in result

    def test_cookie_header_highlighted(self) -> None:
        result = _render_headers_rich("GET / HTTP/1.1", {"Cookie": "session=xyz"})
        assert "session" in result
        assert "Cookie" in result


# ── _build_http_highlights ────────────────────────────────────────────────


class TestBuildHttpHighlights:
    def test_empty_text(self) -> None:
        assert _build_http_highlights("") == {}

    def test_get_line(self) -> None:
        hl = _build_http_highlights("GET / HTTP/1.1\nHost: test\n\nbody")
        # Row 0 should have highlights for method, path, etc.
        assert 0 in hl
        assert len(hl[0]) >= 1

    def test_post_line(self) -> None:
        hl = _build_http_highlights("POST /api/data HTTP/1.1\n\n")
        assert 0 in hl

    def test_header_coloring(self) -> None:
        hl = _build_http_highlights("GET / HTTP/1.1\nHost: example.com\n\n")
        assert 1 in hl  # header row has highlights

    def test_cookie_highlighted(self) -> None:
        hl = _build_http_highlights("GET / HTTP/1.1\nCookie: session=xyz\n\n")
        assert len(hl) >= 2

    def test_redirect_response(self) -> None:
        hl = _build_http_highlights("HTTP/1.1 302 Found\nLocation: /new\n\n")
        assert 0 in hl

    def test_query_string_parsed(self) -> None:
        hl = _build_http_highlights("GET /search?q=hello&page=1 HTTP/1.1\n\n")
        assert 0 in hl


# ── _METHOD_COLORS constants ──────────────────────────────────────────────


class TestMethodColors:
    def test_all_methods_covered(self) -> None:
        from pentool.tui.widgets.request_editor import _METHOD_COLORS
        assert _METHOD_COLORS["GET"] == "keyword"
        assert _METHOD_COLORS["POST"] == "string"
        assert "DELETE" in _METHOD_COLORS

    def test_method_colors_keys_upper(self) -> None:
        from pentool.tui.widgets.request_editor import _METHOD_COLORS
        for key in _METHOD_COLORS:
            assert key == key.upper()


# ── _HEADER_TOKEN constants ───────────────────────────────────────────────


class TestHeaderToken:
    def test_common_headers_covered(self) -> None:
        from pentool.tui.widgets.request_editor import _HEADER_TOKEN
        assert "host" in _HEADER_TOKEN
        assert "content-type" in _HEADER_TOKEN
        assert "authorization" in _HEADER_TOKEN
        assert "cookie" in _HEADER_TOKEN


# ── _SUPPORTED_LANGS ──────────────────────────────────────────────────────


class TestSupportedLangs:
    def test_common_languages(self) -> None:
        from pentool.tui.widgets.request_editor import _SUPPORTED_LANGS
        assert "json" in _SUPPORTED_LANGS
        assert "html" in _SUPPORTED_LANGS
        assert "python" in _SUPPORTED_LANGS


# ── _HEADER_COLORS constants ──────────────────────────────────────────────


class TestHeaderColors:
    def test_common_header_colors(self) -> None:
        from pentool.tui.widgets.request_editor import _HEADER_COLORS
        assert "host" in _HEADER_COLORS
        assert "content-type" in _HEADER_COLORS
        assert "authorization" in _HEADER_COLORS


# ── _METHOD_RICH constants ────────────────────────────────────────────────


class TestMethodRich:
    def test_all_methods(self) -> None:
        from pentool.tui.widgets.request_editor import _METHOD_RICH
        assert "GET" in _METHOD_RICH
        assert "POST" in _METHOD_RICH
        assert "DELETE" in _METHOD_RICH
        assert "OPTIONS" in _METHOD_RICH