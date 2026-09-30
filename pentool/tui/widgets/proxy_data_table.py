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

    # ── Size formatting (int64 data → human-readable display) ────────────────

    def _get_cell_renderable(self, row_index: int, column_index: int, max_width: int | None = None) -> RichText | Text:  # noqa: ANN201
        """Форматировать Size (int64) в человекочитаемый вид (KB/MB).

        Для всех остальных колонок — стандартное поведение.
        """
        if row_index == -1:
            # header — через базовый класс
            return super()._get_cell_renderable(row_index, column_index, max_width)
        try:
            col = self.ordered_columns[column_index]
            label = str(col.label).strip()
            if label == "Size":
                raw = self.get_cell_at(row_index, column_index)
                if raw is not None:
                    from pentool.tui.widgets.proxy_helpers import format_size
                    return format_size(int(raw))
                return "-"
        except Exception:
            pass
        return super()._get_cell_renderable(row_index, column_index, max_width)

    # ── on_event: контекстное меню + comment icon ────────────────────────

    async def on_event(self, event: _events.Event) -> None:
        from pentool.core.logging import get_logger as _log
        if isinstance(event, _events.MouseEvent) and not self._mouse_ready():
            event.stop()
            return
        if isinstance(event, _events.MouseDown) and (
            event.button == 3 or (event.button == 1 and event.ctrl)
        ):
            _log().info("PDT: right-click on DataTable, button=%d", event.button)
            await super().on_event(event)
            # Walk up the DOM to find ProxyScreen._open_context_menu
            try:
                node = self.parent
                while node is not None:
                    if hasattr(node, '_open_context_menu'):
                        node._open_context_menu(event.screen_x, event.screen_y)
                        break
                    node = getattr(node, 'parent', None) if hasattr(node, 'parent') else None
            except Exception as exc:
                _log().error("PDT: context menu failed: %s", exc)
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