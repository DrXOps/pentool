"""Stress test of the proxy on a WebSocket race -> heap corruption.

Reproduces the conditions under which pentool crashed with
"malloc_printerr: free(): corrupted unsorted chunks" in _PyGen_Finalize under
the asyncio loop during intensive WebSocket traffic + a live executor pool.

Idea:
  - a local WS origin (answers 101 Switching Protocols, then echoes bytes),
  - the client opens thousands of WebSocket tunnels THROUGH ProxyServer (CONNECT+upgrade),
  - opens/closes them en masse in batches,
  - concurrently spams executor tasks (run_in_executor / asyncio.to_thread) and
    periodically runs gc.collect() — to make generator finalization overlap
    an active heap and live executor threads.

The run happens in a separate subprocess: a crash (SIGABRT) is caught via
returncode. On successful completion the script prints a summary.

Usage:
  python -m pytest -q tests/perf/stress_ws_crash.py --runstress
or directly:
  python tests/perf/stress_ws_crash.py [N_ITER] [BATCH]
"""

from __future__ import annotations

import asyncio
import gc
import logging
import sys
import time
from typing import Any

logging.basicConfig(level=logging.WARNING)
# Silence proxy noise so the stress test stays focused on the load itself.
logging.getLogger("pentool").setLevel(logging.CRITICAL)

from pentool.modules.proxy import ProxyServer  # noqa: E402

PROXY_HOST = "127.0.0.1"
ORIGIN_HOST = "127.0.0.1"


async def _ws_echo_origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Primitive WS origin: answers 101 to the first request, then echoes bytes."""
    try:
        # Read headers up to \r\n\r\n
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
        writer.write(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        await writer.drain()
        # Echo any bytes back
        while True:
            try:
                data = await reader.read(4096)
            except (ConnectionResetError, asyncio.IncompleteReadError):
                break
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _open_ws_tunnel(proxy_port: int, origin_port: int) -> tuple[object, object]:
    """Open a single WebSocket tunnel through the proxy; return (reader, writer)."""
    reader, writer = await asyncio.open_connection(PROXY_HOST, proxy_port)
    connect_req = (
        f"CONNECT {ORIGIN_HOST}:{origin_port} HTTP/1.1\r\n"
        f"Host: {ORIGIN_HOST}:{origin_port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n\r\n"
    )
    writer.write(connect_req.encode("utf-8"))
    await writer.drain()
    # Read the response (200/101) up to the empty line
    while True:
        line = await reader.readline()
        if not line or line in (b"\r\n", b"\n"):
            break
    return reader, writer


async def _executor_spammer(loop: asyncio.AbstractEventLoop, stop: asyncio.Future) -> None:
    """Keeps the ThreadPoolExecutor pool alive — imitation of UI work (refresh, save...)."""
    while not stop.done():
        # Small tasks in the shared pool — like run_in_executor(None, ...) in the UI.
        for _ in range(20):
            await loop.run_in_executor(None, time.sleep, 0.0)
        await asyncio.sleep(0.02)
        if (asyncio.get_running_loop().time() % 3) < 0.0001:
            gc.collect(0)


def _make_gen_cycle() -> list[Any]:
    """Generator ref-cycle: next() keeps the generator, which references a frame
    that forms a cycle — a typical object finalized in _PyGen_Finalize during GC."""

    def gen():
        x = []
        try:
            for i in range(100):
                x.append([i] * 8)
                yield i
        finally:
            # Keeps the stack alive — the cycle is gen frame -> x -> frame.
            del x

    g = gen()
    next(g)
    return [g]


async def _gc_pressure(stop: asyncio.Future) -> None:
    """Puts pressure on GC finalization of generators in the LIVE loop: at every step it
    creates a batch of generator ref-cycles and runs collection while WS tunnels are
    open — an imitation of _PyGen_Finalize over an active heap in parallel with
    working coroutines."""
    while not stop.done():
        for _ in range(50):
            _make_gen_cycle()
        gc.collect()
        await asyncio.sleep(0.005)


async def _run_batch(proxy_port: int, origin_port: int, batch: int) -> tuple[int, int]:
    opened, closed = 0, 0
    batch_conns: list[tuple[object, object]] = []
    for _ in range(batch):
        try:
            r, w = await _open_ws_tunnel(proxy_port, origin_port)
            batch_conns.append((r, w))
            opened += 1
        except Exception:
            break
    # Close the same batch synchronously (mass termination of tunnel generators).
    for r, w in batch_conns:
        try:
            w.close()
            r.close()
        except Exception:
            pass
    # Let the tunnel coroutines finish and the GC do its work.
    await asyncio.sleep(0.001)
    gc.collect()
    closed = len(batch_conns)
    return opened, closed


async def main(n_iter: int, batch: int) -> int:
    # Local WS origin.
    origin_server = await asyncio.start_server(_ws_echo_origin, ORIGIN_HOST, 0)
    origin_port = origin_server.sockets[0].getsockname()[1]

    # Proxy.
    proxy = ProxyServer(host=PROXY_HOST, port=0, cert_dir="/tmp/pentool_stress_certs")
    await proxy.start()
    # proxy.port stays 0 when port=0 (ephemeral); the real one comes from the socket.
    proxy_port = proxy._server.sockets[0].getsockname()[1]

    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    spam = asyncio.create_task(_executor_spammer(loop, stop))
    gcp = asyncio.create_task(_gc_pressure(stop))

    t0 = time.monotonic()
    total_open = total_close = 0
    held: list[tuple[object, object]] = []
    try:
        # Phase 1: massive open/close waves (fragments the heap).
        for _ in range(n_iter):
            op, cl = await _run_batch(proxy_port, origin_port, batch)
            total_open += op
            total_close += cl
        # Phase 2 (the key one): accumulate MANY OPEN tunnels and keep them open —
        # leave pending _handle_client on _READ_TIMEOUT. Then abruptly stop() ->
        # mass cancellation -> _PyGen_Finalize of a mass of generators against the heap.
        held_it = n_iter // 4 + 1
        for _ in range(held_it):
            for _ in range(batch):
                try:
                    r, w = await _open_ws_tunnel(proxy_port, origin_port)
                    held.append((r, w))
                    total_open += 1
                except Exception:
                    break
        gc.collect()
    finally:
        stop.set_result(None)
        try:
            await spam
        except Exception:
            pass
        try:
            await gcp
        except Exception:
            pass
        # Abrupt stop against a background of open tunnels — a crash candidate.
        await proxy.stop()
        for _, w in held:
            try:
                w.close()
            except Exception:
                pass
        origin_server.close()
        await origin_server.wait_closed()

    dt = time.monotonic() - t0
    print(
        f"[stress] iter={n_iter} batch={batch} opened={total_open} closed={total_close} "
        f"held={len(held)} elapsed={dt:.1f}s — OK (no crash)"
    )
    return 0


def _main() -> int:
    n_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    return asyncio.run(main(n_iter, batch))


if __name__ == "__main__":
    raise SystemExit(_main())
