"""Unit tests: utils/coder.py

Covers: url_encode/decode, base64, html, hex, hashing.
"""

from __future__ import annotations

import pytest

from pentool.utils.coder import (
    base64_decode,
    base64_encode,
    base64url_decode,
    base64url_encode,
    html_decode,
    html_encode,
    url_decode,
    url_decode_plus,
    url_encode,
    url_encode_all,
)


class TestUrlEncoding:
    def test_url_encode_spaces(self) -> None:
        assert url_encode("hello world") == "hello%20world"

    def test_url_encode_special_chars(self) -> None:
        result = url_encode("a=1&b=2")
        assert "%" in result
        assert "&" not in result

    def test_url_decode_roundtrip(self) -> None:
        original = "user=admin&pass=s3cr3t!"
        assert url_decode(url_encode(original)) == original

    def test_url_encode_all_no_safe(self) -> None:
        result = url_encode_all("/path/to/resource")
        assert "/" not in result

    def test_url_decode_plus_converts_plus(self) -> None:
        assert url_decode_plus("hello+world") == "hello world"

    def test_url_decode_plus_keeps_percent(self) -> None:
        assert url_decode_plus("hello%20world") == "hello world"

    def test_url_encode_unicode(self) -> None:
        result = url_encode("café")
        assert "%" in result

    def test_url_decode_unicode(self) -> None:
        encoded = url_encode("café")
        assert url_decode(encoded) == "café"


class TestBase64:
    def test_encode_basic(self) -> None:
        assert base64_encode("hello") == "aGVsbG8="

    def test_decode_basic(self) -> None:
        assert base64_decode("aGVsbG8=") == "hello"

    def test_roundtrip(self) -> None:
        original = "PenTool v0.1 — test"
        assert base64_decode(base64_encode(original)) == original

    def test_decode_without_padding(self) -> None:
        """Decoding without '=' padding."""
        result = base64_decode("aGVsbG8")
        assert result == "hello"

    def test_encode_empty(self) -> None:
        assert base64_encode("") == ""

    def test_decode_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            base64_decode("not-valid-base64!!!")

    def test_base64url_encode(self) -> None:
        result = base64url_encode("hello+world")
        assert "+" not in result
        assert "/" not in result

    def test_base64url_roundtrip(self) -> None:
        original = "data with +/= chars"
        assert base64url_decode(base64url_encode(original)) == original


class TestHtmlEncoding:
    def test_html_encode_lt_gt(self) -> None:
        result = html_encode("<script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result
        assert "&lt;" in result
        assert "&gt;" in result

    def test_html_encode_ampersand(self) -> None:
        result = html_encode("a & b")
        assert "&amp;" in result

    def test_html_encode_quotes(self) -> None:
        result = html_encode('"quoted"')
        assert "&quot;" in result

    def test_html_decode_roundtrip(self) -> None:
        original = '<div class="test">Hello & World</div>'
        assert html_decode(html_encode(original)) == original

    def test_html_decode_entities(self) -> None:
        assert html_decode("&lt;b&gt;") == "<b>"
        assert html_decode("&amp;") == "&"
