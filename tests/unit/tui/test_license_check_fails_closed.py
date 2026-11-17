"""Платная проверка лицензии не открывает доступ при сбое (ADR-6).

`_switch_to` блокирует Scanner и Recon без лицензии. Оба обработчика были
написаны «чтобы не падало»: `except Exception: pass`, — и это превращало сбой
чтения лицензии в разрешение. Ошибка в проверке открывала платный модуль.

Здесь закреплено обратное: не смогли проверить — не пускаем, и пользователю
сказано, почему. `pass` вместо `notify` вернул бы старое поведение молча, а
это ровно тот класс дефектов, который аудит и вычищает.

Почему тест в unit, а не e2e: он не проверяет клавиши и вёрстку, только
решение о доступе. Проверка клавиш живёт в `tests/e2e/test_navigation.py`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.widgets import ContentSwitcher

from pentool.tui.app import PentoolApp
from pentool.tui.screen_registry import get_screen_class


async def _attempt_switch(module_id: str, app: PentoolApp) -> tuple[str | None, list[str]]:
    """Переключить модуль и вернуть (что стало активным, тексты уведомлений)."""
    notes: list[str] = []
    original_notify = app.notify

    def _capture(message, **kwargs):
        notes.append(str(message))
        return original_notify(message, **kwargs)

    app.notify = _capture  # type: ignore[method-assign]
    app._switch_to(module_id)
    return app.query_one(ContentSwitcher).current, notes


@pytest.mark.parametrize(
    ("module_id", "screen_id"),
    [
        ("scanner", "screen-scanner"),
        pytest.param(
            "recon",
            "screen-recon",
            marks=pytest.mark.skipif(
                # Спрашиваем геттер, а не словарь: PRO-экран регистрируется
                # лениво, и `"recon" in SCREEN_MAP` до первого обращения даёт
                # False даже когда PRO установлен — тест скипался впустую.
                get_screen_class("recon") is None,
                reason="Recon живёт в pro-сабмодуле; без него гейт недостижим (_switch_to выходит раньше)",
            ),
        ),
    ],
)
class TestBrokenLicenseCheckDoesNotGrantAccess:
    async def test_a_raising_license_check_blocks_the_module(self, module_id: str, screen_id: str) -> None:
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            with patch(
                "pentool.core.license.get_session_license",
                side_effect=RuntimeError("license file unreadable"),
            ):
                current, notes = await _attempt_switch(module_id, app)
            await pilot.pause()

        assert current != screen_id, (
            f"{module_id} opened although the license check raised — "
            "the handler fails open, and a broken license file becomes a free pass"
        )
        assert any("could not verify the license" in n for n in notes), (
            f"access was denied but the user was not told why; notifications: {notes!r}"
        )

    async def test_an_invalid_license_blocks_the_module(self, module_id: str, screen_id: str) -> None:
        """Контроль: обычный отказ (лицензии нет) по-прежнему закрывает модуль."""
        from pentool.core.license import LicenseInfo

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            with patch(
                "pentool.core.license.get_session_license",
                return_value=LicenseInfo(valid=False),
            ):
                current, _notes = await _attempt_switch(module_id, app)
            await pilot.pause()

        assert current != screen_id
