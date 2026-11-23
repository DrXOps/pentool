"""E2E conftest — isolated Config + patching of slow IO operations."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pentool.core.config import Config, set_config


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end TUI tests via Textual Pilot")


@pytest.fixture(autouse=True)
def e2e_config(tmp_path):
    """Isolated Config: no recent_projects, no update check."""
    cfg = Config(
        db_path=str(tmp_path / "e2e.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19099,
        check_updates=False,
        recent_projects=[],
    )
    set_config(cfg)
    return cfg


@pytest.fixture(autouse=True)
def patch_slow_io():
    """Patch slow IO operations and daemon blockers.

    - load_or_create_ca       : RSA keygen 0.5–2 sec → return a fake tuple
    - check_update_async      : HTTP + sleep(3) → instant result
    - _setup_signal_handlers  : registers SIGTERM → calls sys.exit on pytest teardown
    - ProxyService.init_storage: creates an aiosqlite non-daemon thread → blocks exit
    - BaseSqliteStorage.ensure_open: the same for IntruderStorage (and for any
      other BaseSqliteStorage subclass with lazy connect) — IntruderScreen now
      keeps one persistent aiosqlite connection for the whole app lifecycle
      (see IntruderScreen._get_api()/reload_from_project(), the fix for the crash
      caused by open/close-on-every-result), but e2e tests do not go through
      action_quit()/close(), so the thread would likewise hang on exit.
    """
    from pentool.core.updater import UpdateInfo

    fake_ca_result = ("/tmp/fake_ca.crt", "/tmp/fake_ca.key")

    async def _instant_update_check(*args, **kwargs):
        return UpdateInfo(has_update=False, latest_version="0.0.0", url="")

    async def _noop_init_storage(self):
        """Mock init_storage — does not create an aiosqlite thread."""
        self._storage_ready = False  # storage disabled in E2E tests

    async def _noop_ensure_open(self):
        """Mock BaseSqliteStorage.ensure_open — does not create an aiosqlite thread."""
        return False

    def _noop_signals(self):
        """Do not register SIGTERM/SIGINT — otherwise pytest gets a signal on exit."""
        pass

    with (
        patch("pentool.utils.cert.load_or_create_ca", return_value=fake_ca_result),
        patch("pentool.core.updater.check_update_async", side_effect=_instant_update_check),
        patch("pentool.tui.app.PentoolApp._setup_signal_handlers", _noop_signals),
        patch("pentool.services.proxy_service.ProxyService.init_storage", _noop_init_storage),
        patch("pentool.storage.base_sqlite_storage.BaseSqliteStorage.ensure_open", _noop_ensure_open),
    ):
        yield
