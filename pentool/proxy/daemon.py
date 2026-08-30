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

    def __init__(self, socket_path: str, event_socket_path: str,
                 *, host: str, port: int, cert_dir: str, db_path: str) -> None:
        self._socket_path = socket_path
        self._event_socket_path = event_socket_path
        self._host = host
        self._port = port
        self._cert_dir = cert_dir
        self._db_path = db_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.AbstractServer | None = None
        self._sock: socket.socket | None = None
        self._evt_sock: socket.socket | None = None
        self._clients: set[socket.socket] = set()       # command connections
        self._event_clients: set[socket.socket] = set()
        # Event connections are buffered: conn -> queue of encoded event lines.
        # A per-conn async writer drains the queue via sock_sendall. This is
        # what makes event delivery lossless under bursts — the old sync
        # conn.sendall (on a non-blocking socket) dropped whole events when the
        # kernel buffer filled.
        self._event_queues: dict[socket.socket, asyncio.Queue] = {}
        # Bound each event queue so an unreadable peer can't grow memory
        # without limit; overflow drops the OLDEST events (counted, not silent).
        self._event_queue_max = 20_000
        self._event_dropped = {"count": 0}
        self._proxy = None  # created lazily on first start

    # -- run / entry ---------------------------------------------------------

    async def run_forever(self) -> None:
        """Create the ProxyServer, open sockets, subscribe to proxy events."""
        from pentool.modules.proxy import ProxyServer

        self._loop = asyncio.get_running_loop()
        self._proxy = ProxyServer(
            host=self._host, port=self._port,
            cert_dir=self._cert_dir, db_path=self._db_path,
        )
        self._start_listener()
        self._start_event_listener()
        self._subscribe_proxy_events()
        logger.info("proxy-daemon listening on %s (port %s)", self._socket_path, self._port)
        # Keep the process alive serving the command socket. Proxy start/stop
        # runs on demand via commands (single predictable lifecycle).
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    def _subscribe_proxy_events(self) -> None:
        """Bridge ProxyServer's EventBus emissions to the event socket.

        The ProxyServer in this process publishes ProxyRequestCaptured /
        ProxyRequestCompleted onto the process-local EventBus (get_event_bus()).
        We subscribe to those and forward them to all event-socket clients so
        the TUI-side ProxyClient reader can re-emit them into the TUI's bus.
        """
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import (
                ProxyRequestCaptured,
                ProxyRequestCompleted,
            )
            bus = get_event_bus()

            def _on_captured(event) -> None:
                try:
                    req = event.request
                    data = {
                        "request_id": event.request_id,
                        "method": event.method,
                        "url": event.url,
                        "host": event.host,
                        "request": req.to_dict() if req is not None else None,
                    }
                except Exception:  # noqa: BLE001
                    data = {"request": None}
                self.send_event("captured", data)

            def _on_completed(event) -> None:
                try:
                    req = event.request
                    data = {
                        "request_id": event.request_id,
                        "status_code": int(event.status_code),
                        "request": req.to_dict() if req is not None else None,
                    }
                except Exception:  # noqa: BLE001
                    data = {"request": None}
                self.send_event("completed", data)

            bus.subscribe(ProxyRequestCaptured, _on_captured)
            bus.subscribe(ProxyRequestCompleted, _on_completed)
            self._captured_handler = _on_captured
            self._completed_handler = _on_completed
        except Exception as exc:  # noqa: BLE001
            logger.error("proxy-daemon: event subscription failed: %s", exc)

    def _start_listener(self) -> None:
        """Bind the command socket."""
        sock = self._bind_listener(self._socket_path)
        self._sock = sock
        self._command_listen_task = asyncio.ensure_future(
            self._accept_loop(sock, self._clients, self._handle_cmd_client)
        )

    def _start_event_listener(self) -> None:
        """Bind the event (push) socket."""
        sock = self._bind_listener(self._event_socket_path)
        self._evt_sock = sock
        self._event_listen_task = asyncio.ensure_future(
            self._accept_loop(sock, self._event_clients, self._handle_evt_client,
                              register_evt=True)
        )

    def _bind_listener(self, path: str) -> socket.socket:
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(path)
        except OSError as exc:
            raise RuntimeError(f"could not bind {path}: {exc}") from exc
        sock.listen(16)
        sock.setblocking(False)
        return sock

    async def _accept_loop(self, sock: socket.socket,
                           clients: set[socket.socket],
                           handler, *, register_evt: bool = False) -> None:
        loop = asyncio.get_running_loop()
        while True:
            conn, _addr = await loop.sock_accept(sock)
            conn.setblocking(False)
            clients.add(conn)
            if register_evt:
                # Event connection: give it a bounded buffer + a writer task.
                q: asyncio.Queue = asyncio.Queue(maxsize=self._event_queue_max)
                self._event_queues[conn] = q
                task = asyncio.get_running_loop().create_task(
                    self._event_writer(conn, q)
                )
                # Keep a ref so the writer task isn't GC'd prematurely.
                wts = getattr(self, "_event_writer_tasks", None)
                if wts is None:
                    wts = self._event_writer_tasks = []
                wts.append(task)
            asyncio.get_running_loop().create_task(handler(conn, *(
                (q,) if register_evt else ())))

    async def _handle_evt_client(self, conn: socket.socket,
                                 queue: asyncio.Queue | None = None) -> None:
        """Hold an event connection open until the peer disconnects.

        The reader side only detects the peer going away (it is a one-way
        push channel); the actual sending is done by _event_writer draining
        the per-connection queue.
        """
        try:
            loop = asyncio.get_running_loop()
            while True:
                data = await loop.sock_recv(conn, 4096)
                if not data:
                    break
        except (ConnectionResetError, BrokenPipeError, EOFError):
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._event_queues.pop(conn, None)
            self._event_clients.discard(conn)
            try:
                conn.close()
            except Exception:
                pass

    async def _event_writer(self, conn: socket.socket,
                            queue: asyncio.Queue) -> None:
        """Drain one event connection's queue, sending lines via sock_sendall.

        Runs in the daemon's asyncio loop, so sends never block the loop; the
        queue absorbs bursts so no event is lost (unless the bounded max is
        hit, in which case the oldest are dropped and counted).
        """
        loop = asyncio.get_running_loop()
        try:
            while True:
                payload = await queue.get()
                try:
                    await loop.sock_sendall(conn, payload)
                except OSError:
                    break
        finally:
            # Connection gone: drop its queue ref.
            self._event_queues.pop(conn, None)

    async def _handle_cmd_client(self, conn: socket.socket) -> None:
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

    async def _handle_evt_client(self, conn: socket.socket) -> None:
        """Hold an event connection open until the peer disconnects.

        Events are pushed by the daemon (send_event → _event_clients); the
        peer does not have to send anything. We just keep the socket alive so
        the accept loop doesn't leak connections.
        """
        try:
            loop = asyncio.get_running_loop()
            while True:
                data = await loop.sock_recv(conn, 4096)
                if not data:
                    break
                # Ignore anything the reader sends; it is a one-way channel.
        except (ConnectionResetError, BrokenPipeError, EOFError):
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._event_clients.discard(conn)
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
        if name == "is_in_scope":
            host = cmd.get("host", "")
            return {"ok": True, "in_scope": bool(self._proxy.is_in_scope(host))}
        if name == "get_rules":
            rules = list(self._proxy.match_replace_rules)
            return {"ok": True, "rules": [r.to_dict() for r in rules]}
        if name == "set_rules":
            from pentool.modules.match_replace import MatchReplaceRule
            rules = [MatchReplaceRule.from_dict(d) for d in (cmd.get("rules") or [])]
            self._proxy.match_replace_rules = rules
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
        if name == "find_request":
            req = self._proxy._find_request(cmd.get("request_id", ""))
            if req is None:
                return {"ok": True, "request": None}
            return {"ok": True, "request": req.to_dict()}
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

    # -- send events to all connected event clients -------------------------

    def send_event(self, name: str, data: dict) -> None:
        try:
            payload = (json.dumps({"kind": "event", "name": name, "data": data}) + "\n").encode("utf-8")
        except TypeError:
            logger.debug("proxy-daemon: could not encode event %s", name)
            return
        for conn, queue in list(self._event_queues.items()):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Bounded buffer exceeded — drop the OLDEST queued event so the
                # newest traffic is preserved, and count the loss (not silent).
                self._event_dropped["count"] += 1
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
            except Exception:
                pass


def main(argv: list[str] | None = None) -> None:
    """CLI entry for the proxy daemon process.

    Args come from sys.argv (used by 'python -m pentool.proxy_daemon').
    """
    import argparse
    import sys

    p = argparse.ArgumentParser(prog="pentool-proxy-daemon")
    p.add_argument("--socket", required=True, help="unix command socket path")
    p.add_argument("--event-socket", required=True, help="unix event (push) socket path")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--cert-dir", default="/tmp/pentool_certs")
    p.add_argument("--db", default="")
    a = p.parse_args(argv if argv is not None else sys.argv[1:])

    daemon = ProxyDaemon(
        a.socket, a.event_socket,
        host=a.host, port=a.port, cert_dir=a.cert_dir, db_path=a.db,
    )
    asyncio.run(daemon.run_forever())


if __name__ == "__main__":
    main()
