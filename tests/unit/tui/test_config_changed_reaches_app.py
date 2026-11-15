"""F-029: сохранение настроек доезжает до живого приложения.

Находка утверждала, что `SettingsScreen` пишет в `get_config()` напрямую и не
публикует изменение, поэтому запущенный `ProxyServer` о новой настройке не
узнаёт. Проверка исполнением показала другое: сохранение идёт через
`cfg.update(**changes)`, а `Config.update` уведомляет наблюдателей — App
постит `ConfigChanged` и применяет `proxy_host`/`proxy_port`, тему и таймер
автосейва. Находка была написана по чтению кода; эти тесты держат контракт,
чтобы он не разъехался снова.

Что осталось за скобками (и почему): `ProxyServer` не перезапускается на
лету — он читает `host`/`port` при старте, а обработчик только присваивает
поля и честно говорит пользователю «restart proxy to apply». Это осознанно,
а не потеря.
"""

from __future__ import annotations

import pytest

from pentool.core.config import get_config
from pentool.tui.app import PentoolApp
from pentool.tui.screens.settings.screen import SettingsScreen


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Не трогать настоящий config.yaml при сохранении."""
    cfg = get_config()
    saved: dict = {}

    def _noop_save(path=None) -> None:
        saved["called"] = True

    monkeypatch.setattr(cfg, "save", _noop_save)
    return cfg, saved


class _FakeProxy:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 8080


class TestSavingSettingsPublishesConfigChanged:
    async def test_a_saved_proxy_port_reaches_the_running_proxy(self, isolated_config) -> None:
        """Смена порта в Settings видна живому ProxyServer, а не только в файле."""
        cfg, _saved = isolated_config
        original_port = cfg.proxy_port

        app = PentoolApp()
        app._skip_project_guard = True
        app._proxy = _FakeProxy()  # type: ignore[assignment]
        try:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                settings = app.query_one(SettingsScreen)

                cfg.proxy_port = 8080  # исходное значение для сравнения
                app._proxy.port = 8080
                await settings._async_save_config({"proxy_port": 9090}, "Proxy settings saved")
                await pilot.pause()
                await pilot.pause()

                assert app._proxy.port == 9090, (
                    "the running proxy never learned about the new port — "
                    "Config.update did not reach App.on_config_changed"
                )
        finally:
            cfg.proxy_port = original_port

    async def test_the_app_handler_is_the_thing_that_applies_it(self, isolated_config) -> None:
        """Прямая проверка контракта обработчика, независимо от источника."""
        cfg, _saved = isolated_config
        original_host = cfg.proxy_host

        app = PentoolApp()
        app._skip_project_guard = True
        app._proxy = _FakeProxy()  # type: ignore[assignment]
        try:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                cfg.update(proxy_host="10.1.2.3", proxy_port=7777)
                await pilot.pause()
                await pilot.pause()

                assert app._proxy.host == "10.1.2.3"
                assert app._proxy.port == 7777
        finally:
            cfg.proxy_host = original_host


class TestConfigChangedCarriesWhatChanged:
    def test_only_changed_fields_are_published(self) -> None:
        """`update()` с прежним значением не должен будить наблюдателей.

        Иначе каждый Save в Settings перерисовывал бы прокси и тему, даже
        когда пользователь ничего не менял.
        """
        cfg = get_config()
        seen: list[dict] = []

        def observer(fields: dict) -> None:
            seen.append(fields)

        cfg.add_observer(observer)
        try:
            current = cfg.proxy_port
            cfg.update(proxy_port=current)
            assert seen == [], f"unchanged value published as a change: {seen!r}"
            cfg.update(proxy_port=current + 1)
            assert seen == [{"proxy_port": current + 1}]
        finally:
            # Наблюдатели — список обычных функций (Config._observers): снять
            # его надо явно, иначе он переживёт тест и соберёт чужие события.
            cfg._observers.remove(observer)
