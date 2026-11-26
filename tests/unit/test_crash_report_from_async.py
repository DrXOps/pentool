"""Crash reports are sent even when the caller already runs an event loop.

The old sync wrapper built a new loop and called `run_until_complete(send_crash_async(...))`.
Inside async context the coroutine object was created and then the call raised
"Cannot run the event loop while another loop is running" — the handler swallowed it, so the
report was lost and an un-awaited coroutine stayed behind (the warning that poisoned later
tests). The helper now runs the coroutine in its own thread with its own loop.
"""

from __future__ import annotations

import asyncio

import pytest

from pentool.core import crash_reporter


@pytest.mark.asyncio
async def test_send_crash_works_from_inside_a_running_loop(monkeypatch) -> None:
    sent: list[tuple] = []

    async def fake_send(exc, endpoint=None, source="cli"):
        sent.append((type(exc).__name__, source))

    monkeypatch.setattr(crash_reporter, "send_crash_async", fake_send)
    monkeypatch.setattr(crash_reporter, "_save_local_crash", lambda exc, tb: None)

    crash_reporter.send_crash(ValueError("boom"), source="tui")

    # The report is sent from the helper thread; give it a moment to finish.
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.05)

    assert sent == [("ValueError", "tui")], "краш-репорт не ушёл и не оставил висящую корутину"


def test_send_crash_from_sync_context(monkeypatch) -> None:
    sent: list[str] = []

    async def fake_send(exc, endpoint=None, source="cli"):
        sent.append(source)

    monkeypatch.setattr(crash_reporter, "send_crash_async", fake_send)
    monkeypatch.setattr(crash_reporter, "_save_local_crash", lambda exc, tb: None)

    crash_reporter.send_crash(RuntimeError("sync"), source="cli")

    assert sent == ["cli"]


def test_send_crash_honours_the_opt_out(monkeypatch) -> None:
    called: list[str] = []

    class _Cfg:
        send_crash_reports = False

    monkeypatch.setattr("pentool.core.config.get_config", lambda: _Cfg())
    monkeypatch.setattr(crash_reporter, "send_crash_async", lambda *a, **k: called.append("sent"))

    crash_reporter.send_crash(ValueError("x"))
    assert called == [], "при выключенной отправке ничего не уходит"
