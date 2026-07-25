"""Unit-тесты для core/plugin_manager.py — интеграция с лицензией."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from pentool.core.license import LicenseInfo
from pentool.core.plugin_manager import (
    CURRENT_API_VERSION,
    BaseCheck,
    BasePlugin,
    BaseScanner,
    PluginHook,
    PluginManager,
    PluginMeta,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_plugin(path: Path, code: str) -> None:
    path.write_text(textwrap.dedent(code), encoding="utf-8")


def _free_plugin_code(name: str = "free_plugin") -> str:
    return f"""
        from pentool.core.plugin_manager import BasePlugin, PluginHook

        class MyPlugin(BasePlugin):
            name = "{name}"
            version = "1.0"
            author = "Test"
            description = "Free test plugin"
            api_version = {CURRENT_API_VERSION}
            required_feature = ""

        def register(hook: PluginHook) -> None:
            pass
    """


def _pro_plugin_code(name: str = "pro_plugin", feature: str = "scanner_pro") -> str:
    return f"""
        from pentool.core.plugin_manager import BasePlugin, PluginHook

        class ProPlugin(BasePlugin):
            name = "{name}"
            version = "1.0"
            author = "Test"
            description = "PRO plugin"
            api_version = {CURRENT_API_VERSION}
            required_feature = "{feature}"

        def register(hook: PluginHook) -> None:
            pass
    """


def _future_api_plugin_code(name: str = "future_plugin") -> str:
    future = CURRENT_API_VERSION + 1
    return f"""
        from pentool.core.plugin_manager import BasePlugin, PluginHook

        class FuturePlugin(BasePlugin):
            name = "{name}"
            version = "1.0"
            author = "Test"
            description = "Future API plugin"
            api_version = {future}
            required_feature = ""

        def register(hook: PluginHook) -> None:
            pass
    """


def _screen_plugin_code(name: str = "screen_plugin") -> str:
    return f"""
        from textual.widget import Widget
        from pentool.core.plugin_manager import BasePlugin, PluginHook

        class DummyWidget(Widget):
            pass

        class ScreenPlugin(BasePlugin):
            name = "{name}"
            version = "1.0"
            author = "Test"
            description = "Plugin with screen"
            api_version = {CURRENT_API_VERSION}
            required_feature = ""

        def register(hook: PluginHook) -> None:
            hook.register_screen("Dummy Screen", DummyWidget, hotkey="S+9")
    """


# ── PluginHook ─────────────────────────────────────────────────────────────────

class TestPluginHook:
    def test_register_screen(self):
        from textual.widget import Widget
        hook = PluginHook("test_plugin")
        hook.register_screen("My Screen", Widget)
        assert len(hook._screens) == 1
        assert hook._screens[0].name == "My Screen"
        assert hook._screens[0].plugin_name == "test_plugin"

    def test_register_scanner(self):
        hook = PluginHook("test_plugin")

        class MyScanner(BaseScanner):
            name = "my_scanner"

        hook.register_scanner(MyScanner)
        assert len(hook._scanners) == 1
        assert hook._scanners[0] is MyScanner

    def test_register_passive_check(self):
        hook = PluginHook("test_plugin")

        class MyCheck(BaseCheck):
            name = "my_check"
            passive = True

        hook.register_passive_check(MyCheck)
        assert len(hook._passive_checks) == 1

    def test_register_screen_with_hotkey(self):
        from textual.widget import Widget
        hook = PluginHook("p")
        hook.register_screen("Screen", Widget, hotkey="S+0")
        assert hook._screens[0].hotkey == "S+0"


# ── PluginManager — free plugins ───────────────────────────────────────────────

class TestPluginManagerFree:
    def test_loads_free_plugin(self, tmp_path):
        plugin_file = tmp_path / "free_plugin.py"
        _write_plugin(plugin_file, _free_plugin_code())
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])
        assert len(pm.loaded_plugins()) == 1
        assert str(plugin_file) in pm.loaded_plugins()

    def test_meta_populated_for_free_plugin(self, tmp_path):
        plugin_file = tmp_path / "free_plugin.py"
        _write_plugin(plugin_file, _free_plugin_code("myfree"))
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])
        meta = pm.get_meta()
        assert len(meta) == 1
        m = meta[0]
        assert m.name == "free_plugin"
        assert m.loaded is True
        assert m.required_feature == ""

    def test_skips_files_starting_with_underscore(self, tmp_path):
        plugin_file = tmp_path / "_private_plugin.py"
        _write_plugin(plugin_file, _free_plugin_code("_private"))
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])
        assert len(pm.loaded_plugins()) == 0

    def test_loads_screen_plugin(self, tmp_path):
        plugin_file = tmp_path / "screen_plugin.py"
        _write_plugin(plugin_file, _screen_plugin_code())
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])
        screens = pm.get_screens()
        assert len(screens) == 1
        assert screens[0].name == "Dummy Screen"
        assert screens[0].hotkey == "S+9"

    def test_skips_future_api_version(self, tmp_path):
        plugin_file = tmp_path / "future_plugin.py"
        _write_plugin(plugin_file, _future_api_plugin_code())
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])
        assert len(pm.loaded_plugins()) == 0
        meta = pm.get_meta()
        assert len(meta) == 1
        assert meta[0].loaded is False

    def test_handles_missing_register_function(self, tmp_path):
        plugin_file = tmp_path / "bad_plugin.py"
        plugin_file.write_text("x = 1\n", encoding="utf-8")
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])  # no exception
        assert len(pm.loaded_plugins()) == 0

    def test_handles_broken_plugin(self, tmp_path):
        plugin_file = tmp_path / "broken_plugin.py"
        plugin_file.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        pm = PluginManager()
        pm.load_plugins([str(tmp_path)])  # no exception
        assert len(pm.loaded_plugins()) == 0


# ── PluginManager — PRO plugins with license ──────────────────────────────────

class TestPluginManagerProLicense:
    def _make_pro_pm(self, tmp_path, info: LicenseInfo) -> PluginManager:
        plugin_file = tmp_path / "pro_plugin.py"
        _write_plugin(plugin_file, _pro_plugin_code())
        pm = PluginManager()
        with patch("pentool.core.plugin_manager.PluginManager._check_license_feature",
                   return_value=info.has_feature("scanner_pro")):
            pm.load_plugins([str(tmp_path)])
        return pm

    def test_pro_plugin_blocked_on_free_license(self, tmp_path):
        free_info = LicenseInfo(valid=False, plan="free")
        pm = self._make_pro_pm(tmp_path, free_info)
        assert len(pm.loaded_plugins()) == 0
        meta = pm.get_meta()
        assert len(meta) == 1
        assert meta[0].loaded is False
        assert meta[0].required_feature == "scanner_pro"

    def test_pro_plugin_loads_with_valid_pro_license(self, tmp_path):
        pro_info = LicenseInfo(valid=True, plan="pro", features=["scanner_pro"])
        pm = self._make_pro_pm(tmp_path, pro_info)
        assert len(pm.loaded_plugins()) == 1
        meta = pm.get_meta()
        assert meta[0].loaded is True

    def test_pro_plugin_blocked_when_feature_missing(self, tmp_path):
        """PRO лицензия но без нужной feature."""
        plugin_file = tmp_path / "pro_reports.py"
        _write_plugin(plugin_file, _pro_plugin_code(feature="reports_pro"))
        pm = PluginManager()
        # Лицензия PRO но только со scanner_pro, без reports_pro
        with patch("pentool.core.plugin_manager.PluginManager._check_license_feature",
                   return_value=False):
            pm.load_plugins([str(tmp_path)])
        assert len(pm.loaded_plugins()) == 0

    def test_multiple_plugins_mixed_license(self, tmp_path):
        """Free + PRO плагины: free загружается, PRO заблокирован без лицензии."""
        _write_plugin(tmp_path / "free_plugin.py", _free_plugin_code())
        _write_plugin(tmp_path / "pro_plugin.py", _pro_plugin_code())
        pm = PluginManager()
        # free → OK, pro → blocked
        def check_feature(feature):
            return False  # нет лицензии

        with patch.object(pm, "_check_license_feature", side_effect=check_feature):
            pm.load_plugins([str(tmp_path)])

        assert len(pm.loaded_plugins()) == 1
        meta = pm.get_meta()
        assert len(meta) == 2
        loaded = [m for m in meta if m.loaded]
        blocked = [m for m in meta if not m.loaded]
        assert len(loaded) == 1
        assert len(blocked) == 1
        assert loaded[0].required_feature == ""
        assert blocked[0].required_feature == "scanner_pro"

    def test_is_feature_available_delegates_to_license(self):
        pm = PluginManager()
        with patch("pentool.core.plugin_manager.PluginManager._check_license_feature",
                   return_value=True):
            assert pm.is_feature_available("scanner_pro") is True
        with patch("pentool.core.plugin_manager.PluginManager._check_license_feature",
                   return_value=False):
            assert pm.is_feature_available("scanner_pro") is False

    def test_check_license_feature_no_license_module(self):
        """Если license модуль недоступен — не падаем, возвращаем False."""
        pm = PluginManager()
        with patch("pentool.core.license.get_session_license", side_effect=RuntimeError("boom")):
            result = pm._check_license_feature("scanner_pro")
        assert result is False


# ── PluginManager — load_user_plugins ─────────────────────────────────────────

class TestPluginManagerUserPlugins:
    def test_load_user_plugins_nonexistent_dir(self):
        """Нет ~/.pentool/plugins — не падаем."""
        pm = PluginManager()
        with patch("pentool.core.plugin_manager.USER_PLUGINS_DIR", Path("/nonexistent/path")):
            pm.load_user_plugins()  # no exception
        assert len(pm.loaded_plugins()) == 0

    def test_load_user_plugins_loads_from_user_dir(self, tmp_path):
        plugin_file = tmp_path / "my_plugin.py"
        _write_plugin(plugin_file, _free_plugin_code("user_plugin"))
        pm = PluginManager()
        with patch("pentool.core.plugin_manager.USER_PLUGINS_DIR", tmp_path):
            pm.load_user_plugins()
        assert len(pm.loaded_plugins()) == 1


# ── BasePlugin / BaseCheck / BaseScanner ──────────────────────────────────────

class TestBaseClasses:
    def test_base_plugin_defaults(self):
        class MyPlugin(BasePlugin):
            name = "test"

        p = MyPlugin()
        assert p.name == "test"
        assert p.version == "0.1"
        assert p.api_version == CURRENT_API_VERSION
        assert p.required_feature == ""

    def test_base_check_scan_returns_empty(self):
        import asyncio

        class MyCheck(BaseCheck):
            name = "check"

        check = MyCheck()
        result = asyncio.run(check.scan(None, None))
        assert result == []

    def test_base_scanner_scan_calls_checks(self):
        import asyncio

        calls = []

        class MyCheck(BaseCheck):
            name = "check"
            async def scan(self, target, http_client, **kwargs):
                calls.append("called")
                return ["finding"]

        class MyScanner(BaseScanner):
            name = "scanner"
            checks = [MyCheck]

        scanner = MyScanner()
        results = asyncio.run(scanner.scan(None, None))
        assert results == ["finding"]
        assert calls == ["called"]

    def test_base_scanner_tolerates_check_exceptions(self):
        import asyncio

        class BadCheck(BaseCheck):
            name = "bad"
            async def scan(self, target, http_client, **kwargs):
                raise RuntimeError("explosion")

        class MyScanner(BaseScanner):
            name = "scanner"
            checks = [BadCheck]

        scanner = MyScanner()
        results = asyncio.run(scanner.scan(None, None))
        assert results == []  # пустой, не упал


# ── PluginMeta ─────────────────────────────────────────────────────────────────

class TestPluginMeta:
    def test_defaults(self):
        m = PluginMeta(name="test", path="/path/test.py")
        assert m.loaded is True
        assert m.required_feature == ""
        assert m.version == "?"

    def test_blocked_meta(self):
        m = PluginMeta(
            name="pro_scanner",
            path="/path/pro.py",
            required_feature="scanner_pro",
            loaded=False,
        )
        assert m.loaded is False
        assert m.required_feature == "scanner_pro"
