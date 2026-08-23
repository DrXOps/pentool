"""Reproduce the ProgrammingError crash on project switch / startup."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_app_switches_db_without_crash():
    from textual.app import App
    from pentool.tui.app import PentoolApp

    app = PentoolApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await asyncio.sleep(1.0)
        # Simulate project switch: reload_from_project on all screens
        from pentool.tui.screens.repeater.screen import RepeaterScreen
        from pentool.tui.screens.intruder.screen import IntruderScreen
        from pentool.tui.screens.proxy.screen import ProxyScreen

        repeater = app.query_one(RepeaterScreen)
        intruder = app.query_one(IntruderScreen)
        # Trigger switching to a project db (whatever exists)
        import tempfile, os
        db_path = tempfile.mktemp(suffix=".db")
        # Create a db file
        from pentool.storage.http_storage import HttpStorage
        s = HttpStorage(db_path=db_path)
        # triggers init
        await s.init() if hasattr(s, "init") else None

        # Now switch screens
        try:
            await repeater.reload_from_project(db_path)
        except Exception as exc:
            pytest.fail(f"Repeater reload_from_project crashed: {exc}")
        try:
            await intruder.reload_from_project(db_path)
        except Exception as exc:
            pytest.fail(f"Intruder reload_from_project crashed: {exc}")
