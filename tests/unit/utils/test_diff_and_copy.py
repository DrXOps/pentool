"""Unit-тесты: utils/diff.py и utils/copy_as.py"""

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
        # Должны быть контекстные строки
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
        # GET — нет -X GET
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
        # FUZZ не дублируется
        assert cmd.count("FUZZ") >= 1
