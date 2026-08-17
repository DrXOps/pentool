"""Быстрый perf-проверка bounded worker pool ScanEngine.

Аналог тяжёлого `tests/perf/load_scanner.py --level a` (M7). Ключевое
обещание после фикса H1/H2: `run_active_on_requests` исполняет seed×point×check
через фиксированный пул `concurrency` воркеров, а не eager `asyncio.gather`
на все задачи сразу. Проверяем, что пик живых asyncio.Tasks ≈ concurrency
(+ несколько служебных), и что он НЕ растёт с размером payload-потока.

Берём лёгкий активный чек (SQLi, ~150 payload) — на малом числе seed этого
достаточно много HTTP-вызовов, чтобы bounded-pool был различим, но быстро.
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
    """Запустить активный скан и вернуть пик живых задач."""
    async def _monitor():
        engine = ScanEngine(db_path=":memory:", concurrency=concurrency,
                            http_client=FakeHTTPClient())
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
    """Пик живых задач не должен сильно превышать concurrency."""
    concurrency = 5
    seeds = _seeds(40)
    peak = _peak_during(concurrency, seeds)
    # Бounded pool: concurrency воркеров + main + peeker + пара служебных.
    assert peak <= concurrency + 3, (
        f"Пик живых задач {peak} при concurrency={concurrency} — "
        f"ожидали bounded (~concurrency+неск.). Eager fan-out был бы "
        f"seed×points×checks≈сотни."
    )
    # Хотя бы воркеры запустились
    assert peak >= concurrency, "Воркеры почему-то не поднялись"


def test_peak_tasks_not_scaling_with_seeds():
    """Рост числа seed при фикс. concurrency НЕ должен расти пик задач."""
    c = 4
    peak_10 = _peak_during(c, _seeds(10))
    peak_40 = _peak_during(c, _seeds(40))
    # Пик задач при x4 объёме работы должен остаться ≈ тем же (bounded),
    # а не вырасти в 4 раза.
    assert abs(peak_40 - peak_10) <= 3, (
        f"Пик задач вырос с {peak_10} (10 seed) до {peak_40} (40 seed) при "
        f"concurrency={c} — ожидали стабильный bounded pool."
    )
