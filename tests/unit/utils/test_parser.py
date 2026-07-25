"""Unit-тесты: utils/parser.py

Покрывает: ParsedRequest, ParsedResponse, parse_http_request,
           parse_http_response, build_http_request.
"""

from __future__ import annotations

import pytest

from pentool.utils.parser import (
    ParsedRequest,
    ParsedResponse,
    parse_http_request,
    parse_http_response,
)


class TestParsedRequest:
    def test_host_from_url(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/path")
        assert req.host == "example.com"

    def test_host_from_url_with_port(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com:8080/path")
        assert req.host == "example.com:8080"

    def test_host_from_header_fallback(self) -> None:
        req = ParsedRequest(
            method="GET", url="/path", headers={"Host": "fallback.com"}
        )
        assert req.host == "fallback.com"

    def test_path_simple(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/api/users")
        assert req.path == "/api/users"

    def test_path_with_query(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/api?page=1&limit=10")
        assert "page=1" in req.path
        assert "limit=10" in req.path

    def test_path_default_slash(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com")
        assert req.path == "/"

    def test_is_https_true(self) -> None:
        req = ParsedRequest(method="GET", url="https://example.com/secure")
        assert req.is_https is True

    def test_is_https_false(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/plain")
        assert req.is_https is False

    def test_default_body_empty(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com")
        assert req.body == ""

    def test_default_headers_empty(self) -> None:
        req = ParsedRequest(method="GET", url="http://example.com")
        assert req.headers == {}


class TestParsedResponse:
    def test_basic_fields(self) -> None:
        resp = ParsedResponse(status=200, reason="OK", body="hello")
        assert resp.status == 200
        assert resp.reason == "OK"
        assert resp.body == "hello"

    def test_default_http_version(self) -> None:
        resp = ParsedResponse(status=404)
        assert resp.http_version == "HTTP/1.1"

    def test_default_body_empty(self) -> None:
        resp = ParsedResponse(status=204)
        assert resp.body == ""


class TestParseHttpRequest:
    def test_simple_get(self) -> None:
        raw = "GET /path HTTP/1.1\r\nHost: example.com\r\n\r\n"
        req = parse_http_request(raw)
        assert req.method == "GET"
        assert req.headers.get("Host") == "example.com"

    def test_post_with_body(self) -> None:
        raw = (
            "POST /login HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "Content-Type: application/json\r\n"
            "\r\n"
            '{"user":"admin"}'
        )
        req = parse_http_request(raw)
        assert req.method == "POST"
        assert req.body == '{"user":"admin"}'

    def test_headers_parsed(self) -> None:
        raw = (
            "GET / HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "User-Agent: TestAgent\r\n"
            "Accept: */*\r\n"
            "\r\n"
        )
        req = parse_http_request(raw)
        assert req.headers["User-Agent"] == "TestAgent"
        assert req.headers["Accept"] == "*/*"

    def test_empty_body_get(self) -> None:
        raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        req = parse_http_request(raw)
        assert req.body == ""

    def test_method_uppercase(self) -> None:
        raw = "get / HTTP/1.1\r\nHost: x.com\r\n\r\n"
        req = parse_http_request(raw)
        assert req.method == "GET"

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_http_request("")

    def test_lf_only_separator(self) -> None:
        """Поддержка \\n без \\r."""
        raw = "GET / HTTP/1.1\nHost: example.com\n\n"
        req = parse_http_request(raw)
        assert req.method == "GET"

    def test_multiline_body(self) -> None:
        raw = (
            "POST /data HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "\r\n"
            "line1\r\nline2\r\nline3"
        )
        req = parse_http_request(raw)
        assert "line1" in req.body
        assert "line3" in req.body


class TestParseHttpResponse:
    def test_simple_200(self) -> None:
        raw = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html/>"
        resp = parse_http_response(raw)
        assert resp.status == 200
        assert resp.reason == "OK"
        assert resp.body == "<html/>"

    def test_404_response(self) -> None:
        raw = "HTTP/1.1 404 Not Found\r\n\r\n"
        resp = parse_http_response(raw)
        assert resp.status == 404

    def test_headers_parsed(self) -> None:
        raw = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "X-Custom: value\r\n"
            "\r\n"
            "{}"
        )
        resp = parse_http_response(raw)
        assert resp.headers.get("Content-Type") == "application/json"
        assert resp.headers.get("X-Custom") == "value"

    def test_empty_body(self) -> None:
        raw = "HTTP/1.1 204 No Content\r\n\r\n"
        resp = parse_http_response(raw)
        assert resp.body == ""

    def test_http_version_preserved(self) -> None:
        raw = "HTTP/1.0 200 OK\r\n\r\nbody"
        resp = parse_http_response(raw)
        assert resp.http_version == "HTTP/1.0"
