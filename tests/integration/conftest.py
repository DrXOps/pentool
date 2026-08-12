"""Integration conftest — патч медленных IO и daemon-блокеров для TUI-тестов."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from pentool.core.config import Config, set_config


@pytest.fixture(autouse=True)
def integration_config(tmp_path):
    """Изолированный Config без recent_projects и update-check."""
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
    """Патч медленных IO-операций и daemon-блокеров для TUI-тестов.

    Используй этот fixture явно в тестах которые запускают PentoolApp
    через app.run_test() — добавь аргумент patch_tui_io в сигнатуру теста.

    Не применяется autouse=True потому что ломает unit-тесты ProxyService
    которым нужен реальный init_storage.

    - load_or_create_ca      : RSA keygen 0.5–2 сек → fake tuple
    - check_update_async     : HTTP + sleep(3) → мгновенный результат
    - _setup_signal_handlers : не регистрировать SIGTERM/SIGINT
    - ProxyService.init_storage: aiosqlite non-daemon поток → блокирует exit
    - BaseSqliteStorage.ensure_open: то же самое для IntruderRepository —
      IntruderScreen теперь держит один persistent aiosqlite-коннекшн на
      весь app lifecycle (см. IntruderScreen._get_api()), но интеграционные
      TUI-тесты не закрывают его явно — без мока поток зависает между
      тестами так же, как ProxyService's до этого мока.
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
        """Не запускать proxy-поток — он daemon=False и зависает между тестами."""
        pass

    async def _noop_auto_open(self):
        """Не открывать последний проект — нет recent_projects в тестах."""
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
    """Очистка asyncio ресурсов между TUI-тестами."""
    yield
    import asyncio
    import gc
    import threading

    # Закрыть все незавершённые tasks
    try:
        loop = asyncio.get_event_loop()
        if loop and not loop.is_closed():
            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    except RuntimeError:
        pass  # event loop может быть уже закрыт

    # Принудительная сборка мусора для освобождения textual виджетов
    gc.collect()
    gc.collect()

    # Дать время background threads завершиться
    import time
    time.sleep(0.05)
