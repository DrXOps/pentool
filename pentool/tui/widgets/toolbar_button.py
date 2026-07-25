"""ToolbarButton — единая плоская кнопка для тулбаров всех экранов."""

from __future__ import annotations

from textual.message import Message
from textual.widgets import Static
from pathlib import Path

_CSS = (Path(__file__).parent / "toolbar_button.tcss").read_text(encoding="utf-8")


class ToolbarButton(Static):
    """Плоская кнопка для тулбара — без рамки, высота 1.

    CSS-классы:
        .active   — зелёный цвет (включено / активно)
        .inactive — красный цвет (выключено)
        .disabled — серый цвет, клик игнорируется
        .warn     — оранжевый цвет (предупреждение)
        .sending  — жёлтый цвет (ожидание ответа)
    """

    DEFAULT_CSS = _CSS

    class Pressed(Message):
        """Сообщение о нажатии кнопки."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, button: "ToolbarButton") -> None:
            super().__init__()
            self.button = button

        @property
        def control(self) -> "ToolbarButton":
            """Позволяет @on(ToolbarButton.Pressed, "#btn-id") CSS-селектор."""
            return self.button

    def __init__(self, label: str, btn_id: str, classes: str = "") -> None:
        super().__init__(label, id=btn_id, classes=classes)
        self._label = label
        self._disabled = "disabled" in classes.split()

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        self._label = value
        self.update(value)

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, value: bool) -> None:
        self._disabled = value
        if value:
            self.add_class("disabled")
        else:
            self.remove_class("disabled")

    def on_click(self) -> None:
        """Постит Pressed только если кнопка не disabled."""
        if not self._disabled:
            self.post_message(self.Pressed(self))
