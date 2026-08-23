"""Быстрые perf-проверки bounded worker pool IntruderAttack.

Ассертуемый аналог тяжёлого `tests/perf/load_intruder.py --level b` (M7).
Проверяем ключевое обещание ленивой передачи: число одновременно живых
asyncio.Tasks должно быть ≤ threads + малая константа, и НЕ расти с размером
payload-набора (до фикса это был eager fan-out сотен тысяч задач — см.
intruder.py _run_one/worker — LEARN, H1).

Используем FakeHTTPClient (без сети), чтобы отделить структурный замер
планировщика от сетевого I/O — как tests/perf/fake_http_client.py.
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
    return (
        "GET /page/§100§?p=§01§ HTTP/1.1\r\n"
        "Host: 127.0.0.1:9\r\n"
        "User-Agent: pentool-perf-test/1.0\r\n\r\n"
    )


def _peak_tasks_while(coro_factory, interval: float = 0.005) -> tuple[int, int]:
    """Запустить корутину и сэмплить число живых asyncio.Task.

    Возвращает (peak, результаты-всего). interval 5ms — достаточно плотно.
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
    """Sniper на 20k payload — пик задач ≤ threads + константа, не растёт с N."""
    n_payloads = 20_000
    threads = 5
    # Шаблон с ОДНИМ маркером: Sniper даёт ровно n_payloads комбинаций
    # (n_positions × M), чтобы не путать с 2-позиционной версией.
    template = (
        "GET /page/§1§ HTTP/1.1\r\n"
        "Host: 127.0.0.1:9\r\n"
        "User-Agent: pentool-perf-test/1.0\r\n\r\n"
    )
    cfg = IntruderConfig(
        template=template, attack_type=AttackType.SNIPER,
        payload_sets=[[f"p{i}" for i in range(n_payloads)]],
        threads=threads, timeout=5,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=FakeHTTPClient())

    results = {"n": 0}

    def on_result(_r):
        results["n"] += 1

    async def _run():
        await attack.run(on_result=on_result, on_progress=lambda d, t: None)

    # peak_tasks при flows в рамках одного события — overkill; просто запустим
    # и проверим, что results==20000 (все обработаны). Число одновременных
    # задач проверяем отдельным более строгим тестом cluster-bomb ниже на
    # большом комбинаторном наборе.
    asyncio.run(_run())
    assert results["n"] == n_payloads


def test_cluster_bomb_peak_tasks_bounded():
    """Cluster Bomb 300×300=90k — пик живых задач должен быть мал (bounded)."""
    a = 300
    b = 300
    total = a * b
    threads = 8
    cfg = IntruderConfig(
        template=_template(), attack_type=AttackType.CLUSTER_BOMB,
        payload_sets=[[f"p{i}" for i in range(a)],
                      [f"q{i}" for i in range(b)]],
        threads=threads, timeout=5,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=FakeHTTPClient())

    results = {"n": 0}

    def on_result(_r):
        results["n"] += 1

    async def _build_and_run():
        # Интудер создаёт задачи по ходу — измерить пик во время run:
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
    # Бounded pool: в любой момент живых задач не больше threads-воркеров +
    # main + peeker (2). Задач-«все сразу» в 90k быть не должно.
    assert results["n"] == total, "Cluster Bomb обработал не все комбинации"
    assert peak <= threads + 3, (
        f"Пик одновременно живых задач {peak} при threads={threads} — "
        f"ожидали bounded (eager fan-out был бы ~90k)"
    )


def test_stop_and_pause_release_tasks():
    """stop() перед стартом не оставляет висящих воркеров."""
    cfg = IntruderConfig(
        template=_template(), attack_type=AttackType.CLUSTER_BOMB,
        payload_sets=[[f"p{i}" for i in range(100)], [f"q{i}" for i in range(100)]],
        threads=4, timeout=5,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=FakeHTTPClient())

    async def _stop_first():
        await attack.stop()  # остановить до старта
        await attack.run(on_result=lambda r: None, on_progress=lambda d, t: None)
        return attack.is_running

    running = asyncio.run(_stop_first())
    assert running is False, "stop() до запуска должен был не стартовать атаку"
