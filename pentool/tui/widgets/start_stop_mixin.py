"""StartStopMixin — единая реализация кнопок Start/Pause/Resume/Stop.

Используется экранами с длительными операциями (Intruder, Scanner, Recon).
Предоставляет:

- _set_running_state(running) — переключает btn-start/btn-stop
- @on("#btn-start") — хендлер: Start → Pause / Pause → Resume
- @on("#btn-stop") — хендлер: Stop (хард-стоп, без сохранения прогресса)
- action_toggle_pause() — переключение Pause/Resume
- action_stop() — хард-стоп (должен быть переопределён экраном)

Ожидает в compose():
    Toolbar.start_stop("btn-start", "btn-stop")
"""

from __future__ import annotations

from textual import on

from pentool.core.logging import get_logger
from pentool.tui.widgets.toolbar_button import ToolbarButton

_log = get_logger(__name__)


class StartStopMixin:
    """Mixin для Start/Pause/Resume/Stop кнопок.

    Подмешивается к Screen/Widget.
    """

    # Обязательные поля — экран должен их определить
    _running: bool = False
    _paused: bool = False

    def _set_running_state(self, running: bool) -> None:
        """Обновить btn-start/btn-stop при старте/остановке."""
        try:
            self.query_one("#btn-start", ToolbarButton).label = (
                "⏸ Pause" if running else "▶ Start"
            )
            self.query_one("#btn-start", ToolbarButton).variant = (
                "warning" if running else "success"
            )
            self.query_one("#btn-stop", ToolbarButton).disabled = not running
            if not running:
                self._paused = False
        except Exception:
            _log.debug("_set_running_state: btn widgets not ready yet", exc_info=True)

    @on(ToolbarButton.Pressed, "#btn-start")
    def on_btn_start(self, _: ToolbarButton.Pressed) -> None:
        """Start / Pause / Resume — в зависимости от состояния."""
        if self._paused:
            self.action_resume()
        elif self._running:
            self.action_toggle_pause()
        else:
            self.action_start()

    @on(ToolbarButton.Pressed, "#btn-stop")
    def on_btn_stop(self, _: ToolbarButton.Pressed) -> None:
        """Хард-стоп (без сохранения прогресса)."""
        self.action_stop()

    # ── Методы, которые экран переопределяет ─────────────────────────

    def action_start(self) -> None:
        """Начать операцию. Переопределить в экране."""
        raise NotImplementedError

    def action_stop(self) -> None:
        """Остановить операцию (хард-стоп)."""
        self._running = False
        self._paused = False
        self._set_running_state(False)

    def action_resume(self) -> None:
        """Продолжить после паузы. По умолчанию вызывает action_start()."""
        self.action_start()

    def action_toggle_pause(self) -> None:
        """Pause / Resume."""
        if not self._running:
            return
        if self._paused:
            self._paused = False
            self.query_one("#btn-start", ToolbarButton).label = "⏸ Pause"
            self.action_resume()
        else:
            self._paused = True
            self.query_one("#btn-start", ToolbarButton).label = "▶ Resume"