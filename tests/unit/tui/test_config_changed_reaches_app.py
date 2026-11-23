"""F-029: saving settings actually reaches the running application.

The finding claimed that `SettingsScreen` writes to `get_config()` directly and
does not publish the change, so a running `ProxyServer` never learns about the
new setting. Running the check showed otherwise: saving goes through
`cfg.update(**changes)`, and `Config.update` notifies observers — App posts
`ConfigChanged` and applies `proxy_host`/`proxy_port`, the theme and the
autosave timer. The finding was written from reading the code; these tests hold
the contract so it does not drift apart again.

What is left out of scope (and why): `ProxyServer` is not restarted on the fly
— it reads `host`/`port` at startup, while the handler only assigns the fields
and honestly tells the user «restart proxy to apply». That is deliberate, not
a loss.
"""

from __future__ import annotations

import pytest

from pentool.core.config import get_config
from pentool.tui.app import PentoolApp
from pentool.tui.screens.settings.screen import SettingsScreen


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Do not touch the real config.yaml when saving."""
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
        """Changing the port in Settings is visible to the live ProxyServer, not just on disk."""
        cfg, _saved = isolated_config
        original_port = cfg.proxy_port

        app = PentoolApp()
        app._skip_project_guard = True
        app._proxy = _FakeProxy()  # type: ignore[assignment]
        try:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Settings is lazy like every module screen: mount it on demand
                # instead of assuming every screen is already in the DOM.
                settings = await app.ensure_module_screen("settings", SettingsScreen)
                assert settings is not None

                cfg.proxy_port = 8080  # original value to compare against
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
        """Direct check of the handler contract, regardless of the source."""
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
        """`update()` with the previous value must not wake observers up.

        Otherwise every Save in Settings would repaint the proxy and the theme,
        even when the user changed nothing.
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
            # Observers are a plain list of functions (Config._observers): it has
            # to be removed explicitly, otherwise it outlives the test and
            # collects events from other tests.
            cfg._observers.remove(observer)
