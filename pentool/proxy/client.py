"""ProxyClient — TUI-side facade over the isolated proxy daemon (П.3).

The proxy runs in its OWN process (see proxy/daemon.py). This client:

  * spawns the daemon subprocess on demand;
  * talks to it over TWO unix sockets (JSON commands/replies on one,
    push events on the other);
  * mirrors the public API of ProxyServer (start/stop/is_running/port/host/
    scope/intercept_*/set_intercept/set_scope/set_enforce_scope) so the TUI can
    treat it as a drop-in, without holding the ProxyServer object in memory;
  * runs a background reader thread on the event socket that re-emits proxy
    lifecycle events (ProxyRequestCaptured / ProxyRequestCompleted) back into
    the TUI-side EventBus, so downstream subscribers (HTTP History storage,
    ProxyScreen rows, SiteMap) keep working unchanged.

Two sockets are deliberate. The command socket is request/reply (one line in,
one line out). If push events shared that socket, an event arriving mid-
command would be read by ``_command`` as the reply and silently corrupt the
protocol. Separating the channels removes that whole class of bug.

Nothing in the TUI shares an asyncio loop or EventBus with the proxy anymore —
that is what removes the proxy-on-daemon-thread teardown races.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading

logger = logging.getLogger(__name__)


def time_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


class ProxyClient:
    """Spawns and drives the proxy daemon process over two unix sockets."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 8080,
                 cert_dir: str = "/tmp/pentool_certs", db_path: str = "") -> None:
        self.host = host
        self.port = port
        self.cert_dir = cert_dir
        self.db_path = db_path
        self._proc: subprocess.Popen | None = None
        self._cmd_sock_path: str = ""
        self._evt_sock_path: str = ""
        self._cmd_sock: socket.socket | None = None
        self._evt_sock: socket.socket | None = None
        self._tmp_dir: str = ""
        self._lock = threading.Lock()
        # Reader thread (event socket) state.
        self._reader: threading.Thread | None = None
        self._reader_stop = threading.Event()
        # Cached status fields (refreshed on demand) — these mirror the proxy
        # so `self._proxy` is a drop-in for ProxyServer at the TUI layer.
        self._running: bool = False
        self.intercept_enabled: bool = False
        self.scope: list[str] = []
        self.enforce_scope: bool = False

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Spawn the daemon and wait until both sockets are up."""
        if self.is_running:
            return
        self._tmp_dir = tempfile.mkdtemp(prefix="pentool-proxy-")
        cmd_sock = os.path.join(self._tmp_dir, "proxy.sock")
        evt_sock = os.path.join(self._tmp_dir, "events.sock")
        cmd = [
            sys.executable, "-m", "pentool.proxy.daemon",
            "--socket", cmd_sock,
            "--event-socket", evt_sock,
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
        self._cmd_sock_path = cmd_sock
        self._evt_sock_path = evt_sock
        self._cmd_sock = self._wait_socket(cmd_sock)
        self._evt_sock = self._wait_socket(evt_sock)
        if self._cmd_sock is None:
            self.cleanup()
            raise RuntimeError("proxy daemon did not come up on its command socket")
        if self._evt_sock is None:
            self.cleanup()
            raise RuntimeError("proxy daemon did not come up on its event socket")
        # Start the event reader thread before any proxy work can begin.
        self._start_reader()
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
            # Push the client-side startup prefs (set via property setters in
            # on_mount BEFORE start(), when no socket existed yet) into the
            # daemon so the proxy boots with the intended intercept/scope state.
            if self._intercept_enabled:
                try:
                    self.set_intercept(True)
                except Exception:  # noqa: BLE001
                    pass
            if self._scope:
                try:
                    self.set_scope(list(self._scope))
                except Exception:  # noqa: BLE001
                    pass
        except Exception:
            self.cleanup()
            raise

    def _wait_socket(self, path: str) -> socket.socket | None:
        """Wait up to ~10s for `path` to appear and be connectable."""
        deadline = 10.0
        waited = 0.0
        while waited < deadline:
            if os.path.exists(path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect(path)
                    return s
                except OSError:
                    time_sleep(0.1)
            time_sleep(0.1)
            waited += 0.1
        return None

    def _start_reader(self) -> None:
        """Start a background thread that drains the event socket and re-emits."""
        if self._reader is not None and self._reader.is_alive():
            return
        self._reader_stop.clear()
        self._reader = threading.Thread(
            target=self._reader_loop, daemon=True, name="proxy-events"
        )
        self._reader.start()

    def _reader_loop(self) -> None:
        """Read JSON lines from the event socket, re-emit into TUI EventBus.

        Runs in a daemon thread. Each line is a push event
        ``{"kind":"event","name":...,"data":...}``. We translate proxy capture/
        completion events back into EventBus events in the TUI process so all
        existing subscribers (HTTP History storage, ProxyScreen, SiteMap) work
        as if the proxy still lived in-memory.
        """
        sock = self._evt_sock
        if sock is None:
            return
        buf = b""
        sock.settimeout(0.25)  # wake the loop to observe _reader_stop
        try:
            while not self._reader_stop.is_set():
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break  # daemon closed the event channel
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8", "replace"))
                    except Exception:  # noqa: BLE001
                        continue
                    self._handle_event(msg)
        except Exception as exc:  # noqa: BLE001
            logger.debug("proxy event reader stopped: %s", exc)
        finally:
            self._reader_stop.set()

    def _handle_event(self, msg: dict) -> None:
        """Re-emit a single daemon event into the TUI-side EventBus."""
        if msg.get("kind") != "event":
            return
        name = msg.get("name")
        data = msg.get("data") or {}
        req = data.get("request")
        request_obj = None
        if req:
            try:
                from pentool.modules.proxy import InterceptedRequest
                try:
                    request_obj = InterceptedRequest.from_dict(req)
                except Exception:  # noqa: BLE001
                    request_obj = None
            except Exception:  # noqa: BLE001
                request_obj = None
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import (
                ProxyRequestCaptured,
                ProxyRequestCompleted,
            )
            bus = get_event_bus()
            if name == "captured":
                bus.emit(ProxyRequestCaptured(
                    source="proxy",
                    request_id=data.get("request_id", "") or getattr(request_obj, "id", ""),
                    method=(data.get("method") or getattr(request_obj, "method", "")),
                    url=(data.get("url") or getattr(request_obj, "url", "")),
                    host=(data.get("host") or ""),
                    request=request_obj,
                ))
            elif name == "completed":
                bus.emit(ProxyRequestCompleted(
                    source="proxy",
                    request_id=(data.get("request_id") or getattr(request_obj, "id", "")),
                    status_code=int(data.get("status_code") or 0),
                    request=request_obj,
                ))
        except Exception as exc:  # noqa: BLE001
            logger.debug("proxy event re-emit failed (%s): %s", name, exc)

    def stop(self) -> None:
        """Tell the daemon to stop its ProxyServer and clean up the sockets."""
        try:
            if self._cmd_sock is not None:
                self._command({"cmd": "stop"})
        except Exception:
            pass
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Stop the reader, close sockets, terminate the daemon process."""
        self._reader_stop.set()
        reader = self._reader
        if reader is not None and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=1.0)
        self._reader = None
        with self._lock:
            for attr in ("_cmd_sock", "_evt_sock"):
                s = getattr(self, attr)
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass
                setattr(self, attr, None)
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
        for path in (self._cmd_sock_path, self._evt_sock_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        if self._tmp_dir:
            try:
                os.rmdir(self._tmp_dir)
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
        # Tolerate pre-start calls (no socket yet): cache the desired state;
        # start() pushes it into the daemon. Mirrors ProxyServer.set_intercept
        # which tolerates being called while the proxy is not running.
        self.intercept_enabled = bool(enabled)
        if self._cmd_sock is not None:
            try:
                self._command({"cmd": "set_intercept", "enabled": bool(enabled)})
            except Exception:  # noqa: BLE001
                pass

    # Property mirror so `self._proxy.intercept_enabled = X` (used across the
    # TUI) propagates to the daemon instead of silently keeping a stale flag.
    @property
    def intercept_enabled(self) -> bool:
        return self._intercept_enabled

    @intercept_enabled.setter
    def intercept_enabled(self, value: bool) -> None:
        self._intercept_enabled = bool(value)

    def set_scope(self, hosts: list[str]) -> None:
        self.scope = list(hosts)
        if self._cmd_sock is not None:
            try:
                self._command({"cmd": "set_scope", "hosts": list(hosts)})
            except Exception:  # noqa: BLE001
                pass

    @property
    def scope(self) -> list[str]:
        return list(self._scope)

    @scope.setter
    def scope(self, hosts: list[str]) -> None:
        self._scope = list(hosts)

    def set_enforce_scope(self, enabled: bool) -> None:
        # Update the local mirror immediately (TUI re-reads it to sync the
        # toolbar checkbox); when connected the daemon is told too.
        self.enforce_scope = bool(enabled)
        if self._cmd_sock is not None:
            try:
                self._command({"cmd": "set_enforce_scope", "enabled": bool(enabled)})
            except Exception:  # noqa: BLE001
                pass

    def get_status(self) -> dict:
        resp = self._command({"cmd": "get_status"})
        return resp.get("status") or {}

    def get_requests(self, limit: int = 100, method: str | None = None,
                     host: str | None = None) -> list:
        resp = self._command({"cmd": "get_requests", "limit": limit,
                              "method": method, "host": host})
        return resp.get("requests") or []

    def find_request(self, req_id: str):
        """Fetch one intercepted request from the daemon by id (full obj)."""
        resp = self._command({"cmd": "find_request", "request_id": req_id})
        data = resp.get("request")
        if not data:
            return None
        try:
            from pentool.modules.proxy import InterceptedRequest
            return InterceptedRequest.from_dict(data)
        except Exception:  # noqa: BLE001
            return None

    def is_in_scope(self, host: str) -> bool:
        """Whether `host` is in scope (empty scope = everything in scope).

        Resolved in the daemon so wildcards match against the live scope.
        Falls back to a local host_in_scope check when not connected.
        """
        host = host or ""
        if self._cmd_sock is not None:
            try:
                resp = self._command({"cmd": "is_in_scope", "host": host})
                if isinstance(resp.get("in_scope"), bool):
                    return resp["in_scope"]
            except Exception:  # noqa: BLE001
                pass
        # Offline fallback mirrors ProxyServer.is_in_scope (empty scope = all).
        from pentool.utils.scope import host_in_scope
        return host_in_scope(host, self.scope)

    @property
    def match_replace_rules(self) -> list:
        """Fetch match-replace rules from the daemon (empty when offline)."""
        if self._cmd_sock is not None:
            try:
                resp = self._command({"cmd": "get_rules"})
                rules = resp.get("rules")
                if isinstance(rules, list):
                    return list(rules)
            except Exception:  # noqa: BLE001
                pass
        return []

    @match_replace_rules.setter
    def match_replace_rules(self, rules) -> None:
        """Push match-replace rules to the daemon (tolerated pre-start)."""
        serialized = []
        for r in rules:
            if hasattr(r, "to_dict"):
                serialized.append(r.to_dict())
            elif isinstance(r, dict):
                serialized.append(dict(r))
        if self._cmd_sock is not None:
            try:
                self._command({"cmd": "set_rules", "rules": serialized})
            except Exception:  # noqa: BLE001
                pass

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
        self.intercept_enabled = bool(resp.get("intercept", self._intercept_enabled))
        self.scope = list(resp.get("scope") or self._scope)

    def _command(self, cmd: dict) -> dict:
        """Send one command on the command socket and wait for its reply line."""
        if self._cmd_sock is None:
            raise RuntimeError("proxy client not connected")
        payload = (json.dumps(cmd) + "\n").encode("utf-8")
        with self._lock:
            self._cmd_sock.sendall(payload)
            data = b""
            # Bound each command's wait so a slow/closed daemon reply can never
            # hang the TUI socket loop (e.g. stop() cancelling proxy tasks).
            self._cmd_sock.settimeout(5.0)
            try:
                while b"\n" not in data:
                    chunk = self._cmd_sock.recv(4096)
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
                    self._cmd_sock.settimeout(None)
                except OSError:
                    pass
            line = data.split(b"\n", 1)[0]
        try:
            return json.loads(line.decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
