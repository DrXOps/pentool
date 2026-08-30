"""Proxy daemon process (П.3 isolation).

Runs the ProxyServer in its OWN process/event-loop, so nothing in the TUI
shares memory or an asyncio loop with the proxy. It:

  * listens on a unix socket for JSON commands (start/stop/status/
    set_intercept/set_scope/set_enforce_scope);
  * wraps the ProxyServer and performs those commands on its own loop;
  * forwards capture/completion events back over the socket as JSON
    {"kind":"event","name":..., "data":...}.

The TUI talks only to this socket (see proxy/client.py). This removes the
'proxy on a daemon thread sharing Memory/EventBus with the TUI' failure class.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading

from pentool.core.logging import get_logger

logger = get_logger(__name__)

# Max message size for a single JSON command/event line.
_MAX_LINE = 1 << 20


class ProxyDaemon:
    """Serves the ProxyServer over a unix socket command/event channel."""

    def __init__(self, socket_path: str, *, host: str, port: int,
                 cert_dir: str, db_path: str) -> None:
        self._socket_path = socket_path
        self._host = host
        self._port = port
        self._cert_dir = cert_dir
        self._db_path = db_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.AbstractServer | None = None
        self._sock: socket.socket | None = None
        self._clients: set[socket.socket] = set()
        self._proxy = None  # created lazily on first start

    # -- run / entry ---------------------------------------------------------

    async def run_forever(self) -> None:
        """Create the ProxyServer, open the command socket, serve requests."""
        from pentool.modules.proxy import ProxyServer

        self._loop = asyncio.get_running_loop()
        self._proxy = ProxyServer(
            host=self._host, port=self._port,
            cert_dir=self._cert_dir, db_path=self._db_path,
        )
        self._start_listener()
        logger.info("proxy-daemon listening on %s (port %s)", self._socket_path, self._port)
        # Keep the process alive serving the command socket. Proxy start/stop
        # runs on demand via commands (single predictable lifecycle).
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    def _start_listener(self) -> None:
        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except OSError:
                pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self._socket_path)
        sock.listen(16)
        sock.setblocking(False)
        self._sock = sock
        loop = asyncio.get_running_loop()
        self._future = asyncio.ensure_future(self._accept_loop())

    async def _accept_loop(self) -> None:
        assert self._sock is not None
        loop = asyncio.get_running_loop()
        while True:
            conn, _addr = await loop.sock_accept(self._sock)
            conn.setblocking(False)
            self._clients.add(conn)
            asyncio.get_running_loop().create_task(self._handle_client(conn))

    async def _handle_client(self, conn: socket.socket) -> None:
        loop = asyncio.get_running_loop()
        buf = b""
        try:
            while True:
                data = await loop.sock_recv(conn, 4096)
                if not data:
                    break
                buf += data
                # Process one message per line (JSONL)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    resp = await self._dispatch(json.loads(line.decode("utf-8", "replace")))
                    await loop.sock_sendall(conn, (json.dumps(resp) + "\n").encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, EOFError):
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("proxy-daemon client error: %s", exc)
        finally:
            self._clients.discard(conn)
            try:
                conn.close()
            except Exception:
                pass

    async def _dispatch(self, cmd: dict) -> dict:
        """Execute a command dict and return a JSON-serializable response."""
        name = cmd.get("cmd")
        if name == "start":
            await self._proxy.start()
            return {"ok": True, "running": self._proxy.is_running,
                    "port": self._proxy.port}
        if name == "stop":
            await self._proxy.stop()
            return {"ok": True, "running": self._proxy.is_running}
        if name == "status":
            return {"ok": True, "running": self._proxy.is_running,
                    "port": self._proxy.port, "host": self._proxy.host,
                    "intercept": self._proxy.intercept_enabled,
                    "scope": list(self._proxy.scope)}
        if name == "set_intercept":
            self._proxy.set_intercept(bool(cmd.get("enabled", False)))
            return {"ok": True}
        if name == "set_scope":
            self._proxy.set_scope(cmd.get("hosts") or [])
            return {"ok": True}
        if name == "set_enforce_scope":
            self._proxy.set_enforce_scope(bool(cmd.get("enabled", False)))
            return {"ok": True}
        if name == "get_status":
            return {"ok": True, "status": self._proxy.get_status()}
        if name == "get_requests":
            reqs = self._proxy.get_requests(
                limit=cmd.get("limit", 100),
                method=cmd.get("method"),
                host=cmd.get("host"),
            )
            return {"ok": True, "requests": [r.to_dict() for r in reqs]}
        if name == "forward":
            self._proxy.forward(cmd.get("request_id", ""), cmd.get("modified"))
            return {"ok": True}
        if name == "drop":
            self._proxy.drop(cmd.get("request_id", ""))
            return {"ok": True}
        if name == "clear_requests":
            self._proxy.clear_requests()
            return {"ok": True}
        if name == "replace_requests":
            from pentool.modules.proxy import InterceptedRequest
            reqs = [InterceptedRequest.from_dict(d) for d in (cmd.get("requests") or [])]
            self._proxy.replace_requests(reqs)
            return {"ok": True}
        return {"ok": False, "error": f"unknown cmd: {name}"}

    # -- send events to all connected clients -------------------------------

    def send_event(self, name: str, data: dict) -> None:
        try:
            payload = (json.dumps({"kind": "event", "name": name, "data": data}) + "\n").encode("utf-8")
        except TypeError:
            logger.debug("proxy-daemon: could not encode event %s", name)
            return
        for conn in list(self._clients):
            try:
                conn.sendall(payload)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                self._clients.discard(conn)


def main(argv: list[str] | None = None) -> None:
    """CLI entry for the proxy daemon process.

    Args come from sys.argv (used by 'python -m pentool.proxy_daemon').
    """
    import argparse
    import sys

    p = argparse.ArgumentParser(prog="pentool-proxy-daemon")
    p.add_argument("--socket", required=True, help="unix socket path")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--cert-dir", default="/tmp/pentool_certs")
    p.add_argument("--db", default="")
    a = p.parse_args(argv if argv is not None else sys.argv[1:])

    daemon = ProxyDaemon(
        a.socket, host=a.host, port=a.port, cert_dir=a.cert_dir, db_path=a.db,
    )
    asyncio.run(daemon.run_forever())


if __name__ == "__main__":
    main()
