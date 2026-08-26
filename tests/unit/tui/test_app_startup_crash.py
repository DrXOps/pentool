"""Reproduce the ProgrammingError crash on project switch / startup."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_app_switches_db_without_crash():
    from textual.app import App
    from pentool.tui.app import PentoolApp

    app = PentoolApp()
    s = None
    repeater = intruder = None
    try:
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
    finally:
        # Close every persistent aiosqlite connection this test opened.
        # reload_from_project() lazily creates RepeaterAPI/IntruderAPI (and
        # the HttpStorage above creates its own connection); leaving them
        # open leaves non-daemon `_connection_worker_thread` threads behind,
        # which block threading._shutdown — pytest prints its summary and then
        # hangs until the CI 6h job timeout kills it.
        # Close the app-level proxy storage too — PentoolApp.on_mount() opens
        # it eagerly via ProxyService.init_storage(), and Textual's run_test()
        # exit does not tear it down (quit() is what closes it, and that isn't
        # invoked by run_test).
        try:
            ps = app._proxy_service
            if ps is not None and getattr(ps, "_storage", None) is not None:
                await ps._storage.close()
        except Exception:
            pass
        for api in (
            s,
            getattr(repeater, "_repeater_api", None) if repeater else None,
            getattr(intruder, "_api", None) if intruder else None,
        ):
            try:
                if api is not None:
                    await api.close()
            except Exception:
                pass
