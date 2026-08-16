"""Unit tests for ScannerAPI tab persistence and findings scoping.

Covers the fix for two related bugs:
1. Scanner tabs were persisted by upserting on tab_name ("Scan 1",
   "Scan 2", ...) which resets every app restart (_tab_counter starts
   at 0) — a restarted app's new "Scan 1" tab could silently adopt a
   DIFFERENT tab's saved row from a previous session if tab-creation
   order happened to line up. Fixed by upserting on a stable tab_uid
   instead.
2. get_findings() had no scoping at all — every tab showed every
   finding ever saved to the project DB. Fixed by
   ScanEngine.get_findings(tab_uid=...) filtering to that tab's own
   findings (plus legacy/unscoped rows, for backward compatibility).
"""
from __future__ import annotations

import pytest

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

from pentool.api.scanner_api import ScannerAPI
from pentool.core.db_schema import init_db
from pentool.modules.scanner.base import Finding


@pytest.fixture
async def api(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    a = ScannerAPI(db_path=db_path)
    yield a
    # ScannerAPI's components (ScanEngine, ScannerTabRepository) now hold a
    # persistent aiosqlite connection each (see BaseSqliteStorage) instead
    # of opening one per call — must be closed explicitly or its background
    # thread leaks past the test (PytestUnhandledThreadExceptionWarning on
    # teardown), same as IntruderStorage's fixture (see
    # tests/unit/api/test_intruder_storage.py).
    await a.close()


class TestSaveTabByUid:
    @pytest.mark.asyncio
    async def test_save_new_tab_creates_row(self, api):
        await api.save_tab("uid-1", "Scan 1", "http://a.com")
        tabs = await api.get_tabs()
        assert len(tabs) == 1
        assert tabs[0]["tab_uid"] == "uid-1"
        assert tabs[0]["tab_name"] == "Scan 1"
        assert tabs[0]["target_url"] == "http://a.com"

    @pytest.mark.asyncio
    async def test_resave_same_uid_updates_in_place(self, api):
        """Re-saving with the same tab_uid must UPDATE, not INSERT a
        duplicate — this is what makes upsert-by-uid safe across restarts."""
        await api.save_tab("uid-1", "Scan 1", "http://a.com")
        await api.save_tab("uid-1", "Scan 1 renamed", "http://a.com/updated")

        tabs = await api.get_tabs()
        assert len(tabs) == 1
        assert tabs[0]["tab_name"] == "Scan 1 renamed"
        assert tabs[0]["target_url"] == "http://a.com/updated"

    @pytest.mark.asyncio
    async def test_two_tabs_with_different_uids_stay_separate(self, api):
        await api.save_tab("uid-1", "Scan 1", "http://a.com")
        await api.save_tab("uid-2", "Scan 2", "http://b.com")

        tabs = await api.get_tabs()
        assert len(tabs) == 2
        uids = {t["tab_uid"] for t in tabs}
        assert uids == {"uid-1", "uid-2"}

    @pytest.mark.asyncio
    async def test_same_tab_name_different_uid_does_not_merge(self, api):
        """Regression test for the actual bug: two DIFFERENT tabs that
        happen to share the same cosmetic name ("Scan 1" after an app
        restart resets _tab_counter) must NOT be treated as the same
        saved row — only tab_uid identifies a tab."""
        await api.save_tab("uid-from-session-A", "Scan 1", "http://session-a.com")
        await api.save_tab("uid-from-session-B", "Scan 1", "http://session-b.com")

        tabs = await api.get_tabs()
        assert len(tabs) == 2
        urls = {t["target_url"] for t in tabs}
        assert urls == {"http://session-a.com", "http://session-b.com"}

    @pytest.mark.asyncio
    async def test_save_tab_without_uid_is_noop(self, api):
        await api.save_tab("", "Scan 1", "http://a.com")
        tabs = await api.get_tabs()
        assert tabs == []

    @pytest.mark.asyncio
    async def test_delete_tab_by_uid(self, api):
        await api.save_tab("uid-1", "Scan 1", "http://a.com")
        await api.save_tab("uid-2", "Scan 2", "http://b.com")

        await api.delete_tab("uid-1")

        tabs = await api.get_tabs()
        assert len(tabs) == 1
        assert tabs[0]["tab_uid"] == "uid-2"


class TestFindingsScopedToTab:
    @pytest.mark.asyncio
    async def test_findings_scoped_to_own_tab(self, api):
        engine = api._get_engine()
        f1 = Finding(type="xss", name="XSS in tab1", url="http://a.com/x",
                     severity="high", scan_tab_uid="tab-1")
        f2 = Finding(type="sqli", name="SQLi in tab2", url="http://b.com/y",
                     severity="critical", scan_tab_uid="tab-2")
        await engine.save_findings([f1, f2])

        tab1_findings = await api.get_findings(tab_uid="tab-1")
        tab2_findings = await api.get_findings(tab_uid="tab-2")

        assert len(tab1_findings) == 1
        assert tab1_findings[0].type == "xss"
        assert len(tab2_findings) == 1
        assert tab2_findings[0].type == "sqli"

    @pytest.mark.asyncio
    async def test_no_tab_uid_returns_all_findings(self, api):
        """Passing tab_uid=None (reports/exports) bypasses scoping —
        matches the pre-fix behavior for callers that want everything."""
        engine = api._get_engine()
        f1 = Finding(type="xss", name="A", url="http://a.com/x",
                     severity="high", scan_tab_uid="tab-1")
        f2 = Finding(type="sqli", name="B", url="http://b.com/y",
                     severity="critical", scan_tab_uid="tab-2")
        await engine.save_findings([f1, f2])

        all_findings = await api.get_findings()
        assert len(all_findings) == 2

    @pytest.mark.asyncio
    async def test_unscoped_legacy_findings_visible_to_every_tab(self, api):
        """Findings saved before this fix (scan_tab_uid empty/NULL) must
        remain visible everywhere — backward compatibility for existing
        project databases."""
        engine = api._get_engine()
        legacy = Finding(type="xss", name="Legacy finding", url="http://old.com/x",
                          severity="high")  # scan_tab_uid defaults to ""
        await engine.save_findings([legacy])

        tab1_findings = await api.get_findings(tab_uid="brand-new-tab-A")
        tab2_findings = await api.get_findings(tab_uid="brand-new-tab-B")

        assert len(tab1_findings) == 1
        assert len(tab2_findings) == 1

    @pytest.mark.asyncio
    async def test_unscoped_findings_do_not_leak_other_tabs_scoped_data(self, api):
        engine = api._get_engine()
        legacy = Finding(type="xss", name="Legacy", url="http://old.com/x", severity="high")
        scoped = Finding(type="sqli", name="Scoped to tab-2", url="http://b.com/y",
                          severity="critical", scan_tab_uid="tab-2")
        await engine.save_findings([legacy, scoped])

        tab1_findings = await api.get_findings(tab_uid="tab-1")
        types = {f.type for f in tab1_findings}

        assert "xss" in types    # legacy/unscoped — visible everywhere
        assert "sqli" not in types  # scoped to a different tab — not visible


class TestPersistentConnection:
    """Regression coverage for the connection-consolidation fix applied to
    ScannerTabRepository, mirroring IntruderStorage's fix (see
    tests/unit/api/test_intruder_storage.py::TestPersistentConnection)
    and ScanEngine's (see
    tests/unit/modules/test_scan_engine_resume.py::TestPersistentConnection).

    ScannerTabRepository used to open a brand-new aiosqlite connection (via
    core.db_schema.get_db()) on every single save_tab()/get_tabs()/
    delete_tab() call — now inherits BaseSqliteStorage: one connection,
    opened lazily on first use via ensure_open(), reused for the
    repository's lifetime.
    """

    @pytest.mark.asyncio
    async def test_repeated_save_tab_reuses_same_connection(self, api):
        await api.save_tab("uid-1", "Scan 1", "http://a.com")
        conn_after_first = api._tabs._db
        assert conn_after_first is not None

        for i in range(2, 12):
            await api.save_tab(f"uid-{i}", f"Scan {i}", f"http://{i}.com")
            assert api._tabs._db is conn_after_first

        tabs = await api.get_tabs()
        assert len(tabs) == 11
        assert api._tabs._db is conn_after_first

    @pytest.mark.asyncio
    async def test_save_tab_without_uid_does_not_open_connection(self, tmp_path):
        """ensure_open()'s no-op contract must still hold for the no-op
        (empty tab_uid) path — mirrors the falsy-db_path no-op contract."""
        from pentool.core.db_schema import init_db
        db_path = str(tmp_path / "test2.db")
        await init_db(db_path)
        a = ScannerAPI(db_path=db_path)
        try:
            await a.save_tab("", "Scan 1", "http://a.com")
            assert a._tabs._db is None
        finally:
            await a.close()
