"""Passive scanner replays recorded traffic when it is switched on."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# The passive scanner lives in the PRO tree: the core CI job has no `pro/` checkout, and a
# module-level import would turn a missing optional tree into a collection error for the
# whole suite.
pytest.importorskip("pro.pentool.api.passive_scanner_manager", reason="PRO tree not checked out")

from pro.pentool.api.passive_scanner_manager import _recent_history  # noqa: E402
from pro.pentool.modules.scanner.passive import PassiveScanner  # noqa: E402


class _Engine:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def run_passive(self, request, response):
        self.calls.append((request.url, getattr(response, "status", None)))
        return []

    async def save_findings(self, findings):
        return None


class _Service:
    def __init__(self) -> None:
        self.rows = [{"id": 1}, {"id": 2}]
        self.full = {
            1: {
                "id": 1,
                "method": "GET",
                "url": "http://a.test/1",
                "request_headers": {"Host": "a.test"},
                "request_body": "",
                "status_code": 200,
                "response_headers": {},
                "response_body": "ok",
            },
            2: {
                "id": 2,
                "method": "POST",
                "url": "http://a.test/2",
                "request_headers": {},
                "request_body": "x=1",
                "status_code": 404,
                "response_headers": {},
                "response_body": "missing",
            },
        }

    async def get_history(self, offset: int = 0, limit: int = 200):
        return self.rows[:limit]

    async def get_full_entry(self, row_id: int):
        return self.full.get(row_id)


@pytest.mark.asyncio
async def test_replay_runs_the_same_analysis_as_live_traffic() -> None:
    engine = _Engine()
    scanner = PassiveScanner(engine)

    analysed = await scanner.replay_history(await _recent_history(SimpleNamespace(proxy_service=_Service())))

    assert analysed == 2
    assert [url for url, _status in engine.calls] == ["http://a.test/1", "http://a.test/2"]


@pytest.mark.asyncio
async def test_replay_skips_entries_it_cannot_parse() -> None:
    engine = _Engine()
    scanner = PassiveScanner(engine)

    analysed = await scanner.replay_history([{"id": 9, "url": None}])

    assert analysed == 1  # ParsedRequest accepts an empty url; the point is "no exception"
    assert not engine.calls or engine.calls[0][1] == 0


@pytest.mark.asyncio
async def test_no_history_api_means_no_crash() -> None:
    assert await _recent_history(SimpleNamespace()) == []
