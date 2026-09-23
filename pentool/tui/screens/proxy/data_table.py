"""ProxyDataTable — DataTable для HTTP/WS истории прокси.

Единый класс вместо дублирования ArrowBackendDataTable + ProxyDataTable.
Наследует DataTable напрямую, сам управляет ArrowBackend.
"""

from __future__ import annotations

import logging

import pyarrow as pa
from textual import events as _events
from textual.message import Message
from textual_fastdatatable import ArrowBackend, DataTable

log = logging.getLogger(__name__)


def _make_empty_arrow(columns: list[str]) -> pa.Table:
    """Build an empty Arrow table with the given string columns."""
    cols: dict[str, pa.Array] = {}
    for c in columns:
        cols[c] = pa.array([], type=pa.string())
    return pa.table(cols)


class ProxyDataTable(DataTable):
    """DataTable for Proxy HTTP/WS History with overscroll + messages.

    Управляет собственным ArrowBackend. Предоставляет:
    - set_data(arrow) — полная замена данных
    - add_rows(records) — инкрементальное добавление
    - clear_data() — сброс
    - Кастомные сообщения ContextMenuRequest, ScrolledToTop, CommentIconClicked
    """

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

    def __init__(
        self,
        columns: list[str] | None = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._proxy_columns = columns or []
        if self._proxy_columns:
            self.backend = ArrowBackend(_make_empty_arrow(self._proxy_columns))

    def set_data(self, arrow: pa.Table) -> None:
        """Replace the entire table content with an Arrow table."""
        self.backend = ArrowBackend(arrow)

    def add_rows(self, records: list[tuple]) -> None:
        """Add rows via the parent DataTable.add_rows."""
        super().add_rows(records)

    def clear_data(self) -> None:
        """Reset to an empty table (columns preserved)."""
        if self._proxy_columns:
            self.backend = ArrowBackend(_make_empty_arrow(self._proxy_columns))
        else:
            self.clear()

    def safe_sort(self, col_name: str, direction: str = "ascending") -> bool:
        """Безопасная сортировка с crash-guard.

        Вызывает ``ArrowBackend.sort()`` внутри try/except и проверяет
        готовность таблицы. Возвращает True при успехе, False при ошибке.

        Args:
            col_name: имя колонки для сортировки.
            direction: "ascending" или "descending".
        """
        if not self._mouse_ready():
            log.warning("safe_sort: table not ready (skip)")
            return False
        try:
            self.sort(by=[(col_name, direction)])
            return True
        except Exception as exc:
            log.warning("safe_sort failed: %s", exc)
            return False

    async def on_event(self, event: _events.Event) -> None:
        # Crash guard: while the table is being rebuilt or a sheet is mid-mount
        if isinstance(event, _events.MouseEvent) and not self._mouse_ready():
            event.stop()
            return
        if isinstance(event, _events.MouseDown) and (
            event.button == 3 or (event.button == 1 and event.ctrl)
        ):
            await super().on_event(event)
            self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
        elif isinstance(event, _events.MouseUp) and event.button == 1 and not event.ctrl:
            meta = getattr(event.style, "meta", None) if event.style else None
            await super().on_event(event)
            if meta and "row" in meta and "column" in meta:
                self.post_message(self.CommentIconClicked(meta["row"], meta["column"]))
        else:
            await super().on_event(event)

    def _mouse_ready(self) -> bool:
        try:
            parent = self.parent
            if parent is None:
                return False
            region = self.region
            return region.width > 0 and region.height > 0
        except Exception:
            return False

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if new_value <= 0 and old_value > 0 and self.id in ("request-list", "ws-request-list"):
            self.post_message(self.ScrolledToTop(self.id or ""))