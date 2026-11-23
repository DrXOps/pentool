"""Integration conftest — patches slow IO and daemon blockers for TUI tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pentool.core.config import Config, set_config


@pytest.fixture(autouse=True)
def integration_config(tmp_path):
    """Isolated Config without recent_projects and update-check."""
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19090,
        check_updates=False,
        recent_projects=[],
    )
    set_config(cfg)
    return cfg


@pytest.fixture
def patch_tui_io():
    """Patches slow IO operations and daemon blockers for TUI tests.

    Use this fixture explicitly in tests that launch PentoolApp
    via app.run_test() — add the patch_tui_io argument to the test signature.

    It is not autouse=True because that breaks ProxyService unit tests
    which need a real init_storage.

    - load_or_create_ca      : RSA keygen 0.5–2 sec → fake tuple
    - check_update_async     : HTTP + sleep(3) → instant result
    - _setup_signal_handlers : do not register SIGTERM/SIGINT
    - ProxyService.init_storage: aiosqlite non-daemon thread → blocks exit
    - BaseSqliteStorage.ensure_open: the same for IntruderStorage —
      IntruderScreen now keeps one persistent aiosqlite connection for
      the whole app lifecycle (see IntruderScreen._get_api()), but integration
      TUI tests do not close it explicitly — without the mock the thread hangs
      between tests just like ProxyService's did before this mock.
    """
    from pentool.core.updater import UpdateInfo

    async def _instant_update_check(*a, **kw):
        return UpdateInfo(has_update=False, latest_version="0.0.0", url="")

    async def _noop_init_storage(self):
        self._storage_ready = False

    async def _noop_ensure_open(self):
        return False

    def _noop_signals(self):
        pass

    def _noop_start_proxy(self):
        """Do not start the proxy thread — it is daemon=False and hangs between tests."""
        pass

    async def _noop_auto_open(self):
        """Do not open the last project — there is no recent_projects in tests."""
        pass

    with (
        patch("pentool.utils.cert.load_or_create_ca", return_value=("/tmp/fake.crt", "/tmp/fake.key")),
        patch("pentool.core.updater.check_update_async", side_effect=_instant_update_check),
        patch("pentool.tui.app.PentoolApp._setup_signal_handlers", _noop_signals),
        patch("pentool.services.proxy_service.ProxyService.init_storage", _noop_init_storage),
        patch("pentool.storage.base_sqlite_storage.BaseSqliteStorage.ensure_open", _noop_ensure_open),
        patch("pentool.tui.app.PentoolApp._start_proxy", _noop_start_proxy),
        patch("pentool.tui.app.PentoolApp._auto_open_last_project", _noop_auto_open),
    ):
        yield


@pytest.fixture
async def cleanup_asyncio():
    """Cleanup of asyncio resources between TUI tests."""
    yield
    import asyncio
    import gc

    # Close all unfinished tasks
    try:
        loop = asyncio.get_event_loop()
        if loop and not loop.is_closed():
            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    except RuntimeError:
        pass  # the event loop may already be closed

    # Force garbage collection to free textual widgets
    gc.collect()
    gc.collect()

    # Give background threads time to finish
    import time

    time.sleep(0.05)
