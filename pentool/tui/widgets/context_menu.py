"""Context menu on right-click / keyboard shortcut."""

from __future__ import annotations

from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

_CSS = (Path(__file__).parent / "context_menu.tcss").read_text(encoding="utf-8")


class ContextMenu(Widget):
    """Popup context menu.

    Mounted in app, captures mouse via app.capture_mouse(self).
    Closes on Escape, Enter, or click outside the menu.
    """

    DEFAULT_CSS = _CSS

    can_focus = True

    class ItemSelected(Message):
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    def __init__(
        self,
        items: list[tuple[str, str]],
        x: int,
        y: int,
        callback=None,
    ) -> None:
        super().__init__()
        self._items = items
        self._callback = callback
        self._action_items: list[tuple[str, Static]] = []
        self._focused_idx: int = 0
        self._menu_x = x
        self._menu_y = y
        self.styles.offset = (x, y)

    def compose(self) -> ComposeResult:
        self._action_items = []
        for action, label in self._items:
            if action == "-":
                yield Static("─" * 24, classes="ctx-sep")
            else:
                item = Static(label, classes="ctx-item")
                item._ctx_action = action  # type: ignore[attr-defined]
                self._action_items.append((action, item))
                yield item

    def on_mount(self) -> None:
        self._highlight(0)
        self.app.capture_mouse(self)
        # Two passes: first — preliminary estimate, second — based on real size
        self.call_after_refresh(self._fix_position)
        self.set_timer(0.05, self._fix_position)

    def _fix_position(self) -> None:
        try:
            screen_w = self.app.size.width
            screen_h = self.app.size.height
            menu_w = self.size.width or 30
            # Calculate height manually: each item/sep = 1 line + 2 for border
            total_lines = len(self._items) + 2
            menu_h = self.size.height if self.size.height > 0 else total_lines
            x = self._menu_x
            y = self._menu_y
            if x + menu_w > screen_w:
                x = max(0, screen_w - menu_w)
            if y + menu_h > screen_h:
                y = max(0, screen_h - menu_h)
            self.styles.offset = (x, y)
        except Exception:
            pass

    def _dismiss(self) -> None:
        try:
            self.app.capture_mouse(None)
        except Exception:
            pass
        try:
            self.remove()
        except Exception:
            pass

    def _highlight(self, idx: int) -> None:
        for i, (_, w) in enumerate(self._action_items):
            if i == idx:
                w.add_class("-focused")
            else:
                w.remove_class("-focused")
        self._focused_idx = idx

    def _select(self, action: str) -> None:
        callback = self._callback
        app = self.app  # save before remove()
        self.post_message(self.ItemSelected(action))
        self._dismiss()
        if callback is not None:
            app.call_later(callback, action)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        r = self.region
        left = r.x if r.width  > 0 else self._menu_x
        top  = r.y if r.height > 0 else self._menu_y
        w    = r.width  if r.width  > 0 else 30
        h    = r.height if r.height > 0 else len(self._action_items) + 2

        inside = (left <= event.screen_x < left + w and
                  top  <= event.screen_y < top  + h)

        if not inside:
            self._dismiss()
            return

        # item.region — absolute coordinates (same as event.screen_x/y)
        for action, widget in self._action_items:
            wr = widget.region
            if (wr.y <= event.screen_y < wr.y + wr.height and
                    wr.x <= event.screen_x < wr.x + wr.width):
                self._select(action)
                return
        # Click on border or separator — do not close

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self._dismiss()
            event.stop()
        elif event.key in ("up", "k"):
            if self._action_items:
                self._highlight((self._focused_idx - 1) % len(self._action_items))
            event.stop()
        elif event.key in ("down", "j"):
            if self._action_items:
                self._highlight((self._focused_idx + 1) % len(self._action_items))
            event.stop()
        elif event.key in ("enter", "space"):
            if self._action_items:
                action, _ = self._action_items[self._focused_idx]
                self._select(action)
            event.stop()
