"""Adaptive transport limits for Intruder — AIMD, no network, no Textual (PRO).

Turbo was never a different attack: it was a connection-pool profile behind a switch, so the
user got a false choice ("normal/fast") instead of the honest question "how much parallelism
and delay will the target take". This module answers that question while an attack runs:

* the thread count from the UI is a **ceiling**, not a starting point — adaptation only works
  inside it;
* a burst of `429`/`503`/`403` (three within the window) halves the parallelism and raises the
  delay (multiplicative decrease);
* a median response time twice the baseline lowers the load by one step and adds 50 % delay;
* a series of network errors pauses the attack for two seconds; at 25 % it stops it with the
  reason, instead of hammering a dead target;
* `Retry-After` is obeyed instead of guessed;
* a stable run (many 2xx/3xx in a row) adds one thread at a time up to the ceiling and relaxes
  the delay (additive increase).

The controller is a pure state machine: callers pass the observation and the clock, so the
signals can be tested without a network, and every decision lands in a journal that the attack
report can show.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import median

THROTTLE_STATUSES = (429, 503, 403)


@dataclass(frozen=True)
class LimitDecision:
    """One adaptation step: the new limits and why they changed."""

    threads: int
    delay_ms: int
    reason: str
    pause_s: float = 0.0
    stop: bool = False
    stop_reason: str = ""


@dataclass(frozen=True)
class LimitRecord:
    """Journal entry — what the limit became, when, and on which signal."""

    at: float
    threads: int
    delay_ms: int
    reason: str


@dataclass
class AdaptiveLimits:
    """AIMD controller: additive increase, multiplicative decrease, inside a hard ceiling."""

    hard_cap: int
    min_threads: int = 1
    min_delay_ms: int = 0
    max_delay_ms: int = 5000
    initial_threads: int | None = None
    throttle_window_s: float = 10.0
    error_window: int = 50
    grow_after: int = 20
    #: How long the "network errors" pause is held back before it can fire again, seconds.
    pause_cooldown_s: float = 10.0

    _threads: int = field(init=False)
    _delay: int = field(init=False)
    _throttle_times: deque[float] = field(init=False, default_factory=deque)
    _latencies: deque[int] = field(init=False, default_factory=deque)
    _outcomes: deque[bool] = field(init=False, default_factory=deque)
    _ok_streak: int = field(init=False, default=0)
    _baseline_ms: float | None = field(init=False, default=None)
    _last_pause_at: float = field(init=False, default=float("-inf"))
    _journal: list[LimitRecord] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.hard_cap = max(1, int(self.hard_cap))
        self.min_threads = max(1, min(int(self.min_threads), self.hard_cap))
        self.min_delay_ms = max(0, int(self.min_delay_ms))
        self.max_delay_ms = max(self.min_delay_ms, int(self.max_delay_ms))
        start = self.initial_threads if self.initial_threads is not None else min(5, self.hard_cap)
        self._threads = max(self.min_threads, min(self.hard_cap, int(start)))
        self._delay = self.min_delay_ms

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def threads(self) -> int:
        return self._threads

    @property
    def delay_ms(self) -> int:
        return self._delay

    @property
    def journal(self) -> list[LimitRecord]:
        return list(self._journal)

    # ── Observations ──────────────────────────────────────────────────────────

    def observe(
        self,
        *,
        status: int | None,
        elapsed_ms: int | None,
        now: float,
        error: str | None = None,
        retry_after_s: float | None = None,
    ) -> LimitDecision | None:
        """Feed one request outcome; returns a decision when the limits must change.

        `now` is supplied by the caller (monotonic seconds) so the controller stays pure and
        testable. A `None` decision means "keep going as is".
        """
        if retry_after_s is not None and retry_after_s > 0:
            pause = min(float(retry_after_s), 60.0)
            return self._decide(now=now, reason=f"Retry-After {pause:.0f}s", pause_s=pause)

        if error:
            return self._on_error(error, now)

        if status in THROTTLE_STATUSES:
            return self._on_throttle(status, now)

        return self._on_success(status, elapsed_ms, now)

    def _on_error(self, error: str, now: float) -> LimitDecision | None:
        self._record_outcome(False)
        self._ok_streak = 0
        total = len(self._outcomes)
        failures = sum(1 for ok in self._outcomes if not ok)
        ratio = failures / total if total else 0.0
        if ratio >= 0.25:
            reason = f"сетевые ошибки {ratio:.0%} — атака остановлена"
            return self._decide(now=now, reason=reason, stop=True, stop_reason=reason)
        if ratio >= 0.05 and (now - self._last_pause_at) >= self.pause_cooldown_s:
            self._last_pause_at = now
            self._decrease()
            return self._decide(now=now, reason=f"сетевые ошибки {ratio:.0%}", pause_s=2.0)
        return None

    def _on_throttle(self, status: int, now: float) -> LimitDecision | None:
        self._record_outcome(True)
        self._ok_streak = 0
        self._throttle_times.append(now)
        while self._throttle_times and now - self._throttle_times[0] > self.throttle_window_s:
            self._throttle_times.popleft()
        if len(self._throttle_times) < 3:
            return None
        self._throttle_times.clear()
        self._decrease()
        return self._decide(now=now, reason=f"{status} ×3 за {self.throttle_window_s:.0f} с")

    def _on_success(self, status: int | None, elapsed_ms: int | None, now: float) -> LimitDecision | None:
        self._record_outcome(True)
        self._ok_streak += 1
        if elapsed_ms and elapsed_ms > 0:
            self._latencies.append(int(elapsed_ms))
            if self._baseline_ms is None and len(self._latencies) >= 5:
                self._baseline_ms = median(list(self._latencies)[:5])
            if self._baseline_ms and len(self._latencies) >= 10:
                recent = median(list(self._latencies)[-5:])
                if recent > 2 * self._baseline_ms:
                    self._latencies.clear()
                    self._decrease()
                    return self._decide(now=now, reason=f"задержка ×{recent / self._baseline_ms:.1f}")
        if self._ok_streak >= self.grow_after and self._threads < self.hard_cap:
            self._ok_streak = 0
            self._threads = min(self.hard_cap, self._threads + 1)
            if self._delay > 0:
                self._delay = max(self.min_delay_ms, int(self._delay * 0.9))
            return self._decide(now=now, reason=f"{self.grow_after} успешных подряд")
        return None

    # ── Internals ─────────────────────────────────────────────────────────────

    def _record_outcome(self, ok: bool) -> None:
        """Keep the rolling window of the last `error_window` outcomes."""
        self._outcomes.append(ok)
        while len(self._outcomes) > self.error_window:
            self._outcomes.popleft()

    def _decrease(self) -> None:
        self._threads = max(self.min_threads, self._threads // 2)
        raised = max(self._delay * 2, 50)
        self._delay = min(self.max_delay_ms, max(self.min_delay_ms, raised))

    def _decide(
        self,
        *,
        now: float,
        reason: str,
        pause_s: float = 0.0,
        stop: bool = False,
        stop_reason: str = "",
    ) -> LimitDecision:
        self._journal.append(LimitRecord(now, self._threads, self._delay, reason))
        return LimitDecision(
            threads=self._threads,
            delay_ms=self._delay,
            reason=reason,
            pause_s=pause_s,
            stop=stop,
            stop_reason=stop_reason,
        )
