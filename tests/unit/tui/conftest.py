"""Isolation for TUI screen tests.

Экраны получают путь к базе проекта через `AppMixin._get_db_path()`, то есть из
конфигурации машины (`~/.config/pentool/pentool.db`). Без изоляции прогон
UNIT-тестов пишет в историю настоящего проекта: например, `Repeater.on_mount`
восстанавливает вкладки, а автосохранение затем складывает их обратно, и после
такого прогона у пользователя появляются вкладки, которых он не создавал.

Здесь путь уводится в пустоту: `""` для экранов означает «базы нет», и они
работают на вкладке по умолчанию. Тесты, которым нужна настоящая схема, задают
свой путь сами (`tmp_path`) и перекрывают эту подмену — см.
`test_repeater_tab_state_survives.py`.
"""

from __future__ import annotations

import pytest

from pentool.tui.mixins.app_mixin import AppMixin


@pytest.fixture(autouse=True)
def _no_project_database(monkeypatch):
    monkeypatch.setattr(AppMixin, "_get_db_path", lambda _self: "")
