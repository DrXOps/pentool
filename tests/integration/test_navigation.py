"""Integration-тесты: навигация по модулям (TUI).

Проверяет переключение вкладок, ContentSwitcher, ModuleTabs через Textual Pilot.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from pentool.core.config import Config, set_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    """Изолированная конфигурация для каждого теста."""
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19090,
    )
    set_config(cfg)
    return cfg


@pytest.mark.integration
class TestAppCompose:
    @pytest.mark.asyncio
    async def test_app_mounts_without_error(self) -> None:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # Приложение смонтировалось без исключений

    @pytest.mark.asyncio
    async def test_module_tabs_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.module_tabs import ModuleTabs
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            tabs = app.query_one(ModuleTabs)
            assert tabs is not None

    @pytest.mark.asyncio
    async def test_statusbar_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.statusbar import StatusBar
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            sb = app.query_one(StatusBar)
            assert sb is not None

    @pytest.mark.asyncio
    async def test_menubar_hidden_in_dom(self) -> None:
        """MenuBar убрана из DOM (R-12) — query должен вернуть пустой список."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.menu_bar import MenuBar
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # MenuBar убрана из DOM в R-12 — её не должно быть
            mb_list = app.query(MenuBar)
            assert len(mb_list) == 0  # не в DOM

    @pytest.mark.asyncio
    async def test_proxy_screen_default_active(self) -> None:
        """По умолчанию активен экран proxy."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # ProxyScreen должен быть в DOM
            screens = app.query(ProxyScreen)
            assert len(screens) > 0


@pytest.mark.integration
class TestModuleNavigation:
    @pytest.mark.asyncio
    async def test_switch_to_repeater(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.repeater.screen import RepeaterScreen
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")  # Shift+R → R
            await pilot.pause()
            screens = app.query(RepeaterScreen)
            assert len(screens) > 0

    @pytest.mark.asyncio
    async def test_switch_to_intruder(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.intruder.screen import IntruderScreen
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            screens = app.query(IntruderScreen)
            assert len(screens) > 0

    @pytest.mark.asyncio
    async def test_switch_back_to_proxy(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.proxy.screen import ProxyScreen
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")  # → Repeater
            await pilot.pause()
            await pilot.press("P")  # → Proxy
            await pilot.pause()
            screens = app.query(ProxyScreen)
            assert len(screens) > 0

    @pytest.mark.asyncio
    async def test_switch_to_decoder(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.decoder.screen import DecoderScreen
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            screens = app.query(DecoderScreen)
            assert len(screens) > 0


@pytest.mark.integration
class TestProxyScreenWidgets:
    @pytest.mark.asyncio
    async def test_http_table_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # ProxyScreen активен по умолчанию
            table = app.query("#request-list")
            assert len(table) > 0

    @pytest.mark.asyncio
    async def test_intercept_button_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            btn = app.query("#btn-intercept")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_forward_button_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            btn = app.query("#btn-forward")
            assert len(btn) > 0


@pytest.mark.integration
class TestRepeaterScreenWidgets:
    @pytest.mark.asyncio
    async def test_send_button_always_in_dom(self) -> None:
        """#btn-send всегда присутствует в DOM даже при неактивной вкладке."""
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            btn = app.query("#btn-send")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_request_editor_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.request_editor import RequestEditor
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            # RepeaterScreen использует динамические ID вида #req-editor-{tab_id}
            editors = app.query(RequestEditor)
            assert len(editors) > 0


@pytest.mark.integration
class TestIntruderScreenWidgets:
    @pytest.mark.asyncio
    async def test_start_button_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            btn = app.query("#btn-start")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_results_table_in_dom(self) -> None:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            table = app.query("#results-table")
            assert len(table) > 0
