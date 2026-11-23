"""Fast perf check of the ScanEngine bounded worker pool.

Analogous to the heavy `tests/perf/load_scanner.py --level a` (M7). The key
promise after the H1/H2 fix: `run_active_on_requests` executes seed×point×check
through a fixed pool of `concurrency` workers, not an eager `asyncio.gather`
over all tasks at once. We check that the peak of live asyncio.Tasks ≈ concurrency
(+ a few service ones), and that it does NOT grow with the size of the payload flow.

We take a lightweight active check (SQLi, ~150 payload) — with a small number of
seeds that is enough HTTP calls for the bounded pool to be visible, yet fast.
"""

from __future__ import annotations

import asyncio

import pytest
from pentool.modules.scanner.checks import SQLiCheck
from pentool.modules.scanner.engine import ScanEngine

from pentool.utils.parser import ParsedRequest
from tests.perf.fake_http_client import FakeHTTPClient

pytestmark = pytest.mark.perf


def _seeds(n: int) -> list[ParsedRequest]:
    return [
        ParsedRequest(
            method="GET",
            url=f"http://127.0.0.1:9/page/{i}?p=val{i}",
            headers={"Cookie": f"sess={i}", "User-Agent": "pentool-perf"},
            body="",
        )
        for i in range(n)
    ]


def _peak_during(concurrency: int, seeds: list[ParsedRequest]) -> int:
    """Run an active scan and return the peak of live tasks."""

    async def _monitor():
        engine = ScanEngine(db_path=":memory:", concurrency=concurrency, http_client=FakeHTTPClient())
        engine.register_checks([SQLiCheck()])
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
            await engine.run_active_on_requests(seed_requests=seeds)
        finally:
            stop["go"] = False
            peak = await peeker
        return peak

    return asyncio.run(_monitor())


def test_peak_tasks_bounded_by_concurrency():
    """The peak of live tasks must not significantly exceed concurrency."""
    concurrency = 5
    seeds = _seeds(40)
    peak = _peak_during(concurrency, seeds)
    # Bounded pool: concurrency workers + main + peeker + a couple of service ones.
    assert peak <= concurrency + 3, (
        f"Пик живых задач {peak} при concurrency={concurrency} — "
        f"ожидали bounded (~concurrency+неск.). Eager fan-out был бы "
        f"seed×points×checks≈сотни."
    )
    # At least the workers did start
    assert peak >= concurrency, "Воркеры почему-то не поднялись"


def test_peak_tasks_not_scaling_with_seeds():
    """Growing the number of seeds at a fixed concurrency must NOT raise the task peak."""
    c = 4
    peak_10 = _peak_during(c, _seeds(10))
    peak_40 = _peak_during(c, _seeds(40))
    # With a x4 volume of work the task peak must stay ≈ the same (bounded),
    # rather than grow 4x.
    assert abs(peak_40 - peak_10) <= 3, (
        f"Пик задач вырос с {peak_10} (10 seed) до {peak_40} (40 seed) при "
        f"concurrency={c} — ожидали стабильный bounded pool."
    )
