"""Unit tests: utils/coder.py — encoding, decoding, and hashing helpers."""

from __future__ import annotations

import pytest

from pentool.utils.coder import (
    apply_operation,
    base64_encode,
    base64_decode,
    base64url_encode,
    base64url_decode,
    html_encode,
    html_decode,
    hex_encode,
    hex_decode,
    md5,
    sha1,
    sha256,
    unicode_escape,
    unicode_unescape,
    url_encode,
    url_decode,
    url_decode_plus,
)


def test_url_encode_decode_roundtrip():
    assert url_encode("a b&c") == "a%20b%26c"
    assert url_decode("a%20b%26c") == "a b&c"
    assert url_decode_plus("a+b") == "a b"


def test_base64_roundtrip():
    enc = base64_encode("hello")
    assert base64_decode(enc) == "hello"


def test_base64_decode_invalid_padding_still_works():
    # b64decode with pad-right padding always succeeds for well-formed input
    assert base64_decode("aGVsbG8") == "hello"


def test_base64url_roundtrip():
    enc = base64url_encode("hello world")
    # no padding
    assert "=" not in enc
    assert base64url_decode(enc) == "hello world"


def test_html_roundtrip():
    assert html_encode("<b>a&b</b>") == "&lt;b&gt;a&amp;b&lt;/b&gt;"
    assert html_decode("&lt;b&gt;&amp;&lt;/b&gt;") == "<b>&</b>"


def test_hex_roundtrip():
    assert hex_encode("AB") == "4142"
    assert hex_decode("4142") == "AB"
    assert hex_decode("41 42") == "AB"  # spaces stripped
    assert hex_decode("\\x41\\x42") == "AB"  # \x prefix stripped


def test_unicode_escape_non_ascii():
    assert unicode_escape("café") == "caf\\u00e9"
    # ascii passes through
    assert unicode_escape("abc") == "abc"
    assert unicode_unescape("caf\\u00e9") == "café"


def test_hashes_deterministic():
    assert md5("abc") == "900150983cd24fb0d6963f7d28e17f72"
    assert sha1("abc") == "a9993e364706816aba3e25717850c26c9cd0d89d"
    assert sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_apply_operation_known_and_unknown():
    assert apply_operation("base64_encode", "x") == base64_encode("x")
    with pytest.raises(ValueError):
        apply_operation("nope", "x")


def test_base64_decode_invalid_raises():
    with pytest.raises(ValueError):
        base64_decode("!!!not base64!!!")


def test_base64url_decode_invalid_raises():
    with pytest.raises(ValueError):
        base64url_decode("a@@@")
    with pytest.raises(ValueError):
        base64url_decode("a")


def test_hex_decode_invalid_raises():
    with pytest.raises(ValueError):
        hex_decode("zzz-not-hex")


def test_url_escape_decode_roundtrip_invalid_unicode():
    # '\ud800' is a lone surrogate — unicode_escape fallback path
    result = unicode_unescape("\\uD800")
    assert isinstance(result, str)
