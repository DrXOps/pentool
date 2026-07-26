"""Unit tests for ScopeConfig (regex include/exclude) from scope_dialog.py."""

from __future__ import annotations

import pytest

from pentool.tui.dialogs.scope_dialog import (
    ScopeConfig,
    validate_patterns,
    _host_matches,
    _regex_match,
)


class TestHostMatches:
    def test_exact_match(self):
        assert _host_matches("example.com", "example.com")

    def test_exact_no_match(self):
        assert not _host_matches("example.com", "other.com")

    def test_wildcard_subdomain(self):
        assert _host_matches("*.example.com", "sub.example.com")

    def test_wildcard_no_match(self):
        assert not _host_matches("*.example.com", "example.com")

    def test_wildcard_deep(self):
        assert _host_matches("*.example.com", "a.b.example.com")

    def test_case_insensitive(self):
        assert _host_matches("EXAMPLE.COM", "example.com")

    def test_empty_pattern(self):
        assert not _host_matches("", "example.com")


class TestRegexMatch:
    def test_simple_pattern(self):
        assert _regex_match(r"/api/", "http://example.com/api/users")

    def test_no_match(self):
        assert not _regex_match(r"/admin/", "http://example.com/api/users")

    def test_extension_pattern(self):
        assert _regex_match(r"\.(php|asp)$", "http://example.com/page.php")

    def test_case_insensitive(self):
        assert _regex_match(r"example", "http://EXAMPLE.com/")

    def test_invalid_regex_no_crash(self):
        # Invalid regex — should return False, not crash
        result = _regex_match(r"[invalid", "http://example.com")
        assert result is False

    def test_empty_pattern_matches_all(self):
        # Empty string — matches all (re.search("", ...) → True)
        assert _regex_match("", "http://example.com")


class TestValidatePatterns:
    def test_valid_patterns(self):
        invalid = validate_patterns([r"\d+", r"https?://", r"[a-z]+"])
        assert invalid == []

    def test_invalid_pattern(self):
        invalid = validate_patterns([r"[invalid"])
        assert len(invalid) == 1
        assert r"[invalid" in invalid

    def test_mixed(self):
        invalid = validate_patterns([r"\d+", r"[bad", r"https://"])
        assert len(invalid) == 1
        assert r"[bad" in invalid

    def test_empty_list(self):
        assert validate_patterns([]) == []


class TestScopeConfigHosts:
    def test_empty_config_matches_all(self):
        cfg = ScopeConfig()
        assert cfg.matches("http://example.com/path")

    def test_host_list_match(self):
        cfg = ScopeConfig(hosts=["example.com"])
        assert cfg.matches("http://example.com/path")

    def test_host_list_no_match(self):
        cfg = ScopeConfig(hosts=["example.com"])
        assert not cfg.matches("http://other.com/path")

    def test_host_wildcard(self):
        cfg = ScopeConfig(hosts=["*.example.com"])
        assert cfg.matches("http://sub.example.com/path")

    def test_multiple_hosts(self):
        cfg = ScopeConfig(hosts=["example.com", "other.com"])
        assert cfg.matches("http://other.com/page")
        assert cfg.matches("http://example.com/page")
        assert not cfg.matches("http://third.com/page")


class TestScopeConfigRegexInclude:
    def test_include_match(self):
        cfg = ScopeConfig(regex_include=[r"/api/"])
        assert cfg.matches("http://example.com/api/users")

    def test_include_no_match(self):
        cfg = ScopeConfig(regex_include=[r"/api/"])
        assert not cfg.matches("http://example.com/public")

    def test_multiple_include_any_matches(self):
        cfg = ScopeConfig(regex_include=[r"/api/", r"/admin/"])
        assert cfg.matches("http://example.com/api/v1")
        assert cfg.matches("http://example.com/admin/panel")
        assert not cfg.matches("http://example.com/public")

    def test_include_empty_matches_all(self):
        cfg = ScopeConfig(regex_include=[])
        assert cfg.matches("http://example.com/anything")


class TestScopeConfigRegexExclude:
    def test_exclude_match_excluded(self):
        cfg = ScopeConfig(regex_exclude=[r"\.js$"])
        assert not cfg.matches("http://example.com/app.js")

    def test_exclude_no_match_passes(self):
        cfg = ScopeConfig(regex_exclude=[r"\.js$"])
        assert cfg.matches("http://example.com/api/users")

    def test_multiple_exclude(self):
        cfg = ScopeConfig(regex_exclude=[r"\.js$", r"/static/"])
        assert not cfg.matches("http://example.com/app.js")
        assert not cfg.matches("http://example.com/static/img.png")
        assert cfg.matches("http://example.com/api/data")

    def test_exclude_empty_excludes_nothing(self):
        cfg = ScopeConfig(regex_exclude=[])
        assert cfg.matches("http://example.com/anything")


class TestScopeConfigCombined:
    def test_host_and_include(self):
        cfg = ScopeConfig(
            hosts=["example.com"],
            regex_include=[r"/api/"],
        )
        assert cfg.matches("http://example.com/api/users")
        assert not cfg.matches("http://example.com/public")
        assert not cfg.matches("http://other.com/api/users")

    def test_host_and_exclude(self):
        cfg = ScopeConfig(
            hosts=["example.com"],
            regex_exclude=[r"\.js$"],
        )
        assert cfg.matches("http://example.com/api/users")
        assert not cfg.matches("http://example.com/app.js")
        assert not cfg.matches("http://other.com/api/users")

    def test_all_filters(self):
        cfg = ScopeConfig(
            hosts=["example.com"],
            regex_include=[r"/api/"],
            regex_exclude=[r"\.js$"],
        )
        assert cfg.matches("http://example.com/api/users")
        assert not cfg.matches("http://example.com/api/app.js")
        assert not cfg.matches("http://example.com/public")

    def test_host_list_property(self):
        cfg = ScopeConfig(hosts=["a.com", "b.com"])
        assert cfg.host_list == ["a.com", "b.com"]

    def test_dataclass_defaults(self):
        cfg = ScopeConfig()
        assert cfg.hosts == []
        assert cfg.regex_include == []
        assert cfg.regex_exclude == []
