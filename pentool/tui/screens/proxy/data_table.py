"""ProxyDataTable — DataTable для HTTP/WS истории прокси.

Наследует ArrowBackendDataTable (widgets/data_table.py), добавляет:
- Кастомные сообщения ContextMenuRequest, ScrolledToTop, CommentIconClicked
- on_event для контекстного меню и comment icon
- watch_scroll_y для infinite scroll (подгрузка старых логов)
"""

from __future__ import annotations

from textual import events as _events
from textual.message import Message

from pentool.tui.widgets.data_table import ArrowBackendDataTable


class ProxyDataTable(ArrowBackendDataTable):
    """DataTable for Proxy HTTP/WS History с контекстным меню и infinite scroll."""

    class ContextMenuRequest(Message):
        """Request to open the context menu from a DataTable."""
        def __init__(self, screen_x: int, screen_y: int) -> None:
            super().__init__()
            self.screen_x = screen_x
            self.screen_y = screen_y

    class ScrolledToTop(Message):
        """Posted when the user scrolls to the very top of the table.

        Used by ProxyScreen (request-list HTTP, ws-request-list WS) as the
        trigger to load an older page of history from SQLite.
        """
        def __init__(self, table_id: str) -> None:
            super().__init__()
            self.table_id = table_id

    class CommentIconClicked(Message):
        """Posted on a single left-click landing in the Host column — used
        to open the comment dialog directly when the row has a 💬 marker."""
        def __init__(self, row_index: int, column_index: int) -> None:
            super().__init__()
            self.row_index = row_index
            self.column_index = column_index

    # ── on_event: контекстное меню + comment icon ────────────────────────

    async def on_event(self, event: _events.Event) -> None:
        if isinstance(event, _events.MouseEvent) and not self._mouse_ready():
            event.stop()
            return
        if isinstance(event, _events.MouseDown) and (
            event.button == 3 or (event.button == 1 and event.ctrl)
        ):
            await super().on_event(event)
            self.post_message(self.ContextMenuRequest(
                event.screen_x, event.screen_y
            ))
        elif isinstance(event, _events.MouseUp) and event.button == 1 and not event.ctrl:
            meta = getattr(event.style, "meta", None) if event.style else None
            await super().on_event(event)
            if meta and "row" in meta and "column" in meta:
                self.post_message(
                    self.CommentIconClicked(meta["row"], meta["column"])
                )
        else:
            await super().on_event(event)

    # ── Infinite scroll ───────────────────────────────────────────────────

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if new_value <= 0 and old_value > 0 and self.id in (
            "request-list", "ws-request-list"
        ):
            self.post_message(self.ScrolledToTop(self.id or ""))