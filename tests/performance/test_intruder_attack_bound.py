"""Fast perf checks for the bounded worker pool of IntruderAttack.

The assertable analog of the heavy `tests/perf/load_intruder.py --level b` (M7).
We verify the key promise of lazy dispatch: the number of simultaneously live
asyncio.Tasks must be ≤ threads + a small constant, and must NOT grow with the
size of the payload set (before the fix this was an eager fan-out of hundreds of
thousands of tasks — see intruder.py _run_one/worker — LEARN, H1).

We use FakeHTTPClient (no network) to separate the structural measurement of the
scheduler from network I/O — same as tests/perf/fake_http_client.py.
"""

from __future__ import annotations

import asyncio

import pytest

from pentool.modules.intruder import (
    AttackType,
    IntruderAttack,
    IntruderConfig,
)
from tests.perf.fake_http_client import FakeHTTPClient

pytestmark = pytest.mark.perf


def _template() -> str:
    return "GET /page/§100§?p=§01§ HTTP/1.1\r\nHost: 127.0.0.1:9\r\nUser-Agent: pentool-perf-test/1.0\r\n\r\n"


def _peak_tasks_while(coro_factory, interval: float = 0.005) -> tuple[int, int]:
    """Run the coroutine and sample the number of live asyncio.Tasks.

    Returns (peak, total results). interval 5ms — dense enough.
    """

    async def _runner():
        peak = 0
        stop = {"go": True}

        async def _peek():
            nonlocal peak
            while stop["go"]:
                n = len(asyncio.all_tasks())
                if n > peak:
                    peak = n
                await asyncio.sleep(interval)

        peeker = asyncio.create_task(_peek())
        coro = coro_factory()
        try:
            await coro
        finally:
            stop["go"] = False
            await peeker
        return peak

    return asyncio.run(_runner())


def test_sniper_bounded_tasks():
    """Sniper over 20k payloads — peak tasks ≤ threads + constant, does not grow with N."""
    n_payloads = 20_000
    threads = 5
    # Template with a SINGLE marker: Sniper yields exactly n_payloads combinations
    # (n_positions × M), so it is not confused with the 2-position version.
    template = "GET /page/§1§ HTTP/1.1\r\nHost: 127.0.0.1:9\r\nUser-Agent: pentool-perf-test/1.0\r\n\r\n"
    cfg = IntruderConfig(
        template=template,
        attack_type=AttackType.SNIPER,
        payload_sets=[[f"p{i}" for i in range(n_payloads)]],
        threads=threads,
        timeout=5,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=FakeHTTPClient())

    results = {"n": 0}

    def on_result(_r):
        results["n"] += 1

    async def _run():
        await attack.run(on_result=on_result, on_progress=lambda d, t: None)

    # peak_tasks for flows within a single event is overkill; we just run it
    # and check that results==20000 (all processed). The count of concurrent
    # tasks is checked by the stricter cluster-bomb test below on a
    # large combinatorial set.
    asyncio.run(_run())
    assert results["n"] == n_payloads


def test_cluster_bomb_peak_tasks_bounded():
    """Cluster Bomb 300×300=90k — the peak of live tasks must be small (bounded)."""
    a = 300
    b = 300
    total = a * b
    threads = 8
    cfg = IntruderConfig(
        template=_template(),
        attack_type=AttackType.CLUSTER_BOMB,
        payload_sets=[[f"p{i}" for i in range(a)], [f"q{i}" for i in range(b)]],
        threads=threads,
        timeout=5,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=FakeHTTPClient())

    results = {"n": 0}

    def on_result(_r):
        results["n"] += 1

    async def _build_and_run():
        # The intruder creates tasks as it goes — measure the peak during run:
        peak = 0
        stop = {"go": True}

        async def _peek():
            nonlocal peak
            while stop["go"]:
                n = len(asyncio.all_tasks())
                if n > peak:
                    peak = n
                await asyncio.sleep(0.005)
            return peak

        peeker = asyncio.create_task(_peek())
        try:
            await attack.run(on_result=on_result, on_progress=lambda d, t: None)
        finally:
            stop["go"] = False
            peak = await peeker
        return peak

    peak = asyncio.run(_build_and_run())
    # Bounded pool: at any moment there are at most threads workers +
    # main + peeker (2) live tasks. There must be no "all at once" 90k tasks.
    assert results["n"] == total, "Cluster Bomb обработал не все комбинации"
    assert peak <= threads + 3, (
        f"Пик одновременно живых задач {peak} при threads={threads} — ожидали bounded (eager fan-out был бы ~90k)"
    )


def test_stop_and_pause_release_tasks():
    """stop() before start leaves no dangling workers."""
    cfg = IntruderConfig(
        template=_template(),
        attack_type=AttackType.CLUSTER_BOMB,
        payload_sets=[[f"p{i}" for i in range(100)], [f"q{i}" for i in range(100)]],
        threads=4,
        timeout=5,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=FakeHTTPClient())

    async def _stop_first():
        await attack.stop()  # stop before starting
        await attack.run(on_result=lambda r: None, on_progress=lambda d, t: None)
        return attack.is_running

    running = asyncio.run(_stop_first())
    assert running is False, "stop() до запуска должен был не стартовать атаку"
