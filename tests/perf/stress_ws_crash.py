"""Стресс-тест прокси на WebSocket-гонку -> heap corruption.

Воспроизводит условия, при которых pentool падал с
"malloc_printerr: free(): corrupted unsorted chunks" в _PyGen_Finalize под
asyncio-циклом при интенсивном WebSocket-трафике + живом пуле executor.

Идея:
  - локальный WS-origin (описывает 101 Switching Protocols, затем эхо байт),
  - клиент открывает тысячи WebSocket-туннелей ЧЕРЕЗ ProxyServer (CONNECT+upgrade),
  - массово открывает/закрывает их пачками,
  - параллельно спамит executor-задачи (run_in_executor / asyncio.to_thread) и
    периодически гоняет gc.collect() — чтобы пересечь финализацию генераторов
    с активной кучей и живыми executor-потоками.

Запуск делается в отдельном подпроцессе: падение (SIGABRT) ловится по
returncode. При успешном завершении скрипт печатает итог.

Использование:
  python -m pytest -q tests/perf/stress_ws_crash.py --runstress
или напрямую:
  python tests/perf/stress_ws_crash.py [N_ITER] [BATCH]
"""

from __future__ import annotations

import asyncio
import gc
import logging
import sys
import time

logging.basicConfig(level=logging.WARNING)
# Отключить шум прокси, чтобы стресс-тест был сосредоточен на нагрузке.
logging.getLogger("pentool").setLevel(logging.CRITICAL)

from pentool.modules.proxy import ProxyServer  # noqa: E402

PROXY_HOST = "127.0.0.1"
ORIGIN_HOST = "127.0.0.1"


async def _ws_echo_origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Примитивный WS-origin: на первый запрос отвечает 101, дальше — эхо байт."""
    try:
        # Прочитать заголовки до \r\n\r\n
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
        writer.write(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        await writer.drain()
        # Эхо любых байт обратно
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
    """Открыть один WebSocket-туннель через прокси; вернуть (reader, writer)."""
    reader, writer = await asyncio.open_connection(PROXY_HOST, proxy_port)
    connect_req = (
        f"CONNECT {ORIGIN_HOST}:{origin_port} HTTP/1.1\r\n"
        f"Host: {ORIGIN_HOST}:{origin_port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n\r\n"
    )
    writer.write(connect_req.encode("utf-8"))
    await writer.drain()
    # Прочитать ответ (200/101) до пустой строки
    while True:
        line = await reader.readline()
        if not line or line in (b"\r\n", b"\n"):
            break
    return reader, writer


async def _executor_spammer(loop: asyncio.AbstractEventLoop, stop: asyncio.Future) -> None:
    """Держит пул ThreadPoolExecutor живым — имитация UI-work (refresh, save...)."""
    while not stop.done():
        # Мелкие задачи в общем пуле — как run_in_executor(None, ...) в UI.
        for _ in range(20):
            await loop.run_in_executor(None, time.sleep, 0.0)
        await asyncio.sleep(0.02)
        if (asyncio.get_running_loop().time() % 3) < 0.0001:
            gc.collect(0)


def _make_gen_cycle() -> list[Any]:
    """Генератор-рефцикл: next() держит генератор, который ссылается на фрейм,
    образующий цикл — типовой объект, финализируется в _PyGen_Finalize при GC."""
    def gen():
        x = []
        try:
            for i in range(100):
                x.append([i] * 8)
                yield i
        finally:
            # Держит стек живым — цикл gen frame -> x -> frame.
            del x
    g = gen()
    next(g)
    return [g]


async def _gc_pressure(stop: asyncio.Future) -> None:
    """Давит на GC-финализацию генераторов в ЖИВОМ loop: на каждом шаге создаёт
    пачку генератор-рефциклов и гоняет collection, пока открыты WS-туннели —
    имитация _PyGen_Finalize по активной куче параллельно рабочим корутинам."""
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
    # Закрыть ту же пачку синхронно (массовое завершение генераторов туннеля).
    for r, w in batch_conns:
        try:
            w.close()
            r.close()
        except Exception:
            pass
    # Дать корутинам туннелей завершиться и GC-у отработать.
    await asyncio.sleep(0.001)
    gc.collect()
    closed = len(batch_conns)
    return opened, closed


async def main(n_iter: int, batch: int) -> int:
    # Локальный WS-origin.
    origin_server = await asyncio.start_server(_ws_echo_origin, ORIGIN_HOST, 0)
    origin_port = origin_server.sockets[0].getsockname()[1]

    # Прокси.
    proxy = ProxyServer(host=PROXY_HOST, port=0, cert_dir="/tmp/pentool_stress_certs")
    await proxy.start()
    # proxy.port остаётся 0 при port=0 (эфемерный); реальный — из сокета.
    proxy_port = proxy._server.sockets[0].getsockname()[1]

    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    spam = asyncio.create_task(_executor_spammer(loop, stop))
    gcp = asyncio.create_task(_gc_pressure(stop))

    t0 = time.monotonic()
    total_open = total_close = 0
    held: list[tuple[object, object]] = []
    try:
        # Фаза 1: массовые волны открыть/закрыть (фрагментирует кучу).
        for _ in range(n_iter):
            op, cl = await _run_batch(proxy_port, origin_port, batch)
            total_open += op
            total_close += cl
        # Фаза 2 (ключевая): накопить МНОГО ОТКРЫТЫХ туннелей и не закрывать их —
        # оставить pending _handle_client на _READ_TIMEOUT. Затем резко stop() ->
        # массовая отмена -> _PyGen_Finalize массы генераторов на фоне кучи.
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
        # Резкий стоп на фоне открытых туннелей — кандидат на крэш.
        await proxy.stop()
        for _, w in held:
            try:
                w.close()
            except Exception:
                pass
        origin_server.close()
        await origin_server.wait_closed()

    dt = time.monotonic() - t0
    print(f"[stress] iter={n_iter} batch={batch} opened={total_open} closed={total_close} "
          f"held={len(held)} elapsed={dt:.1f}s — OK (no crash)")
    return 0


def _main() -> int:
    n_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    return asyncio.run(main(n_iter, batch))


if __name__ == "__main__":
    raise SystemExit(_main())
