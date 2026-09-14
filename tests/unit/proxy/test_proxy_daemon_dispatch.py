"""Unit tests: proxy/daemon.py — command dispatch error handling."""

from __future__ import annotations

import pytest

from pentool.proxy.daemon import ProxyDaemon


def _make_daemon() -> ProxyDaemon:
    """Build a bare daemon with mocked internals so dispatch runs without sockets."""
    import types
    d = ProxyDaemon.__new__(ProxyDaemon)
    proxy = types.SimpleNamespace(
        is_running=False,
        port=8080,
        host="127.0.0.1",
        intercept_enabled=False,
        scope=[],
    )
    proxy.set_intercept = lambda enabled: setattr(proxy, 'intercept_enabled', bool(enabled))
    proxy.set_scope = lambda hosts: setattr(proxy, 'scope', list(hosts))
    proxy.is_in_scope = lambda host: host in proxy.scope
    d._proxy = proxy
    return d


class TestDispatchStart:
    @pytest.mark.asyncio
    async def test_start_ok(self):
        d = _make_daemon()

        async def _start():
            d._proxy.is_running = True
        d._proxy.start = _start

        resp = await d._dispatch({"cmd": "start"})
        assert resp["ok"] is True
        assert resp["running"] is True

    @pytest.mark.asyncio
    async def test_start_failure_returns_error_not_raises(self):
        """When proxy.start() throws, dispatch must return {ok: false} with the
        cause — NOT crash the daemon / drop the connection (which caused the
        misleading 'Broken pipe' on the client)."""
        d = _make_daemon()

        async def _boom():
            raise RuntimeError("Address already in use")
        d._proxy.start = _boom

        resp = await d._dispatch({"cmd": "start"})
        assert resp["ok"] is False
        assert "Address already in use" in resp.get("error", "")

    @pytest.mark.asyncio
    async def test_start_os_error_returned(self):
        d = _make_daemon()

        async def _boom():
            raise OSError(98, "Address already in use")
        d._proxy.start = _boom

        resp = await d._dispatch({"cmd": "start"})
        assert resp["ok"] is False
        assert "Address already in use" in resp.get("error", "")

    @pytest.mark.asyncio
    async def test_unknown_cmd(self):
        d = _make_daemon()
        resp = await d._dispatch({"cmd": "nonsense"})
        assert resp["ok"] is False
        assert "unknown" in resp.get("error", "")


class TestDispatchStatus:
    @pytest.mark.asyncio
    async def test_status_returns_state(self):
        d = _make_daemon()
        resp = await d._dispatch({"cmd": "status"})
        assert resp["ok"] is True
        assert resp["running"] is False
        assert resp["port"] == 8080


class TestDispatchSet:
    @pytest.mark.asyncio
    async def test_set_intercept(self):
        d = _make_daemon()
        resp = await d._dispatch({"cmd": "set_intercept", "enabled": True})
        assert resp["ok"] is True
        assert d._proxy.intercept_enabled is True

    @pytest.mark.asyncio
    async def test_set_scope(self):
        d = _make_daemon()
        resp = await d._dispatch({"cmd": "set_scope", "hosts": ["a.com"]})
        assert resp["ok"] is True
        assert d._proxy.scope == ["a.com"]
