"""Unit-тесты: modules/proxy.py

Покрывает: MatchReplaceRule, MatchReplaceEngine, ProxyServer (состояние, scope, intercept).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestMatchReplaceRule:
    def test_simple_replace(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(match="admin", replace="user")])
        assert engine._apply_rules("user=admin&pass=x", engine.rules) == "user=user&pass=x"

    def test_regex_replace(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(match=r"\d+", replace="NUM", is_regex=True)])
        assert engine._apply_rules("id=123&count=456", engine.rules) == "id=NUM&count=NUM"

    def test_disabled_rule_skipped(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(match="secret", replace="REDACTED", enabled=False)])
        assert engine._apply_rules("token=secret", engine.rules) == "token=secret"

    def test_multiple_rules_in_order(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([
            MatchReplaceRule(match="a", replace="b", id="1"),
            MatchReplaceRule(match="b", replace="c", id="2"),
        ])
        assert engine._apply_rules("a", engine.rules) == "c"

    def test_invalid_regex_does_not_raise(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(match="[invalid", replace="x", is_regex=True, id="1")])
        result = engine._apply_rules("some text", engine.rules)
        assert result == "some text"

    def test_to_dict_from_dict_roundtrip(self) -> None:
        from pentool.modules.match_replace import MatchReplaceRule
        rule = MatchReplaceRule(
            id="test",
            match="X-Debug", replace="", target="request", scope="headers"
        )
        data = rule.to_dict()
        restored = MatchReplaceRule.from_dict(data)
        assert restored.match == rule.match
        assert restored.target == rule.target
        assert restored.scope == rule.scope

    def test_rule_has_auto_id(self) -> None:
        from pentool.modules.match_replace import MatchReplaceRule
        rule = MatchReplaceRule(id="auto", match="x", replace="y")
        assert rule.id
        assert len(rule.id) > 0

    def test_apply_rules_empty_list(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine
        engine = MatchReplaceEngine()
        text = "unchanged text"
        assert engine._apply_rules(text, []) == text


class TestMatchReplaceScope:
    def test_body_only_scope(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(id="1", match="secret", replace="REDACTED", scope="body")])
        raw = "POST / HTTP/1.1\r\nHost: secret.com\r\n\r\nsecret=value"
        result = engine.apply_to_request(raw)
        assert "secret.com" in result      # заголовок не тронут
        assert "REDACTED=value" in result  # тело изменено

    def test_headers_only_scope(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(id="1", match="secret", replace="REDACTED", scope="headers")])
        raw = "POST / HTTP/1.1\r\nHost: secret.com\r\n\r\nsecret=value"
        result = engine.apply_to_request(raw)
        assert "REDACTED.com" in result    # заголовок изменён
        assert "secret=value" in result   # тело не тронуто


class TestProxyServerState:
    def test_not_running_initially(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(host="127.0.0.1", port=19081,
                             cert_dir=str(tmp_path / "certs"))
        assert server.is_running is False

    def test_empty_requests_initially(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(host="127.0.0.1", port=19082,
                             cert_dir=str(tmp_path / "certs"))
        assert server.requests == []

    def test_get_status_not_running(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(host="127.0.0.1", port=19083,
                             cert_dir=str(tmp_path / "certs"))
        status = server.get_status()
        assert status["running"] is False
        assert status["port"] == 19083

    def test_intercept_disabled_by_default(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        assert server.intercept_enabled is False

    def test_set_intercept(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        server.intercept_enabled = True
        assert server.intercept_enabled is True

    def test_scope_empty_by_default(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        assert server.scope == []

    def test_set_scope(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        server.set_scope(["example.com", "*.test.com"])
        assert "example.com" in server.scope

    def test_in_scope_exact_match(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        server.set_scope(["example.com"])
        assert server.is_in_scope("example.com") is True

    def test_not_in_scope(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        server.set_scope(["example.com"])
        assert server.is_in_scope("other.com") is False

    def test_empty_scope_matches_all(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        # Пустой scope → всё в scope
        assert server.is_in_scope("anything.com") is True

    def test_clear_requests(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        server.clear_requests()
        assert server.requests == []

    def test_match_replace_rules_empty_by_default(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        assert server.match_replace_rules == []

    def test_set_match_replace_rules(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        from pentool.modules.match_replace import MatchReplaceRule
        server = ProxyServer(cert_dir=str(tmp_path / "certs"))
        rules = [MatchReplaceRule(id="1", match="x", replace="y")]
        server.match_replace_rules = rules
        assert len(server.match_replace_rules) == 1


class TestProxyServerStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, tmp_path: Path) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer(
            host="127.0.0.1",
            port=19091,
            cert_dir=str(tmp_path / "certs"),
        )
        await server.start()
        assert server.is_running is True
        await server.stop()
        assert server.is_running is False
