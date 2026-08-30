"""Unit tests: proxy/client.py — facade over the proxy daemon socket."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from pentool.proxy.client import ProxyClient


def _make_client() -> ProxyClient:
    c = ProxyClient(host="127.0.0.1", port=1234)
    c._sock = MagicMock()
    return c


class TestCommand:
    def test_sends_json_and_parses_reply(self):
        c = _make_client()
        c._sock.recv.return_value = b'{"ok": true, "running": true}\n'
        resp = c._command({"cmd": "status"})
        # sent one line ending with \n
        sent = c._sock.sendall.call_args[0][0]
        assert sent.endswith(b"\n")
        assert b'"cmd": "status"' in sent
        assert resp == {"ok": True, "running": True}

    def test_bad_reply_is_tolerated(self):
        c = _make_client()
        c._sock.recv.return_value = b"not-json\n"
        resp = c._command({"cmd": "status"})
        assert resp.get("ok") is False

    def test_not_connected_raises(self):
        c = ProxyClient()
        with pytest.raises(RuntimeError):
            c._command({"cmd": "status"})


class TestApi:
    def test_is_running_false_when_no_process(self):
        c = ProxyClient()
        assert c.is_running is False

    def test_apply_status_updates_fields(self):
        c = _make_client()
        c._apply_status({"running": True, "port": 9999, "host": "h",
                         "intercept": True, "scope": ["a.com"]})
        assert c._running is True
        assert c.port == 9999
        assert c.intercept_enabled is True
        assert c.scope == ["a.com"]

    def test_is_running_polls_daemon(self):
        c = _make_client()
        c._proc = MagicMock()
        c._command = MagicMock(return_value={"running": True})
        assert c.is_running is True

    def test_set_intercept_sends_command(self):
        c = _make_client()
        c.intercept_enabled = False
        c._sock.recv.return_value = b'{"ok": true}\n'
        c.set_intercept(True)
        sent = c._sock.sendall.call_args[0][0]
        assert b'"enabled": true' in sent
        assert c.intercept_enabled is True

    def test_set_scope_sends_hosts(self):
        c = _make_client()
        c._sock.recv.return_value = b'{"ok": true}\n'
        c.set_scope(["x.io"])
        sent = c._sock.sendall.call_args[0][0]
        assert b'"hosts": ["x.io"]' in sent


class TestCleanup:
    def test_cleanup_terminates_process(self):
        proc = MagicMock()
        c = ProxyClient()
        c._proc = proc
        c._sock = MagicMock()
        c.cleanup()
        proc.terminate.assert_called_once()
        proc.wait.assert_called()
