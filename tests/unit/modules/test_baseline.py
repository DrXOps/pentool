"""Unit tests for pentool/modules/scanner/baseline.py.

Regression coverage for a bug found while auditing checks alongside the
BaseActiveCheck migration (see
MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md addendum):
BaselineCache.is_identical()/diff_score()/_make_entry() read
`resp.status_code`/`resp.text`, but ParsedResponse only has
`status`/`body` (aiohttp/requests-style names that never existed on this
dataclass). `_make_entry()` is called from `get_or_fetch()` inside a
`try/except: return None` — so every real call to get_or_fetch() silently
returned None, meaning Baseline Cache + Differential Skip (Phase A.4 of
the Scanner modernization plan) never cached anything and diff-skip never
triggered, since its introduction.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.baseline import BaselineCache, BaselineEntry, _make_entry
from pentool.utils.parser import ParsedRequest, ParsedResponse


class _FakeClient:
    def __init__(self, resp: ParsedResponse) -> None:
        self._resp = resp

    async def send(self, request):
        return self._resp


class TestMakeEntry:
    def test_does_not_raise_attributeerror(self):
        """The core regression: this used to blow up on every call."""
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        entry = _make_entry(resp, timing_ms=1.0)
        assert isinstance(entry, BaselineEntry)
        assert entry.status == 200
        assert entry.body_len == len("hello world")

    def test_content_type_extracted(self):
        resp = ParsedResponse(
            status=200, reason="OK",
            headers={"Content-Type": "text/html"}, body="",
        )
        entry = _make_entry(resp, timing_ms=1.0)
        assert entry.content_type == "text/html"


class TestBaselineCacheGetOrFetch:
    @pytest.mark.asyncio
    async def test_returns_real_entry_not_none(self):
        """Before the fix, get_or_fetch() always returned None (the
        AttributeError inside _make_entry() was swallowed by its own
        try/except)."""
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello")
        cache = BaselineCache()
        req = ParsedRequest(method="GET", url="http://test/page", headers={}, body="")
        entry = await cache.get_or_fetch(req, _FakeClient(resp))
        assert entry is not None
        assert entry.status == 200

    @pytest.mark.asyncio
    async def test_cached_on_second_call(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello")
        cache = BaselineCache()
        req = ParsedRequest(method="GET", url="http://test/page", headers={}, body="")
        entry1 = await cache.get_or_fetch(req, _FakeClient(resp))
        entry2 = await cache.get_or_fetch(req, _FakeClient(resp))
        assert entry1 is entry2


class TestIsIdentical:
    def test_identical_response(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        entry = _make_entry(resp, timing_ms=1.0)
        cache = BaselineCache()
        same = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        assert cache.is_identical(entry, same) is True

    def test_different_status_not_identical(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        entry = _make_entry(resp, timing_ms=1.0)
        cache = BaselineCache()
        different = ParsedResponse(status=500, reason="Error", headers={}, body="hello world")
        assert cache.is_identical(entry, different) is False

    def test_different_body_not_identical(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        entry = _make_entry(resp, timing_ms=1.0)
        cache = BaselineCache()
        different = ParsedResponse(
            status=200, reason="OK", headers={},
            body="a completely different response body here",
        )
        assert cache.is_identical(entry, different) is False


class TestDiffScore:
    def test_identical_scores_zero(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        entry = _make_entry(resp, timing_ms=1.0)
        cache = BaselineCache()
        same = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        assert cache.diff_score(entry, same) == 0.0

    def test_different_status_scores_above_zero(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello world")
        entry = _make_entry(resp, timing_ms=1.0)
        cache = BaselineCache()
        different = ParsedResponse(status=500, reason="Error", headers={}, body="hello world")
        assert cache.diff_score(entry, different) > 0.0
