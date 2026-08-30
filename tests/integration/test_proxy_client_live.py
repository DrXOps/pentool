"""Live integration test: ProxyClient drives the isolated daemon process."""

from __future__ import annotations

import pytest

from pentool.proxy.client import ProxyClient


def test_client_starts_daemon_and_controls_it():
    """Spawn the real daemon subprocess and exercise the socket API end-to-end."""
    client = ProxyClient(host="127.0.0.1", port=0, db_path="", cert_dir="/tmp/pentool_certs")
    try:
        client.start()
        assert client.is_running is True  # daemon booted and answered status

        client.set_intercept(True)
        assert client.intercept_enabled is True

        client.set_scope(["example.com"])
        assert "example.com" in client.scope

        resp = client._command({"cmd": "status"})
        assert resp.get("ok") is True
        assert resp.get("port") == client.port

        # read/control commands over IPC
        status = client.get_status()
        assert isinstance(status, dict)
        reqs = client.get_requests(limit=5)
        assert isinstance(reqs, list)
        client.clear_requests()
        assert client.get_requests() == []
    finally:
        client.stop()


def test_client_restart_idempotent():
    """start() after stop() must relaunch cleanly."""
    client = ProxyClient(host="127.0.0.1", port=0)
    try:
        client.start()
        assert client.is_running is True
        client.stop()
        assert client.is_running is False
        client.start()
        assert client.is_running is True
    finally:
        client.stop()


def test_client_unknown_command_graceful():
    client = ProxyClient(host="127.0.0.1", port=0)
    try:
        client.start()
        resp = client._command({"cmd": "no_such_cmd"})
        assert resp.get("ok") is False
    finally:
        client.stop()
