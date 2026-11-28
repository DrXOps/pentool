"""Live adaptive Intruder: a real HTTP server pushing back (429 / refused connection).

The unit tests feed the controller synthetic signals. This one runs the whole attack over real
sockets against a local server, which is the closest automated equivalent of the manual "local
server with an artificial limit" check:

* three 429s in a row lower the parallelism inside the user's ceiling and land in the journal;
* a target that refuses connections stops the attack with the error reason instead of hammering
  a dead endpoint;
* a healthy response keeps the attack going to the end.
"""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from pentool.modules.intruder import AttackType, IntruderAttack, IntruderConfig

TEMPLATE = "GET /§F§ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"


class _Server:
    """A local HTTP server whose refusal count and status are decided by the test."""

    def __init__(self, statuses: list[int], hold_s: float = 0.0) -> None:
        self.statuses = statuses
        self.hold_s = hold_s
        self.seen = 0

    async def handle(self, request: web.Request) -> web.Response:
        index = min(self.seen, len(self.statuses) - 1)
        self.seen += 1
        status = self.statuses[index]
        if self.hold_s:
            await asyncio.sleep(self.hold_s)
        return web.Response(status=status, body=b"ok")

    async def start(self) -> tuple[web.AppRunner, str]:
        app = web.Application()
        app.router.add_route("GET", "/{tail:.*}", self.handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        return runner, f"127.0.0.1:{port}"


def _config(host: str, n: int, *, threads: int = 6, timeout: int = 2) -> IntruderConfig:
    return IntruderConfig(
        template=TEMPLATE.replace("127.0.0.1", host),
        attack_type=AttackType.SNIPER,
        payload_sets=[[f"p{i}" for i in range(n)]],
        threads=threads,
        delay_ms=0,
        timeout=timeout,
        adaptive=True,
    )


async def _run(config: IntruderConfig) -> tuple[list, list]:
    attack = IntruderAttack(config)
    results: list = []
    decisions: list = []
    await attack.run(results.append, lambda done, total: None, decisions.append)
    return results, decisions


@pytest.mark.asyncio
async def test_throttled_server_lowers_the_limit_and_is_journaled() -> None:
    server = _Server([429, 429, 429, 200])
    runner, host = await server.start()
    try:
        results, decisions = await _run(_config(host, 8))
    finally:
        await runner.cleanup()

    assert len(results) == 8, "429 не должен обрывать атаку"
    assert decisions, "серия 429 обязана дать решение"
    throttled = next(decision for decision in decisions if "429" in decision.reason)
    assert throttled.threads < 6
    assert throttled.delay_ms > 0
    assert server.seen >= 8


@pytest.mark.asyncio
async def test_a_refused_target_stops_the_attack_with_the_reason() -> None:
    # Port 1 is closed on any normal machine: every request is a network error.
    results, decisions = await _run(_config("127.0.0.1:1", 10, threads=1))

    assert decisions and decisions[-1].stop, "100 % сетевых ошибок должны остановить атаку"
    assert "ошибк" in decisions[-1].stop_reason.lower()
    assert len(results) == 1, "после остановки новые запросы не отправляются"


@pytest.mark.asyncio
async def test_a_healthy_server_is_not_throttled() -> None:
    server = _Server([200])
    runner, host = await server.start()
    try:
        results, decisions = await _run(_config(host, 6))
    finally:
        await runner.cleanup()

    assert len(results) == 6
    assert decisions == [], "здоровый сервер не повод менять лимиты"
