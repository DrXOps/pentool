"""Adaptive Intruder transport: the controller wired into IntruderAttack (PRO).

The controller is tested on its own; here the whole run is exercised with an injected client,
so no network is involved: a burst of 429s must lower parallelism inside the user's ceiling, a
`Retry-After` must become a shared pause, and a quarter of network errors must stop the attack
with a reason — while a fixed (non-adaptive) run keeps its old behaviour exactly.
"""

from __future__ import annotations

from pentool.modules.intruder import AttackType, IntruderAttack, IntruderConfig

TEMPLATE = "GET /§F§ HTTP/1.1\r\nHost: example.com\r\n\r\n"


class _Resp:
    def __init__(self, status: int = 200, headers: dict | None = None, body: bytes = b"ok") -> None:
        self.status = status
        self.reason = "OK"
        self.headers = headers or {}
        self.body = body
        self.http_version = "HTTP/1.1"
        # `response_raw_from_parsed` prefers raw bytes when present.
        self._raw_body = None


class _Client:
    """Returns prepared responses in order; an Exception item is raised on that request."""

    def __init__(self, items: list) -> None:
        self.items = list(items)
        self.calls = 0
        self.closed = False

    async def send(self, req):  # noqa: ANN001 - the HTTPClient surface
        item = self.items[min(self.calls, len(self.items) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        self.closed = True


def _config(n: int, *, threads: int = 8, adaptive: bool = True) -> IntruderConfig:
    return IntruderConfig(
        template=TEMPLATE,
        attack_type=AttackType.SNIPER,
        payload_sets=[[f"p{i}" for i in range(n)]],
        threads=threads,
        delay_ms=0,
        timeout=5,
        adaptive=adaptive,
    )


async def _run(attack: IntruderAttack, client: _Client) -> list:
    results: list = []
    decisions: list = []
    await attack.run(
        on_result=results.append,
        on_progress=lambda done, total: None,
        on_limit_change=decisions.append,
    )
    return results, decisions


class TestThrottling:
    async def test_429_burst_lowers_parallelism_and_is_reported(self) -> None:
        config = _config(8, threads=8)
        attack = IntruderAttack(config, http_client=_Client([_Resp(429), _Resp(429), _Resp(429), _Resp(200)]))
        results, decisions = await _run(attack, attack._http_client)  # type: ignore[arg-type]

        assert len(results) == 8, "атака не должна бросать работу из-за 429"
        assert decisions, "серия 429 обязана дать решение"
        throttle = next(d for d in decisions if "429" in d.reason)
        assert throttle.threads < 5, "мультипликативное понижение внутри потолка"
        assert throttle.delay_ms > 0
        assert attack.limit_journal, "решение должно попасть в журнал"
        assert attack.stop_reason == ""


class TestRetryAfter:
    async def test_retry_after_becomes_a_pause_not_a_guess(self) -> None:
        config = _config(3, threads=2)
        client = _Client([_Resp(429, headers={"Retry-After": "7"}), _Resp(200)])
        attack = IntruderAttack(config, http_client=client)
        results, decisions = await _run(attack, client)

        assert len(results) == 3
        pause = next(d for d in decisions if "Retry-After" in d.reason)
        assert pause.pause_s == 7
        assert pause.threads == 2, "Retry-After не трогает лимит — он задаёт паузу"

    async def test_retry_after_is_parsed_from_the_response(self) -> None:
        client = _Client([_Resp(503, headers={"Retry-After": "3"})])
        attack = IntruderAttack(_config(1), http_client=client)
        result = await attack._send_request(1, ["x"], TEMPLATE.replace("§F§", "x"), client)
        assert result.retry_after_s == 3.0

    async def test_http_date_retry_after_is_ignored(self) -> None:
        client = _Client([_Resp(503, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})])
        attack = IntruderAttack(_config(1), http_client=client)
        result = await attack._send_request(1, ["x"], TEMPLATE.replace("§F§", "x"), client)
        assert result.retry_after_s is None, "формат даты не угадывается"


class TestNetworkErrors:
    async def test_quarter_of_errors_stops_the_attack_with_a_reason(self) -> None:
        config = _config(6, threads=1)
        client = _Client([TimeoutError("timeout")])
        attack = IntruderAttack(config, http_client=client)
        results, decisions = await _run(attack, client)

        assert attack.stop_reason, "при 25 % сетевых ошибок атака обязана остановиться с причиной"
        assert any(d.stop for d in decisions)
        assert len(results) == 1, "после остановки запросы больше не отправляются"
        assert client.calls == 1
        assert attack.limit_journal[-1].reason == attack.stop_reason


class TestCeilingAndFixedRuns:
    async def test_growth_never_exceeds_the_users_threads(self) -> None:
        config = _config(40, threads=3)
        client = _Client([_Resp(200)])
        attack = IntruderAttack(config, http_client=client)
        await _run(attack, client)

        assert attack.limits is not None
        assert attack.limits.threads <= 3
        assert attack.limits.hard_cap == 3

    async def test_fixed_run_keeps_the_old_behaviour(self) -> None:
        config = _config(5, adaptive=False)
        client = _Client([_Resp(429)])
        attack = IntruderAttack(config, http_client=client)
        results, decisions = await _run(attack, client)

        assert len(results) == 5
        assert decisions == []
        assert attack.limits is None
        assert attack.limit_journal == []
        assert attack.stop_reason == ""
