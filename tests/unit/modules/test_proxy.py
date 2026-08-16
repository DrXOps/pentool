"""Unit tests: modules/proxy.py

Covers: MatchReplaceRule, MatchReplaceEngine, ProxyServer (state, scope, intercept).
"""

from __future__ import annotations

from datetime import datetime, timezone
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
        assert "secret.com" in result      # header not touched
        assert "REDACTED=value" in result  # body modified

    def test_headers_only_scope(self) -> None:
        from pentool.modules.match_replace import MatchReplaceEngine, MatchReplaceRule
        engine = MatchReplaceEngine()
        engine.set_rules([MatchReplaceRule(id="1", match="secret", replace="REDACTED", scope="headers")])
        raw = "POST / HTTP/1.1\r\nHost: secret.com\r\n\r\nsecret=value"
        result = engine.apply_to_request(raw)
        assert "REDACTED.com" in result    # header modified
        assert "secret=value" in result   # body not touched


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
        # Empty scope → everything is in scope
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


class TestInterceptedRequestSerialization:
    def test_to_dict_roundtrip(self) -> None:
        from pentool.modules.proxy import InterceptedRequest
        from pentool.utils.parser import ParsedResponse
        req = InterceptedRequest(
            id="r1",
            method="POST",
            url="http://example.com/api",
            headers={"Host": "example.com"},
            body='{"a":1}',
            timestamp=datetime.now(timezone.utc),
            state="forwarded",
            is_https=True,
            response=ParsedResponse(status=200, reason="OK", headers={"X": "y"}, body="hello"),
        )
        d = req.to_dict()
        restored = InterceptedRequest.from_dict(d)
        assert restored.id == "r1"
        assert restored.method == "POST"
        assert restored.is_https is True
        assert restored.response is not None
        assert restored.response.status == 200
        assert restored.response.body == "hello"

    def test_from_dict_no_response(self) -> None:
        from pentool.modules.proxy import InterceptedRequest
        req = InterceptedRequest.from_dict({
            "id": "x", "method": "GET", "url": "http://h/", "headers": {},
            "body": "", "timestamp": "", "state": "waiting",
        })
        assert req.response is None
        assert req.state == "waiting"

    def test_to_parsed_request(self) -> None:
        from pentool.modules.proxy import InterceptedRequest
        req = InterceptedRequest(
            id="r", method="PUT", url="http://h/x", headers={"Host": "h"},
            body="b", timestamp=datetime.now(timezone.utc),
        )
        pr = req.to_parsed_request()
        assert pr.method == "PUT"
        assert pr.url == "http://h/x"
        assert pr.body == "b"


class TestProxyWsHelpers:
    def test_build_frame_masked(self) -> None:
        from pentool.modules.proxy import ProxyServer
        frame = ProxyServer._build_ws_frame(0x1, b"abc", mask=False)
        # opcode=1 text, no mask, payload len 3, payload
        assert frame[0] == 0x81
        assert frame[1] == 3
        assert frame[2:] == b"abc"

    def test_parse_frame_roundtrip(self) -> None:
        from pentool.modules.proxy import ProxyServer
        frame = ProxyServer._build_ws_frame(0x2, b"hello", mask=False)
        parsed = ProxyServer._parse_ws_frame(frame)
        assert parsed is not None
        opcode, fin, payload, _ = parsed
        assert opcode == 0x2
        assert payload == b"hello"


class TestProxyRawSerializers:
    def test_request_to_raw(self) -> None:
        from pentool.modules.proxy import ProxyServer
        from pentool.utils.parser import ParsedRequest
        req = ParsedRequest(method="GET", url="http://h/path", headers={"Host": "h"}, body="")
        raw = ProxyServer._request_to_raw(req)
        assert raw.startswith("GET http://h/path HTTP/1.1")

    def test_request_to_raw_with_body(self) -> None:
        from pentool.modules.proxy import ProxyServer
        from pentool.utils.parser import ParsedRequest
        req = ParsedRequest(method="POST", url="http://h/", headers={"Host": "h"}, body="payload")
        raw = ProxyServer._request_to_raw(req)
        assert raw.endswith("payload")

    def test_response_to_raw(self) -> None:
        from pentool.modules.proxy import ProxyServer
        from pentool.utils.parser import ParsedResponse
        resp = ParsedResponse(status=200, reason="OK", headers={"X": "1"}, body="hi")
        raw = ProxyServer._response_to_raw(resp)
        assert "HTTP" in raw and "200 OK" in raw

    def test_response_to_bytes_removes_encoding_headers(self) -> None:
        from pentool.modules.proxy import ProxyServer
        from pentool.utils.parser import ParsedResponse
        resp = ParsedResponse(status=200, reason="OK",
                              headers={"transfer-encoding": "chunked",
                                       "content-encoding": "gzip"},
                              body="hello")
        b = ProxyServer._response_to_bytes(resp)
        text = b.decode()
        assert "transfer-encoding" not in text
        assert "content-encoding" not in text
        assert "Content-Length: 5" in text
        assert text.endswith("hello")


class TestProxyRequestHistory:
    def test_add_and_ring_buffer(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        server._requests_max = 3
        for i in range(5):
            server._add_request(InterceptedRequest(
                id=str(i), method="GET", url=f"http://h/{i}", headers={},
                body="", timestamp=datetime.now(timezone.utc)))
        assert len(server.requests) == 3
        assert server.requests[0].id == "2"

    def test_get_requests_filters(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        server._add_request(InterceptedRequest(
            id="1", method="GET", url="http://a.com/x", headers={}, body="",
            timestamp=datetime.now(timezone.utc)))
        server._add_request(InterceptedRequest(
            id="2", method="POST", url="http://b.com/y", headers={}, body="",
            timestamp=datetime.now(timezone.utc)))
        # newest first
        assert server.get_requests(limit=1)[0].id == "2"
        # method filter
        only_post = server.get_requests(method="post")
        assert [r.id for r in only_post] == ["2"]
        # host filter (substring)
        only_a = server.get_requests(host="a.com")
        assert [r.id for r in only_a] == ["1"]

    def test_replace_requests_atomic(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        server._add_request(InterceptedRequest(
            id="old", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc)))
        new = [InterceptedRequest(
            id="new", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc))]
        server.replace_requests(new)
        assert [r.id for r in server.requests] == ["new"]

    def test_clear_requests(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        server._add_request(InterceptedRequest(
            id="x", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc)))
        server.clear_requests()
        assert server.requests == []

    def test_find_request(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        server._add_request(InterceptedRequest(
            id="target", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc)))
        assert server._find_request("target") is not None
        assert server._find_request("missing") is None


class TestProxyDecisionFlow:
    def test_forward_waiting_request(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        req = InterceptedRequest(
            id="f", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc), state="waiting")
        server._add_request(req)
        server.forward("f", modified_raw="MODIFIED")
        assert req.state == "forwarded"
        assert req._modified_raw == "MODIFIED"

    def test_drop_waiting_request(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        req = InterceptedRequest(
            id="d", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc), state="waiting")
        server._add_request(req)
        server.drop("d")
        assert req.state == "dropped"

    def test_forward_already_resolved_noop(self) -> None:
        from pentool.modules.proxy import ProxyServer, InterceptedRequest
        server = ProxyServer()
        req = InterceptedRequest(
            id="r", method="GET", url="http://h/", headers={}, body="",
            timestamp=datetime.now(timezone.utc), state="forwarded")
        server._add_request(req)
        server.forward("r")  # state already not waiting → no-op, unchanged
        assert req.state == "forwarded"


class TestProxyEnforceScope:
    def test_set_enforce_scope_no_loop(self) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer()
        server._loop = None
        server.set_enforce_scope(True)
        assert server.enforce_scope is True

    def test_set_enforce_scope_with_loop(self) -> None:
        from unittest.mock import MagicMock
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer()
        loop = MagicMock()
        loop.is_running.return_value = True
        server._loop = loop
        server.set_enforce_scope(True)
        loop.call_soon_threadsafe.assert_called_once()

    def test_is_in_scope_wildcard(self) -> None:
        from pentool.modules.proxy import ProxyServer
        server = ProxyServer()
        server.scope = ["*.example.com"]
        assert server.is_in_scope("sub.example.com") is True
        assert server.is_in_scope("other.com") is False
