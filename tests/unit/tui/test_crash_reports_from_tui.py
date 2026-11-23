"""Guards: a fatal TUI exception must reach the crash endpoint.

Until 2026-11-23 `PentoolApp._handle_exception` only wrote to the local journal
(plus an all-thread dump): a TUI crash never reached the server, so nobody learned
about it. The report is now posted from a worker thread with a bounded wait — the
app is dying, but the report must not be lost, and a slow network must not keep the
terminal hostage.
"""

from __future__ import annotations

import inspect
import time
from unittest.mock import MagicMock, patch

from pentool.tui.app import PentoolApp


def _app() -> PentoolApp:
    """An app instance without composing: the report path does not need widgets."""
    app = PentoolApp.__new__(PentoolApp)
    app._fatal_crash_reported = False
    return app


def test_fatal_exception_is_sent_once_per_run() -> None:
    app = _app()
    with patch("pentool.core.crash_reporter.send_crash") as send:
        app._report_fatal_crash(ValueError("boom"))
        app._report_fatal_crash(ValueError("boom again"))

    assert send.call_count == 1, "a crash loop must not flood the server with reports"


def test_report_is_marked_as_tui_source() -> None:
    app = _app()
    with patch("pentool.core.crash_reporter.send_crash") as send:
        app._report_fatal_crash(RuntimeError("boom"))

    assert send.call_args.kwargs.get("source") == "tui", "the server cannot tell TUI crashes from CLI ones"


def test_reporter_failure_does_not_escape() -> None:
    """The reporter is best-effort: a broken send must not mask the original crash."""
    app = _app()
    with patch("pentool.core.crash_reporter.send_crash", side_effect=RuntimeError("network down")):
        app._report_fatal_crash(ValueError("boom"))  # must not raise

    assert app._fatal_crash_reported is True


def test_handle_exception_reports_before_textual_takes_over() -> None:
    """`_handle_exception` must call the reporter (order matters: app is torn down next)."""
    source = inspect.getsource(PentoolApp._handle_exception)
    report_at = source.find("self._report_fatal_crash(error)")
    super_at = source.find("super()._handle_exception(error)")

    assert report_at != -1, "_handle_exception no longer reports the crash"
    assert super_at != -1
    assert report_at < super_at, "the report must be sent before Textual tears the app down"


def test_handle_exception_invokes_the_report_method() -> None:
    """Actually call it: the parent handler is stubbed so the app survives."""
    from textual.app import App

    app = _app()
    with (
        patch.object(App, "_handle_exception", lambda self, error: None),
        patch.object(PentoolApp, "_report_fatal_crash") as report,
    ):
        app._handle_exception(ValueError("boom"))

    report.assert_called_once()
    assert isinstance(report.call_args.args[0], ValueError)


def test_slow_report_keeps_a_local_dump() -> None:
    """A report that outlives the join window must not lose the traceback."""
    app = _app()
    app._CRASH_REPORT_JOIN_TIMEOUT = 0.05
    with (
        patch("pentool.core.crash_reporter.send_crash", side_effect=lambda *a, **k: time.sleep(0.3)),
        patch("pentool.core.crash_reporter._save_local_crash") as local,
    ):
        app._report_fatal_crash(ValueError("boom"))

    local.assert_called_once()


def test_send_crash_forwards_source_to_payload() -> None:
    """`send_crash(source=...)` must reach the HTTP payload, not be swallowed."""
    import asyncio

    from pentool.core import crash_reporter

    captured: dict[str, object] = {}

    class _Session:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def post(self, endpoint, json=None, ssl=None):  # noqa: A002 - aiohttp API
            captured.update(json or {})
            return MagicMock()

    class _Aiohttp:
        ClientTimeout = MagicMock(return_value=None)

        @staticmethod
        def ClientSession(*args, **kwargs):  # noqa: N802 - mirrors aiohttp
            return _Session()

    with patch.dict("sys.modules", {"aiohttp": _Aiohttp}):
        asyncio.run(crash_reporter.send_crash_async(ValueError("boom"), source="tui"))

    assert captured.get("source") == "tui"
    assert captured.get("exception") == "ValueError"
    assert "boom" in str(captured.get("traceback"))
