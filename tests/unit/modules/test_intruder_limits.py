"""Adaptive Intruder limits — AIMD controller without a network (PRO).

The controller replaces the Turbo switch: the user's thread count is a ceiling, and the attack
adapts inside it. Signals are fed in by the caller together with the clock, so every rule can be
tested deterministically: throttle bursts, latency spikes, network-error ratios, Retry-After and
the additive growth back to the ceiling.
"""

from __future__ import annotations

from pentool.modules.intruder_limits import AdaptiveLimits

T0 = 1000.0


def _limits(**kwargs) -> AdaptiveLimits:
    params = {"hard_cap": 50, "min_delay_ms": 100}
    params.update(kwargs)
    return AdaptiveLimits(**params)


def _success(limits: AdaptiveLimits, now: float = T0, ms: int = 100, status: int = 200):
    return limits.observe(status=status, elapsed_ms=ms, now=now)


def _throttle(limits: AdaptiveLimits, now: float, status: int = 429):
    return limits.observe(status=status, elapsed_ms=20, now=now)


class TestStart:
    def test_starts_below_the_users_ceiling(self) -> None:
        limits = _limits(hard_cap=50)
        assert limits.threads == 5, "потолок — максимум, а не отправная точка"
        assert limits.threads <= limits.hard_cap

    def test_small_ceiling_is_respected(self) -> None:
        assert _limits(hard_cap=3).threads == 3

    def test_explicit_initial_threads_win_inside_the_ceiling(self) -> None:
        assert _limits(hard_cap=50, initial_threads=2).threads == 2
        assert _limits(hard_cap=50, initial_threads=500).threads == 50


class TestThrottling:
    def test_three_throttles_in_the_window_halve_threads_and_raise_delay(self) -> None:
        limits = _limits(hard_cap=50, min_delay_ms=100)
        assert _throttle(limits, T0) is None
        assert _throttle(limits, T0 + 1) is None
        decision = _throttle(limits, T0 + 2)

        assert decision is not None
        assert decision.threads == 2, "мультипликативное понижение: половина от 5, но не ниже 1"
        assert decision.delay_ms > 100
        assert "429" in decision.reason
        assert decision.stop is False

    def test_throttles_spread_over_the_window_do_not_fire(self) -> None:
        limits = _limits(hard_cap=50)
        _throttle(limits, T0)
        _throttle(limits, T0 + 20)
        assert _throttle(limits, T0 + 40) is None, "три 429 за 40 с — это не серия"

    def test_delay_is_capped(self) -> None:
        limits = _limits(hard_cap=50, min_delay_ms=100, max_delay_ms=400)
        for base in (T0, T0 + 60, T0 + 120, T0 + 180):
            _throttle(limits, base)
            _throttle(limits, base + 1)
            _throttle(limits, base + 2)
        assert limits.delay_ms <= 400


class TestLatency:
    def test_doubled_median_latency_lowers_the_load(self) -> None:
        limits = _limits(hard_cap=50, min_delay_ms=0)
        for i in range(5):
            _success(limits, T0 + i, ms=100)
        before = limits.threads
        decision = None
        for i in range(5, 10):
            decision = _success(limits, T0 + i, ms=300)

        assert decision is not None
        assert decision.threads < before
        assert decision.delay_ms > 0, "к задержке добавляется шаг, а не только снижение"

    def test_stable_latency_does_not_trigger(self) -> None:
        limits = _limits(hard_cap=50)
        for i in range(10):
            assert _success(limits, T0 + i, ms=100) is None


class TestNetworkErrors:
    def test_five_percent_of_errors_pauses_and_lowers(self) -> None:
        limits = _limits(hard_cap=50)
        for i in range(5):
            _success(limits, T0 + i, ms=100)
        decision = limits.observe(status=None, elapsed_ms=None, error="timeout", now=T0 + 5)

        assert decision is not None
        assert decision.pause_s == 2.0
        assert decision.threads < 5
        assert decision.stop is False

    def test_pause_has_a_cooldown(self) -> None:
        limits = _limits(hard_cap=50, error_window=50)
        for i in range(18):
            _success(limits, T0 + i, ms=100)
        first = limits.observe(status=None, elapsed_ms=None, error="reset", now=T0 + 18)  # 5 %
        assert first is not None and first.pause_s
        # Another error immediately after the pause: 10 % is above the pause threshold yet
        # inside the cooldown, and below the stop threshold — so no second pause.
        assert limits.observe(status=None, elapsed_ms=None, error="reset", now=T0 + 19) is None

    def test_quarter_of_errors_stops_the_attack_with_a_reason(self) -> None:
        limits = _limits(hard_cap=50, error_window=8)
        for i in range(3):
            _success(limits, T0 + i, ms=100)
        limits.observe(status=None, elapsed_ms=None, error="timeout", now=T0 + 3)  # 25 %
        decision = limits.observe(status=None, elapsed_ms=None, error="timeout", now=T0 + 4)

        assert decision is not None and decision.stop is True
        assert "ошибк" in decision.stop_reason.lower()
        assert limits.journal and limits.journal[-1].reason == decision.reason


class TestRetryAfter:
    def test_retry_after_is_obeyed_without_guessing(self) -> None:
        limits = _limits(hard_cap=50)
        decision = limits.observe(status=429, elapsed_ms=10, now=T0, retry_after_s=7)

        assert decision is not None
        assert decision.pause_s == 7
        assert decision.threads == 5, "Retry-After не понижает лимит — он задаёт паузу"
        assert "Retry-After" in decision.reason


class TestGrowth:
    def test_stable_success_grows_one_thread_at_a_time_to_the_ceiling(self) -> None:
        limits = _limits(hard_cap=7, min_delay_ms=0)
        seen: list[int] = []
        now = T0
        for i in range(200):
            now += 0.1
            decision = _success(limits, now, ms=100)
            if decision is not None:
                seen.append(decision.threads)
        assert seen, "устойчивая серия должна поднимать лимит"
        assert limits.threads == 7, "рост упирается в потолок пользователя"
        assert seen == sorted(seen), "аддитивное повышение, без скачков"

    def test_growth_relaxes_delay_but_not_below_the_users_minimum(self) -> None:
        limits = _limits(hard_cap=20, min_delay_ms=80, initial_threads=2)
        for base in (T0, T0 + 50):
            _throttle(limits, base)
            _throttle(limits, base + 1)
            _throttle(limits, base + 2)
        raised = limits.delay_ms
        assert raised > 80

        now = T0 + 100
        for _ in range(200):
            now += 0.1
            _success(limits, now, ms=100)
        assert limits.delay_ms >= 80, "пользовательская задержка — минимум, а не ноль"


class TestJournal:
    def test_every_decision_is_recorded_with_time_reason_and_limits(self) -> None:
        limits = _limits(hard_cap=50)
        _throttle(limits, T0)
        _throttle(limits, T0 + 1)
        decision = _throttle(limits, T0 + 2)
        assert decision is not None

        entry = limits.journal[-1]
        assert entry.at == T0 + 2
        assert entry.threads == decision.threads
        assert entry.delay_ms == decision.delay_ms
        assert entry.reason == decision.reason

    def test_no_decision_no_journal(self) -> None:
        limits = _limits(hard_cap=50)
        assert _success(limits, T0) is None
        assert limits.journal == []
