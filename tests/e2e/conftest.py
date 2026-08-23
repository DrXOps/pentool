"""E2E conftest — изолированный Config + патч медленных IO-операций."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from pentool.core.config import Config, set_config


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end TUI tests via Textual Pilot")


@pytest.fixture(autouse=True)
def e2e_config(tmp_path):
    """Изолированный Config: нет recent_projects, нет update-check."""
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
    """Патчим медленные IO-операции и daemon-блокеры.

    - load_or_create_ca       : RSA keygen 0.5–2 сек → возвращаем fake tuple
    - check_update_async      : HTTP + sleep(3) → мгновенный результат
    - _setup_signal_handlers  : регистрирует SIGTERM → вызывает sys.exit при teardown pytest
    - ProxyService.init_storage: создаёт aiosqlite non-daemon поток → блокирует exit
    - BaseSqliteStorage.ensure_open: то же самое для IntruderStorage (и любого
      другого BaseSqliteStorage-потомка с ленивым connect) — IntruderScreen
      теперь держит один persistent aiosqlite-коннекшн на весь app lifecycle
      (см. IntruderScreen._get_api()/reload_from_project(), фикс краша от
      open/close-на-каждый-результат), но e2e-тесты не проходят через
      action_quit()/close(), поэтому поток аналогично зависал бы на выходе.
    """
    from pentool.core.updater import UpdateInfo

    fake_ca_result = ("/tmp/fake_ca.crt", "/tmp/fake_ca.key")

    async def _instant_update_check(*args, **kwargs):
        return UpdateInfo(has_update=False, latest_version="0.0.0", url="")

    async def _noop_init_storage(self):
        """Мок init_storage — не создаёт aiosqlite поток."""
        self._storage_ready = False  # storage disabled in E2E tests

    async def _noop_ensure_open(self):
        """Мок BaseSqliteStorage.ensure_open — не создаёт aiosqlite поток."""
        return False

    def _noop_signals(self):
        """Не регистрировать SIGTERM/SIGINT — иначе pytest получает сигнал при выходе."""
        pass

    with (
        patch("pentool.utils.cert.load_or_create_ca", return_value=fake_ca_result),
        patch("pentool.core.updater.check_update_async", side_effect=_instant_update_check),
        patch("pentool.tui.app.PentoolApp._setup_signal_handlers", _noop_signals),
        patch("pentool.services.proxy_service.ProxyService.init_storage", _noop_init_storage),
        patch("pentool.storage.base_sqlite_storage.BaseSqliteStorage.ensure_open", _noop_ensure_open),
    ):
        yield
