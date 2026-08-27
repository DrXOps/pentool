"""Unit tests: pentool.utils.scope.host_in_scope().

This is the single shared scope-matching helper used by both Proxy
(ProxyServer.is_in_scope) and Spider. Original coverage lived in a
security-class that also had to be removed; consolidated here so the utility
has its own behavioral tests, including the case-insensitivity + port-strip
semantics that only this module exercises.
"""
from __future__ import annotations

import pytest

from pentool.utils.scope import host_in_scope


class TestHostInScope:
    def test_empty_scope_allows_all(self) -> None:
        assert host_in_scope("example.com", []) is True
        assert host_in_scope("evil.com", []) is True

    def test_scope_allows_listed_host(self) -> None:
        assert host_in_scope("example.com", ["example.com"]) is True

    def test_scope_blocks_unlisted(self) -> None:
        assert host_in_scope("evil.com", ["example.com"]) is False

    def test_wildcard_scope(self) -> None:
        assert host_in_scope("sub.example.com", ["*.example.com"]) is True

    def test_wildcard_blocks_unrelated(self) -> None:
        # A wildcard pattern for one domain must not admit an unrelated host.
        assert host_in_scope("evil.com", ["*.example.com"]) is False

    def test_wildcard_matches_bare_parent(self) -> None:
        # Per host_in_scope()'s contract, *.example.com also matches the bare
        # parent domain (subdomain-or-exact), so example.com IS admitted.
        assert host_in_scope("example.com", ["*.example.com"]) is True

    def test_scope_case_insensitive(self) -> None:
        # host and patterns are normalized to lower-case by the helper.
        assert host_in_scope("EXAMPLE.COM", ["example.com"]) is True
        assert host_in_scope("example.com", ["Example.COM"]) is True

    def test_scope_strips_port_by_default(self) -> None:
        assert host_in_scope("example.com:8080", ["example.com"]) is True
        assert host_in_scope("example.com", ["example.com:8080"]) is True

    def test_scope_strip_port_false(self) -> None:
        assert host_in_scope("example.com:8080", ["example.com"], strip_port=False) is False

    def test_empty_pattern_skipped(self) -> None:
        assert host_in_scope("example.com", ["", "example.com"]) is True
