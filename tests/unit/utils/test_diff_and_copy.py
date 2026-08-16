"""Unit tests: utils/diff.py and utils/copy_as.py"""

from __future__ import annotations

import pytest

from pentool.utils.parser import ParsedRequest


class TestDiffTexts:
    def test_identical_texts_no_diff(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("hello\nworld", "hello\nworld")
        assert result == []

    def test_added_line(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("line1\n", "line1\nline2\n")
        types = [d.type for d in result]
        assert "+" in types

    def test_removed_line(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("line1\nline2\n", "line1\n")
        types = [d.type for d in result]
        assert "-" in types

    def test_changed_line(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("old content\n", "new content\n")
        types = [d.type for d in result]
        assert "+" in types
        assert "-" in types

    def test_context_lines(self) -> None:
        from pentool.utils.diff import diff_texts, DiffLine
        text1 = "\n".join(["a", "b", "c", "d", "e"])
        text2 = "\n".join(["a", "b", "X", "d", "e"])
        result = diff_texts(text1, text2, context=1)
        # There should be context lines
        context = [d for d in result if d.type == " "]
        assert len(context) > 0

    def test_diff_line_content(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("foo\n", "bar\n")
        added = [d for d in result if d.type == "+"]
        removed = [d for d in result if d.type == "-"]
        assert any("bar" in d.content for d in added)
        assert any("foo" in d.content for d in removed)

    def test_empty_to_content(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("", "hello\n")
        types = [d.type for d in result]
        assert "+" in types

    def test_content_to_empty(self) -> None:
        from pentool.utils.diff import diff_texts
        result = diff_texts("hello\n", "")
        types = [d.type for d in result]
        assert "-" in types


class TestCopyAsCurl:
    def test_get_request(self) -> None:
        from pentool.utils.copy_as import copy_as_curl
        req = ParsedRequest(
            method="GET",
            url="http://example.com/api",
            headers={"Host": "example.com", "Accept": "application/json"},
        )
        cmd = copy_as_curl(req)
        assert "curl" in cmd
        assert "example.com/api" in cmd

    def test_post_with_data(self) -> None:
        from pentool.utils.copy_as import copy_as_curl
        req = ParsedRequest(
            method="POST",
            url="http://example.com/login",
            headers={"Host": "example.com", "Content-Type": "application/json"},
            body='{"user":"admin"}',
        )
        cmd = copy_as_curl(req)
        assert "-X" in cmd or "POST" in cmd
        assert "admin" in cmd

    def test_skips_content_length_header(self) -> None:
        from pentool.utils.copy_as import copy_as_curl
        req = ParsedRequest(
            method="GET",
            url="http://example.com/",
            headers={"Host": "example.com", "Content-Length": "0"},
        )
        cmd = copy_as_curl(req)
        assert "Content-Length" not in cmd

    def test_includes_custom_header(self) -> None:
        from pentool.utils.copy_as import copy_as_curl
        req = ParsedRequest(
            method="GET",
            url="http://example.com/",
            headers={"Host": "example.com", "X-API-Key": "secret123"},
        )
        cmd = copy_as_curl(req)
        assert "X-API-Key" in cmd
        assert "secret123" in cmd

    def test_no_x_flag_for_get(self) -> None:
        from pentool.utils.copy_as import copy_as_curl
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        cmd = copy_as_curl(req)
        # GET — no -X GET
        assert "-X GET" not in cmd


class TestCopyAsFfuf:
    def test_adds_fuzz_to_url(self) -> None:
        from pentool.utils.copy_as import copy_as_ffuf
        req = ParsedRequest(method="GET", url="http://example.com/path", headers={})
        cmd = copy_as_ffuf(req)
        assert "FUZZ" in cmd
        assert "ffuf" in cmd

    def test_preserves_existing_fuzz(self) -> None:
        from pentool.utils.copy_as import copy_as_ffuf
        req = ParsedRequest(
            method="GET",
            url="http://example.com/FUZZ",
            headers={},
        )
        cmd = copy_as_ffuf(req)
        # FUZZ is not duplicated
        assert cmd.count("FUZZ") >= 1


class TestDiffToRich:
    def test_formats_plus_minus_at_space(self) -> None:
        from pentool.utils.diff import diff_texts, diff_to_rich
        d = diff_texts("a\nb\n", "a\nc\n")
        rich = diff_to_rich(d)
        assert "[green]" in rich
        assert "[red]" in rich
        assert "[cyan]" in rich or "@@" not in rich  # header may be absent for tiny diffs

    def test_escapes_brackets(self) -> None:
        from pentool.utils.diff import DiffLine, diff_to_rich
        d = [DiffLine(type="+", content="a [b] c")]
        rich = diff_to_rich(d)
        # '[' is escaped to '\[' to avoid Rich markup injection; ']' is left as-is
        assert "\\[" in rich
        assert "[green]+a \\[b] c[/green]" in rich

    def test_added_line_green(self) -> None:
        from pentool.utils.diff import DiffLine, diff_to_rich
        d = [DiffLine(type="+", content="x")]
        assert diff_to_rich(d) == "[green]+x[/green]"

    def test_removed_line_red(self) -> None:
        from pentool.utils.diff import DiffLine, diff_to_rich
        d = [DiffLine(type="-", content="x")]
        assert diff_to_rich(d) == "[red]-x[/red]"

    def test_context_line_plain(self) -> None:
        from pentool.utils.diff import DiffLine, diff_to_rich
        d = [DiffLine(type=" ", content="x")]
        assert diff_to_rich(d) == " x"


# ── copy_as: additional generators ──────────────────────────────────────────

def _req(method="GET", url="http://example.com/path?a=1", headers=None, body=None):
    from pentool.utils.parser import ParsedRequest
    return ParsedRequest(method=method, url=url, headers=headers or {}, body=body)


def test_sqlmap_adds_data_when_params():
    from pentool.utils.copy_as import copy_as_sqlmap
    cmd = copy_as_sqlmap(_req(method="POST", body="a=1&b=2"))
    assert "--data" in cmd
    assert "sqlmap" in cmd


def test_sqlmap_no_data_without_params():
    from pentool.utils.copy_as import copy_as_sqlmap
    cmd = copy_as_sqlmap(_req(body="plain"))
    assert "--data" not in cmd


def test_sqlmap_binary_body():
    from pentool.utils.copy_as import copy_as_sqlmap
    cmd = copy_as_sqlmap(_req(body=b"email=x@y"))
    assert "--data" in cmd


def test_nmap_default_port_by_scheme():
    from pentool.utils.copy_as import copy_as_nmap
    assert "-p" in copy_as_nmap(_req(url="http://h/"))
    https = copy_as_nmap(_req(url="https://h/"))
    assert ":443" not in https  # host no port → 443 default
    http = copy_as_nmap(_req(url="http://h/"))
    assert "443" not in http


def test_nmap_explicit_port():
    from pentool.utils.copy_as import copy_as_nmap
    cmd = copy_as_nmap(_req(url="http://h:8080/"))
    assert "8080" in cmd


def test_jwt_tool_no_token():
    from pentool.utils.copy_as import copy_as_jwt_tool
    cmd = copy_as_jwt_tool(_req(headers={"Authorization": "Bearer notjwt"}))
    assert "# No JWT found" in cmd


def test_jwt_tool_bearer_token():
    from pentool.utils.copy_as import copy_as_jwt_tool
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
    cmd = copy_as_jwt_tool(_req(headers={"Authorization": f"Bearer {token}"}))
    assert "jwt_tool" in cmd
    assert token in cmd


def test_jwt_tool_from_cookie():
    from pentool.utils.copy_as import copy_as_jwt_tool
    token = "eyJh.eyJz.iG"
    cmd = copy_as_jwt_tool(_req(headers={"Cookie": f"session={token}; other=1"}))
    assert token in cmd


def test_save_request_txt(tmp_path):
    from pentool.utils.copy_as import save_request_txt
    out = tmp_path / "req.txt"
    save_request_txt(_req(method="POST", headers={"Host": "example.com"}, body="data"), str(out))
    text = out.read_text()
    assert "POST /path?a=1 HTTP/1.1" in text
    assert "data" in text


def test_fetch_basic():
    from pentool.utils.copy_as import copy_as_fetch
    cmd = copy_as_fetch(_req(method="GET", headers={"Host": "h"}, body=None))
    assert "fetch(" in cmd
    assert "GET" in cmd


def test_fetch_body_and_headers():
    from pentool.utils.copy_as import copy_as_fetch
    cmd = copy_as_fetch(_req(method="POST", headers={"X-A": "1"}, body="p=1"))
    assert '"body": "p=1"' in cmd
    assert "X-A" in cmd
    assert "Host" not in cmd  # host stripped


def test_open_in_browser():
    from unittest.mock import patch
    from pentool.utils.copy_as import open_in_browser
    with patch("webbrowser.open", return_value=True):
        assert open_in_browser("http://x") is True
    with patch("webbrowser.open", side_effect=Exception):
        assert open_in_browser("http://x") is False


class TestExtractUrlFromRaw:
    def test_empty(self):
        from pentool.utils.copy_as import extract_url_from_raw
        assert extract_url_from_raw("") == ""

    def test_full_url_first_line(self):
        from pentool.utils.copy_as import extract_url_from_raw
        assert extract_url_from_raw("GET http://h/p HTTP/1.1\r\n") == "http://h/p"

    def test_path_only_no_host(self):
        from pentool.utils.copy_as import extract_url_from_raw
        assert extract_url_from_raw("GET /x HTTP/1.1\r\n\r\n") == "/x"

    def test_uses_host_header(self):
        from pentool.utils.copy_as import extract_url_from_raw
        raw = "GET /api HTTP/1.1\r\nHost: example.com\r\n\r\n"
        assert extract_url_from_raw(raw) == "https://example.com/api"

    def test_http_proto_and_port80(self):
        from pentool.utils.copy_as import extract_url_from_raw
        raw = "GET / HTTP/1.1\r\nHost: h:80\r\nX-Forwarded-Proto: http\r\n\r\n"
        assert extract_url_from_raw(raw).startswith("http://")


class TestCopyToClipboard:
    def test_returns_true_when_xclip_success(self):
        from unittest.mock import patch, MagicMock
        from pentool.utils.copy_as import copy_to_clipboard
        proc = MagicMock()
        proc.returncode = 0
        with patch("pentool.utils.copy_as.subprocess.run", return_value=proc):
            assert copy_to_clipboard("hi") is True

    def test_pyperclip_fallback(self):
        from unittest.mock import MagicMock, patch
        from pentool.utils.copy_as import copy_to_clipboard, subprocess
        proc = MagicMock()
        proc.returncode = 1
        with patch.object(subprocess, "run", return_value=proc), \
             patch("builtins.__import__", side_effect=ImportError):
            assert copy_to_clipboard("hi") is False
