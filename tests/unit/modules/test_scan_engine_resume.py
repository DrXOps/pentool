"""Unit tests for ScanEngine — Resume dedup, progress estimate, dispatch.

Covers three fixes made after the scan_pipeline dispatch fix:
1. Resume actually skips already-completed (url, check, point) tasks
   instead of re-running the whole scan from scratch.
2. on_total_estimate() gives the caller a rough total-request estimate
   before work starts (drives the TUI progress bar).
3. Dispatch correctly routes uses_scan_pipeline checks (e.g. SQLi/XSS)
   to their scan() method even when a specific injection point is
   passed, instead of the analyze()-only branch.
"""
from __future__ import annotations

import pytest

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.engine import ScanEngine
from pentool.modules.scanner.checks.sqli import SQLiCheck
from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest.fixture(autouse=True)
def _pro_license():
    """Force a valid PRO session license for every test in this file.

    BaseCheck.is_available() gates every check behind
    get_session_license().has_feature("scanner_pro") — the session license
    is a module-level cache (pentool.core.license._session_license) shared
    across the whole test process. Other test files (e.g. test_license.py)
    legitimately leave it set to a "free" LicenseInfo after they run, which
    silently made active_checks empty here (0 requests, 0 scan() calls)
    whenever this file ran after them in a full-suite run — despite this
    file passing in isolation. Pin it explicitly instead of relying on
    whatever the previous test file left behind.
    """
    from pentool.core.license import LicenseInfo, refresh_session_license
    pro = LicenseInfo(valid=True, plan="pro", features=["scanner_pro"])
    refresh_session_license(pro)
    yield
    refresh_session_license(None)


class FakeHTTPClient:
    """Minimal fake — instantly answers every send()/get()/post()."""

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, req):
        self.calls += 1
        return ParsedResponse(status=200, reason="OK", headers={}, body="<html>ok</html>")

    async def get(self, url, headers=None):
        self.calls += 1
        return ParsedResponse(status=200, reason="OK", headers={}, body="<html>ok</html>")

    async def post(self, url, body="", headers=None):
        self.calls += 1
        return ParsedResponse(status=200, reason="OK", headers={}, body="<html>ok</html>")


def _make_engine(client: FakeHTTPClient, concurrency: int = 5) -> ScanEngine:
    engine = ScanEngine(db_path=":memory:", concurrency=concurrency, http_client=client)
    engine.register_check(SQLiCheck())
    return engine


def _reqs(n: int) -> list[ParsedRequest]:
    return [
        ParsedRequest(method="GET", url=f"http://example.com/page{i}?id=1",
                      headers={}, body="")
        for i in range(n)
    ]


class TestResumeDedup:
    """ScanEngine._completed_task_keys — persistent dedup across Stop/Resume."""

    @pytest.mark.asyncio
    async def test_resume_skips_already_completed_tasks(self):
        client = FakeHTTPClient()
        engine = _make_engine(client)
        reqs = _reqs(3)

        await engine.run_active_on_requests(seed_requests=reqs, resume=False)
        first_run_calls = client.calls
        assert first_run_calls > 0
        assert len(engine._completed_task_keys) > 0

        client.calls = 0
        await engine.run_active_on_requests(seed_requests=reqs, resume=True)
        # Same engine, same requests, same checks — everything already
        # marked as completed, so Resume should make (almost) no calls.
        assert client.calls < first_run_calls
        assert client.calls <= 2  # allow for e.g. one baseline-only probe

    @pytest.mark.asyncio
    async def test_fresh_start_after_resume_redoes_everything(self):
        """A fresh Start (resume=False) must clear resume tracking and
        re-run the full scan — it must NOT silently inherit skipped tasks
        from an unrelated earlier run against the same engine instance."""
        client = FakeHTTPClient()
        engine = _make_engine(client)
        reqs = _reqs(3)

        await engine.run_active_on_requests(seed_requests=reqs, resume=False)
        first_run_calls = client.calls

        client.calls = 0
        await engine.run_active_on_requests(seed_requests=reqs, resume=False)
        assert client.calls == first_run_calls

    @pytest.mark.asyncio
    async def test_reset_resume_state_clears_tracking(self):
        client = FakeHTTPClient()
        engine = _make_engine(client)
        reqs = _reqs(2)

        await engine.run_active_on_requests(seed_requests=reqs, resume=False)
        assert len(engine._completed_task_keys) > 0

        engine.reset_resume_state()
        assert len(engine._completed_task_keys) == 0

    @pytest.mark.asyncio
    async def test_stopped_task_is_not_marked_completed(self):
        """If Stop cuts a task short (pressed mid-scan, not before it),
        that task must be retried on Resume — not skipped as if it had
        finished. Simulates the real sequence: request_stop() is called
        while a task is already in flight (via the on_request callback,
        fired for every real network call the check makes), not before
        run_active_on_requests() even starts (reset_dedup() would just
        clear that flag again at the top of the call)."""
        client = FakeHTTPClient()
        engine = _make_engine(client)
        reqs = _reqs(1)

        def _on_request(url, check_name, point_name):
            engine.request_stop()

        await engine.run_active_on_requests(
            seed_requests=reqs, resume=False, on_request=_on_request,
        )
        # Stop fired on the very first real network call, before any task
        # could run to completion — none should be recorded as done.
        assert len(engine._completed_task_keys) == 0


class TestTotalEstimate:
    """on_total_estimate callback — rough request-count estimate for the
    UI progress bar, computed before active-scan work starts."""

    @pytest.mark.asyncio
    async def test_on_total_estimate_called_once_before_work(self):
        client = FakeHTTPClient()
        engine = _make_engine(client)
        reqs = _reqs(2)

        estimates = []
        await engine.run_active_on_requests(
            seed_requests=reqs, on_total_estimate=estimates.append,
        )
        assert len(estimates) == 1
        assert estimates[0] > 0

    @pytest.mark.asyncio
    async def test_estimate_scales_with_request_count(self):
        client = FakeHTTPClient()
        estimates_small: list[int] = []
        engine_small = _make_engine(client)
        await engine_small.run_active_on_requests(
            seed_requests=_reqs(1), on_total_estimate=estimates_small.append,
        )

        client2 = FakeHTTPClient()
        estimates_large: list[int] = []
        engine_large = _make_engine(client2)
        await engine_large.run_active_on_requests(
            seed_requests=_reqs(5), on_total_estimate=estimates_large.append,
        )

        assert estimates_large[0] > estimates_small[0]

    @pytest.mark.asyncio
    async def test_no_estimate_callback_does_not_raise(self):
        """on_total_estimate is optional — omitting it must not break the scan."""
        client = FakeHTTPClient()
        engine = _make_engine(client)
        findings = await engine.run_active_on_requests(seed_requests=_reqs(1))
        assert isinstance(findings, list)


class TestScanPipelineDispatch:
    """Regression test for the root-cause bug: engine dispatch was keyed
    only on `point is not None`, so uses_scan_pipeline checks (created as
    per-point tasks, same as analyze()-API checks) fell into the
    analyze()-only branch and never called their own multi-phase scan()
    method — silently skipping context-aware logic and instead running a
    flat, context-blind payload list once PER injection point (quadratic
    request blow-up for checks like XSS).
    """

    @pytest.mark.asyncio
    async def test_pipeline_check_scan_called_once_per_point(self):
        client = FakeHTTPClient()
        engine = _make_engine(client)

        scan_calls: list = []
        orig_scan = SQLiCheck.scan

        async def traced_scan(self, request, response, http_client, **kwargs):
            scan_calls.append(kwargs.get("point"))
            return await orig_scan(self, request, response, http_client, **kwargs)

        SQLiCheck.scan = traced_scan
        try:
            req = ParsedRequest(method="GET", url="http://example.com/page?id=1",
                                 headers={"Cookie": "session=abc"}, body="")
            await engine.run_active_on_requests(seed_requests=[req])
        finally:
            SQLiCheck.scan = orig_scan

        # scan() must be called (dispatch reached it), and each call must
        # receive a distinct, non-None point — one call per injection point,
        # not zero calls (dispatch bug) and not N^2 calls (each scan() call
        # re-iterating every point itself).
        assert len(scan_calls) > 0
        assert all(p is not None for p in scan_calls)
        assert len(set((p.kind, p.name) for p in scan_calls)) == len(scan_calls)

    @pytest.mark.asyncio
    async def test_request_volume_scales_linearly_with_endpoint_count(self):
        """Before the fix, request volume for a pipeline check scaled with
        N_points^2 per endpoint (quadratic) because dispatch skipped
        scan() and re-ran a flat payload list once per point. After the
        fix it must scale linearly with the number of endpoints."""
        req_template = "http://example.com/page{i}?id=1&name=test"

        client1 = FakeHTTPClient()
        engine1 = _make_engine(client1)
        await engine1.run_active_on_requests(
            seed_requests=[ParsedRequest(method="GET", url=req_template.format(i=0),
                                          headers={"Cookie": "s=1"}, body="")]
        )
        calls_for_one = client1.calls

        client5 = FakeHTTPClient()
        engine5 = _make_engine(client5)
        await engine5.run_active_on_requests(
            seed_requests=[
                ParsedRequest(method="GET", url=req_template.format(i=i),
                              headers={"Cookie": "s=1"}, body="")
                for i in range(5)
            ]
        )
        calls_for_five = client5.calls

        # Linear: 5x the endpoints -> ~5x the requests (allow slack for
        # baseline/probe overhead), NOT ~25x (quadratic).
        assert calls_for_five <= calls_for_one * 6
        assert calls_for_five >= calls_for_one * 4
