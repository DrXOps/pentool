"""Unit tests: api/proxy_api.py

Covers: ProxyAPI without proxy (safe defaults), ProxyAPI with mock ProxyServer.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pentool.api.proxy_api import ProxyAPI, InterceptedRequest, MatchReplaceRule


class TestProxyAPIWithoutProxy:
    """Tests for ProxyAPI without an initialized ProxyServer."""

    def test_is_running_false(self) -> None:
        api = ProxyAPI()
        assert api.is_running() is False

    def test_get_port_default(self) -> None:
        api = ProxyAPI()
        assert api.get_port() == 8080

    def test_get_host_default(self) -> None:
        api = ProxyAPI()
        assert api.get_host() == "127.0.0.1"

    def test_get_status_safe_defaults(self) -> None:
        api = ProxyAPI()
        status = api.get_status()
        assert status["running"] is False
        assert status["host"] == "127.0.0.1"
        assert status["port"] == 8080
        assert status["intercept_enabled"] is False
        assert status["scope"] == []

    def test_get_requests_empty(self) -> None:
        api = ProxyAPI()
        assert api.get_requests() == []

    def test_get_scope_empty(self) -> None:
        api = ProxyAPI()
        assert api.get_scope() == []

    def test_get_match_replace_rules_empty(self) -> None:
        api = ProxyAPI()
        assert api.get_match_replace_rules() == []

    def test_find_request_none(self) -> None:
        api = ProxyAPI()
        assert api.find_request("some-id") is None

    def test_get_intercept_false(self) -> None:
        api = ProxyAPI()
        assert api.get_intercept() is False

    def test_forward_raises_without_proxy(self) -> None:
        api = ProxyAPI()
        with pytest.raises(RuntimeError):
            api.forward("req-id")

    def test_drop_raises_without_proxy(self) -> None:
        api = ProxyAPI()
        with pytest.raises(RuntimeError):
            api.drop("req-id")

    def test_set_intercept_no_error(self) -> None:
        """set_intercept without proxy — silently ignored."""
        api = ProxyAPI()
        api.set_intercept(True)  # no error

    def test_set_scope_no_error(self) -> None:
        api = ProxyAPI()
        api.set_scope(["example.com"])  # no error

    def test_clear_requests_no_error(self) -> None:
        api = ProxyAPI()
        api.clear_requests()  # no error


class TestProxyAPIWithMockProxy:
    """Tests for ProxyAPI with mock ProxyServer."""

    def _make_api(self, mock_proxy) -> ProxyAPI:
        api = ProxyAPI()
        api.set_proxy(mock_proxy)
        return api

    def test_is_running_delegates(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        # is_running — @property on ProxyServer, accessed as attribute
        assert api.is_running() is True

    def test_get_port_delegates(self, mock_proxy_server) -> None:
        mock_proxy_server.port = 9090
        api = self._make_api(mock_proxy_server)
        assert api.get_port() == 9090

    def test_get_host_delegates(self, mock_proxy_server) -> None:
        mock_proxy_server.host = "0.0.0.0"
        api = self._make_api(mock_proxy_server)
        assert api.get_host() == "0.0.0.0"

    def test_get_status_delegates(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        status = api.get_status()
        assert status["running"] is True
        mock_proxy_server.get_status.assert_called_once()

    def test_get_intercept_true(self, mock_proxy_server) -> None:
        mock_proxy_server.intercept_enabled = True
        api = self._make_api(mock_proxy_server)
        assert api.get_intercept() is True

    def test_set_intercept_updates_proxy(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        api.set_intercept(True)
        # set_intercept is now thread-safe — calls ProxyServer.set_intercept()
        mock_proxy_server.set_intercept.assert_called_once_with(True)

    def test_set_scope_calls_proxy(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        api.set_scope(["example.com"])
        mock_proxy_server.set_scope.assert_called_once_with(["example.com"])

    def test_get_scope_delegates(self, mock_proxy_server) -> None:
        mock_proxy_server.scope = ["example.com", "*.test.com"]
        api = self._make_api(mock_proxy_server)
        scope = api.get_scope()
        assert "example.com" in scope

    def test_forward_delegates(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        api.forward("req-123")
        mock_proxy_server.forward.assert_called_once_with("req-123", None)

    def test_forward_with_modified_raw(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        api.forward("req-123", "GET / HTTP/1.1\r\n\r\n")
        mock_proxy_server.forward.assert_called_once_with(
            "req-123", "GET / HTTP/1.1\r\n\r\n"
        )

    def test_drop_delegates(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        api.drop("req-456")
        mock_proxy_server.drop.assert_called_once_with("req-456")

    def test_clear_requests_delegates(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        api.clear_requests()
        mock_proxy_server.clear_requests.assert_called_once()

    def test_set_match_replace_rules(self, mock_proxy_server) -> None:
        api = self._make_api(mock_proxy_server)
        rules = [MatchReplaceRule(match="x", replace="y")]
        api.set_match_replace_rules(rules)
        assert mock_proxy_server.match_replace_rules == rules
