"""ProxyClient — TUI-side facade over the isolated proxy daemon (П.3).

The proxy runs in its OWN process (see proxy/daemon.py). This client:

  * spawns the daemon subprocess on demand;
  * talks to it over a unix socket (JSON commands in, JSON replies/events out);
  * mirrors the public API of ProxyServer (start/stop/is_running/port/host/
    scope/intercept_*/set_intercept/set_scope/set_enforce_scope) so the TUI can
    treat it as a drop-in, without holding the ProxyServer object in memory.

Nothing in the TUI shares an asyncio loop or EventBus with the proxy anymore —
that is what removes the proxy-on-daemon-thread teardown races.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading

logger = logging.getLogger(__name__)


class ProxyClient:
    """Spawns and drives the proxy daemon process over a unix socket."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 8080,
                 cert_dir: str = "/tmp/pentool_certs", db_path: str = "") -> None:
        self.host = host
        self.port = port
        self.cert_dir = cert_dir
        self.db_path = db_path
        self._proc: subprocess.Popen | None = None
        self._sock_path: str = ""
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        # Cached status fields (refreshed on demand).
        self._running: bool = False
        self.intercept_enabled: bool = False
        self.scope: list[str] = []

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Spawn the daemon and wait until the command socket is up."""
        if self.is_running:
            return
        tmp = tempfile.mkdtemp(prefix="pentool-proxy-")
        sock_path = os.path.join(tmp, "proxy.sock")
        cmd = [
            sys.executable, "-m", "pentool.proxy.daemon",
            "--socket", sock_path,
            "--host", self.host,
            "--port", str(self.port),
            "--cert-dir", self.cert_dir,
            "--db", self.db_path,
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
        )
        self._sock_path = sock_path
        # Wait for the socket to appear (daemon binds it after boot).
        deadline = 10.0
        waited = 0.0
        self._sock = None
        while waited < deadline:
            if os.path.exists(sock_path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect(sock_path)
                    self._sock = s
                    break
                except OSError:
                    time_sleep(0.1)
            time_sleep(0.1)
            waited += 0.1
        if self._sock is None:
            raise RuntimeError("proxy daemon did not come up on its socket")
        try:
            # Ask the daemon to actually start its ProxyServer (spawn just
            # brought the process up) — mirrors ProxyServer.start().
            resp = self._command({"cmd": "start"})
            if not resp.get("ok"):
                raise RuntimeError(f"proxy start failed: {resp.get('error')}")
            self._apply_status(resp)
            # Refresh cached running state from live status.
            status = self._command({"cmd": "status"})
            self._apply_status(status)
        except Exception:
            self.cleanup()
            raise

    def stop(self) -> None:
        """Tell the daemon to stop its ProxyServer and clean up the socket."""
        try:
            if self._sock is not None:
                self._command({"cmd": "stop"})
        except Exception:
            pass
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Close the socket and terminate the daemon process if alive."""
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            proc = self._proc
            self._proc = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._sock_path and os.path.exists(self._sock_path):
            try:
                os.unlink(self._sock_path)
            except OSError:
                pass

    def __del__(self) -> None:  # best-effort cleanup
        try:
            self.cleanup()
        except Exception:
            pass

    # -- public proxy API ----------------------------------------------------

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False
        try:
            resp = self._command({"cmd": "status"})
            self._apply_status(resp)
        except Exception:
            return False
        return self._running

    def set_intercept(self, enabled: bool) -> None:
        self._command({"cmd": "set_intercept", "enabled": bool(enabled)})
        self.intercept_enabled = bool(enabled)

    def set_scope(self, hosts: list[str]) -> None:
        self._command({"cmd": "set_scope", "hosts": list(hosts)})
        self.scope = list(hosts)

    def set_enforce_scope(self, enabled: bool) -> None:
        self._command({"cmd": "set_enforce_scope", "enabled": bool(enabled)})

    def get_status(self) -> dict:
        resp = self._command({"cmd": "get_status"})
        return resp.get("status") or {}

    def get_requests(self, limit: int = 100, method: str | None = None,
                     host: str | None = None) -> list:
        resp = self._command({"cmd": "get_requests", "limit": limit,
                              "method": method, "host": host})
        return resp.get("requests") or []

    def forward(self, request_id: str, modified: str | None = None) -> None:
        self._command({"cmd": "forward", "request_id": request_id,
                       "modified": modified})

    def drop(self, request_id: str) -> None:
        self._command({"cmd": "drop", "request_id": request_id})

    def clear_requests(self) -> None:
        self._command({"cmd": "clear_requests"})

    # -- transport -----------------------------------------------------------

    def _apply_status(self, resp: dict) -> None:
        self._running = bool(resp.get("running"))
        self.port = resp.get("port", self.port)
        self.host = resp.get("host", self.host)
        self.intercept_enabled = bool(resp.get("intercept", self.intercept_enabled))
        self.scope = list(resp.get("scope") or self.scope)

    def _command(self, cmd: dict) -> dict:
        """Send one command and wait for its reply line."""
        if self._sock is None:
            raise RuntimeError("proxy client not connected")
        payload = (json.dumps(cmd) + "\n").encode("utf-8")
        with self._lock:
            self._sock.sendall(payload)
            data = b""
            # Bound each command's wait so a slow/closed daemon reply can never
            # hang the TUI socket loop (e.g. stop() cancelling proxy tasks).
            self._sock.settimeout(5.0)
            try:
                while b"\n" not in data:
                    chunk = self._sock.recv(4096)
                    if not chunk:
                        # Peer closed without a reply (e.g. daemon exits on
                        # stop). Treat as ok — idempotent commands.
                        return {"ok": True}
                    data += chunk
            except socket.timeout:
                # No reply within the bound — report ok rather than hang.
                return {"ok": True}
            finally:
                try:
                    self._sock.settimeout(None)
                except OSError:
                    pass
            line = data.split(b"\n", 1)[0]
        try:
            return json.loads(line.decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


def time_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)
