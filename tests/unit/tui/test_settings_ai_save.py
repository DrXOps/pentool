"""The AI tab's Save button: the second instance of the same regression.

``0f563b3`` removed ``ToolbarButton("Save", "settings-save-ai")`` when the
``ai_enabled`` switch became live-saving, but left ``_save_ai_settings`` and
its ``@on(..., "#settings-save-ai")`` decorator behind. The MCP port and the
model path were still loaded from config into the two ``Input`` widgets and
still written back by ``_save_ai_settings`` — the only way to reach that code
was a button that no longer existed.

``test_on_selectors_resolve.py`` catches the shape of this statically. These
tests pin the behaviour, because "the id exists" is weaker than "pressing it
persists the edits", and a future toolbar rewrite can pass the first while
breaking the second.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult

from pentool.tui.screens.settings.screen import SettingsScreen


class _App(App):
    """Bare host app. ``_cfg`` is what ``PentoolApp`` sets at startup and what
    ``_save_ai_settings`` checks before touching the config; ``_save_settings``
    is patched per-test, so a sentinel object is enough."""

    def compose(self) -> ComposeResult:
        yield SettingsScreen()

    def __init__(self) -> None:
        super().__init__()
        self._cfg = object()


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Конфиг на время теста — свой, а не ~/.config/pentool/config.yaml.

    Иначе prefill читает реальный файл: если там ai_enabled=true, переключатель
    уже включён, установка True не даёт события Changed, и тест падает по
    причине, не связанной с кодом.
    """
    from pentool.core.config import Config, set_config

    set_config(Config(db_path=str(tmp_path / "t.db"), cert_dir=str(tmp_path / "certs")))
    yield


async def _open_settings(pilot):
    await pilot.pause()
    return pilot.app.query_one(SettingsScreen)


class TestAiSaveButton:
    async def test_button_exists_on_the_ai_tab(self) -> None:
        app = _App()
        async with app.run_test(size=(160, 50)) as pilot:
            screen = await _open_settings(pilot)
            found = screen.query("#settings-save-ai")
            assert len(found) == 1, "#settings-save-ai is wired to a handler but has no button"

    async def test_pressing_it_saves_port_and_model_path(self) -> None:
        app = _App()
        async with app.run_test(size=(160, 50)) as pilot:
            screen = await _open_settings(pilot)
            from pentool.tui.widgets.toolbar_button import ToolbarButton

            screen.query_one("#set-ai-mcp-port").value = "8765"
            screen.query_one("#set-ai-model-path").value = "/tmp/model.gguf"

            captured: dict[str, object] = {}

            def _capture(_self, changes, message):
                captured.update(changes)
                captured["__message"] = message

            with patch.object(SettingsScreen, "_save_settings", _capture):
                button = screen.query_one("#settings-save-ai", ToolbarButton)
                button.post_message(ToolbarButton.Pressed(button))
                await pilot.pause()
                await pilot.pause()

            assert captured.get("ai_mcp_port") == 8765
            assert captured.get("ai_mcp_model_path") == "/tmp/model.gguf"

    async def test_the_enabled_switch_stays_live_saving(self) -> None:
        """The reason the button was removed must keep working.

        ``0f563b3``'s point was that ``ai_enabled`` saves on toggle; restoring
        the button must not have brought ``ai_enabled`` back under it, or the
        switch would write twice.
        """
        app = _App()
        async with app.run_test(size=(160, 50)) as pilot:
            screen = await _open_settings(pilot)
            saved: dict[str, object] = {}

            with patch.object(SettingsScreen, "_save_settings", lambda _s, ch, msg: saved.update(ch)):
                screen.query_one("#set-ai-enabled").value = True
                await pilot.pause()
                await pilot.pause()

            assert saved.get("ai_enabled") is True
            assert "ai_mcp_port" not in saved, "the live switch must save only ai_enabled"
