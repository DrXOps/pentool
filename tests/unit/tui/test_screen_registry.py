"""Unit tests for the screen registry (Этап 5.1)."""

from __future__ import annotations

import pytest

from pentool.tui.screen_registry import SCREEN_MAP, get_screen_class

CORE_MODULES = {
    "dashboard",
    "proxy",
    "repeater",
    "intruder",
    "scanner",
    "target",
    # Decoder / Comparer / Sequencer merged into Utils (sub-tabs, not modules).
    "utils",
    "extensions",
    "settings",
}


class TestScreenRegistry:
    def test_all_core_modules_mapped(self):
        # Подмножество, а не равенство: PRO-экраны (recon) регистрируются
        # лениво, при первом обращении к get_screen_class(), поэтому набор
        # ключей зависит от порядка тестов. Точный набор здесь означал бы
        # «тест проходит или падает в зависимости от того, кто раньше
        # открыл Recon».
        missing = CORE_MODULES - set(SCREEN_MAP)
        assert not missing, f"не зарегистрированы экраны: {sorted(missing)}"

    def test_get_screen_class_known(self):
        from pentool.tui.screens.proxy.screen import ProxyScreen

        assert get_screen_class("proxy") is ProxyScreen

    def test_get_screen_class_unknown_returns_none(self):
        assert get_screen_class("nope") is None

    def test_classes_are_widget_types(self):
        for module_id, cls in SCREEN_MAP.items():
            assert isinstance(cls, type), f"{module_id} -> {cls!r} is not a class"

    def test_recon_is_reached_through_the_getter(self):
        """PRO-экран грузится лениво и обязан быть доступен через геттер.

        Импорт на уровне модуля давал цикл app → registry → recon → app:
        `ImportError` проглатывался, и Recon открывался пустым окном. Поэтому
        проверяем именно API, а не наличие ключа в SCREEN_MAP.
        """
        cls = get_screen_class("recon")
        if cls is None:
            pytest.skip("PRO-модуль не установлен в этом окружении")
        assert cls.__name__ == "ReconScreen"
        assert SCREEN_MAP.get("recon") is cls
