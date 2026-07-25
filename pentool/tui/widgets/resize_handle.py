"""ResizeHandle — перетаскиваемый разделитель между двумя панелями."""

from __future__ import annotations

from textual.events import MouseDown, MouseMove, MouseUp
from textual.widget import Widget
from pathlib import Path

_CSS = (Path(__file__).parent / "resize_handle.tcss").read_text(encoding="utf-8")


class ResizeHandle(Widget):
    """Перетаскиваемый разделитель между двумя виджетами.

    Механика (без пустот, без отставания):
    - mouse_down: фиксируем screen_x/y, размер левой панели и суммарный
      размер пары (left.size + right.size). Total кешируется и не меняется
      во время drag — иначе 1fr плавает.
    - mouse_move: new_left = start_left + (screen_x - start_x).
      new_right = total - new_left. Обе панели в абсолютных единицах → нет пустот.
    - mouse_up: release_mouse.
    """

    DEFAULT_CSS = _CSS

    def __init__(
        self,
        left_id: str,
        right_id: str,
        vertical: bool = False,
        min_left: int = 8,
        min_right: int = 8,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._left_id = left_id
        self._right_id = right_id
        self._vertical = vertical
        self._min_left = min_left
        self._min_right = min_right
        self._dragging = False
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._start_size: int = 0
        self._pair_total_cached: int = 0

        self.tooltip = "Drag to resize"
        if vertical:
            self.add_class("-vertical")

    def render(self) -> str:
        """Рендерим символ-разделитель вместо текста по умолчанию."""
        if self._vertical:
            return "─" * (self.size.width or 1)
        return "│"

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            return
        try:
            left = self.app.query_one(f"#{self._left_id}")
            right = self.app.query_one(f"#{self._right_id}")
        except Exception:
            return

        self._dragging = True
        self._drag_start_x = event.screen_x
        self._drag_start_y = event.screen_y

        if self._vertical:
            self._start_size = left.size.height
            self._pair_total_cached = left.size.height + right.size.height
        else:
            self._start_size = left.size.width
            self._pair_total_cached = left.size.width + right.size.width

        self.add_class("-dragging")
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if not self._dragging:
            return
        try:
            left = self.app.query_one(f"#{self._left_id}")
            right = self.app.query_one(f"#{self._right_id}")
        except Exception:
            return

        delta = event.screen_y - self._drag_start_y if self._vertical else event.screen_x - self._drag_start_x
        total = self._pair_total_cached

        new_left = self._start_size + delta
        new_left = max(self._min_left, min(new_left, total - self._min_right))
        new_right = total - new_left

        if self._vertical:
            left.styles.height = new_left
            right.styles.height = new_right
        else:
            left.styles.width = new_left
            right.styles.width = new_right

        # Принудительный немедленный перерасчёт layout
        if self.parent is not None:
            self.parent.refresh(layout=True)

        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.remove_class("-dragging")
        self.release_mouse()
        event.stop()
