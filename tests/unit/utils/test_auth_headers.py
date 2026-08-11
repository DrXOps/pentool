"""Tests for pentool/utils/auth_headers.py."""

from __future__ import annotations

from pentool.utils.auth_headers import AUTH_HEADER_KEYS, extract_auth_headers


class TestExtractAuthHeaders:
    def test_empty_headers_returns_empty(self):
        assert extract_auth_headers({}) == {}

    def test_none_like_falsy_returns_empty(self):
        assert extract_auth_headers({}) == {}

    def test_extracts_cookie(self):
        headers = {"Cookie": "PHPSESSID=abc123", "Host": "example.com"}
        result = extract_auth_headers(headers)
        assert result == {"Cookie": "PHPSESSID=abc123"}

    def test_extracts_authorization(self):
        headers = {"Authorization": "Bearer xyz", "User-Agent": "test"}
        result = extract_auth_headers(headers)
        assert result == {"Authorization": "Bearer xyz"}

    def test_case_insensitive_matching(self):
        headers = {"COOKIE": "a=b", "authorization": "Bearer z"}
        result = extract_auth_headers(headers)
        assert result == {"COOKIE": "a=b", "authorization": "Bearer z"}

    def test_preserves_original_key_casing(self):
        headers = {"X-Auth-Token": "tok123"}
        result = extract_auth_headers(headers)
        assert "X-Auth-Token" in result
        assert result["X-Auth-Token"] == "tok123"

    def test_ignores_non_auth_headers(self):
        headers = {
            "Host": "example.com",
            "Accept": "text/html",
            "Content-Type": "application/json",
        }
        assert extract_auth_headers(headers) == {}

    def test_multiple_auth_headers_all_extracted(self):
        headers = {
            "Cookie": "session=1",
            "Authorization": "Bearer tok",
            "X-Api-Key": "key123",
            "Host": "example.com",
        }
        result = extract_auth_headers(headers)
        assert set(result.keys()) == {"Cookie", "Authorization", "X-Api-Key"}

    def test_all_known_keys_recognized(self):
        headers = {k: "v" for k in AUTH_HEADER_KEYS}
        result = extract_auth_headers(headers)
        assert len(result) == len(AUTH_HEADER_KEYS)
