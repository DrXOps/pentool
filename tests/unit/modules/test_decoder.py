"""Unit-тесты для pentool/modules/decoder.py."""

from __future__ import annotations

import pytest
from pentool.modules.decoder import (
    OP_LABELS,
    DecoderChain,
    decode_smart,
    encode_op,
    run_chain,
)


class TestUrlEncodeDecode:
    def test_url_encode_basic(self):
        assert encode_op("URL Encode", "hello world") == "hello%20world"

    def test_url_encode_special(self):
        result = encode_op("URL Encode", "a=1&b=2")
        assert "%" in result
        assert "=" not in result or result == "a%3D1%26b%3D2"

    def test_url_decode_basic(self):
        assert encode_op("URL Decode", "hello%20world") == "hello world"

    def test_url_decode_percent_signs(self):
        result = encode_op("URL Decode", "%2F%3F%3D")
        assert result == "/?="

    def test_url_roundtrip(self):
        original = "test string with spaces & special=chars"
        encoded = encode_op("URL Encode", original)
        decoded = encode_op("URL Decode", encoded)
        assert decoded == original


class TestBase64:
    def test_base64_encode(self):
        assert encode_op("Base64 Encode", "Hello") == "SGVsbG8="

    def test_base64_decode(self):
        assert encode_op("Base64 Decode", "SGVsbG8=") == "Hello"

    def test_base64_decode_no_padding(self):
        assert encode_op("Base64 Decode", "SGVsbG8") == "Hello"

    def test_base64_roundtrip(self):
        original = "Test data 123 !@#"
        encoded = encode_op("Base64 Encode", original)
        decoded = encode_op("Base64 Decode", encoded)
        assert decoded == original


class TestBase64URL:
    def test_base64url_encode(self):
        result = encode_op("Base64URL Encode", "Hello")
        assert result == "SGVsbG8"  # без паддинга

    def test_base64url_roundtrip(self):
        original = "url-safe data: +/="
        encoded = encode_op("Base64URL Encode", original)
        decoded = encode_op("Base64URL Decode", encoded)
        assert decoded == original

    def test_base64url_no_plus_slash(self):
        result = encode_op("Base64URL Encode", b"\xfb\xff".decode("latin-1"))
        assert "+" not in result
        assert "/" not in result


class TestHtmlEncodeDecode:
    def test_html_encode(self):
        assert encode_op("HTML Encode", "<script>") == "&lt;script&gt;"

    def test_html_encode_quotes(self):
        result = encode_op("HTML Encode", '"hello"')
        assert "&quot;" in result

    def test_html_decode(self):
        assert encode_op("HTML Decode", "&lt;script&gt;") == "<script>"

    def test_html_roundtrip(self):
        original = "<b>Hello & 'World'</b>"
        encoded = encode_op("HTML Encode", original)
        decoded = encode_op("HTML Decode", encoded)
        assert decoded == original


class TestHexEncodeDecode:
    def test_hex_encode(self):
        assert encode_op("Hex Encode", "AB") == "4142"

    def test_hex_decode(self):
        assert encode_op("Hex Decode", "4142") == "AB"

    def test_hex_roundtrip(self):
        original = "test123"
        encoded = encode_op("Hex Encode", original)
        decoded = encode_op("Hex Decode", encoded)
        assert decoded == original


class TestUnicode:
    def test_unicode_encode_ascii(self):
        # ASCII не кодируется
        result = encode_op("Unicode Encode", "hello")
        assert result == "hello"

    def test_unicode_encode_non_ascii(self):
        result = encode_op("Unicode Encode", "café")
        assert "\\u00e9" in result or "\\u00E9" in result

    def test_unicode_decode(self):
        result = encode_op("Unicode Decode", "\\u0041\\u0042\\u0043")
        assert result == "ABC"


class TestHashing:
    def test_md5(self):
        result = encode_op("MD5", "hello")
        assert result == "5d41402abc4b2a76b9719d911017c592"
        assert len(result) == 32

    def test_sha1(self):
        result = encode_op("SHA1", "hello")
        assert result == "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"
        assert len(result) == 40

    def test_sha256(self):
        result = encode_op("SHA256", "hello")
        assert len(result) == 64

    def test_sha512(self):
        result = encode_op("SHA512", "hello")
        assert len(result) == 128


class TestJWTDecode:
    _JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

    def test_jwt_decode_returns_json(self):
        import json
        result = encode_op("JWT Decode", self._JWT)
        data = json.loads(result)
        assert "header" in data
        assert "payload" in data

    def test_jwt_decode_header(self):
        import json
        result = encode_op("JWT Decode", self._JWT)
        data = json.loads(result)
        assert data["header"]["alg"] == "HS256"

    def test_jwt_decode_payload(self):
        import json
        result = encode_op("JWT Decode", self._JWT)
        data = json.loads(result)
        assert data["payload"]["name"] == "John Doe"

    def test_jwt_invalid(self):
        result = encode_op("JWT Decode", "not.a.jwt")
        # Не должен бросать, должен вернуть что-то
        assert isinstance(result, str)


class TestRunChain:
    def test_empty_chain(self):
        result, steps = run_chain([], "hello")
        assert result == "hello"
        assert steps == ["hello"]

    def test_single_step(self):
        result, steps = run_chain(["Base64 Encode"], "Hello")
        assert result == "SGVsbG8="
        assert len(steps) == 2

    def test_two_steps(self):
        result, steps = run_chain(["Base64 Encode", "URL Encode"], "Hi")
        assert len(steps) == 3
        # Base64("Hi") = "SGk=" → URL encode → "SGk%3D"
        assert "SGk" in result

    def test_invalid_op_in_chain(self):
        result, steps = run_chain(["INVALID_OP", "Base64 Encode"], "test")
        # Ошибочная операция записывает [error ...] в output
        assert "[error" in steps[1]

    def test_roundtrip_chain(self):
        encode_chain = ["Base64 Encode", "URL Encode"]
        decode_chain = ["URL Decode", "Base64 Decode"]
        original = "Test data!"
        encoded, _ = run_chain(encode_chain, original)
        decoded, _ = run_chain(decode_chain, encoded)
        assert decoded == original


class TestDecodeSmart:
    def test_smart_url(self):
        result = decode_smart("hello%20world")
        assert result == "hello world"

    def test_smart_base64(self):
        result = decode_smart("SGVsbG8=")
        assert result == "Hello"

    def test_smart_hex(self):
        result = decode_smart("48656c6c6f")
        assert result == "Hello"

    def test_smart_html(self):
        result = decode_smart("&lt;b&gt;Hello&lt;/b&gt;")
        assert result == "<b>Hello</b>"

    def test_smart_plain_text(self):
        original = "just plain text"
        result = decode_smart(original)
        assert result == original

    def test_smart_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.sig"
        result = decode_smart(jwt)
        assert "header" in result


class TestDecoderChain:
    def test_add_valid_op(self):
        chain = DecoderChain()
        chain.add("Base64 Encode")
        assert chain.operations == ["Base64 Encode"]

    def test_add_invalid_op(self):
        chain = DecoderChain()
        with pytest.raises(KeyError):
            chain.add("INVALID")

    def test_remove_op(self):
        chain = DecoderChain(operations=["Base64 Encode", "URL Encode"])
        chain.remove(0)
        assert chain.operations == ["URL Encode"]

    def test_clear(self):
        chain = DecoderChain(operations=["Base64 Encode"])
        chain.clear()
        assert chain.operations == []

    def test_run(self):
        chain = DecoderChain(operations=["Base64 Encode"])
        result, steps = chain.run("Hello")
        assert result == "SGVsbG8="


class TestOpRegistry:
    def test_all_labels_unique(self):
        assert len(OP_LABELS) == len(set(OP_LABELS))

    def test_encode_op_raises_on_unknown(self):
        with pytest.raises(KeyError):
            encode_op("NONEXISTENT", "data")

    def test_all_ops_callable(self):
        for label in OP_LABELS:
            result = encode_op(label, "test")
            assert isinstance(result, str)
