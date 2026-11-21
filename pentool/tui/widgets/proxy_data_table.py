"""ProxyDataTable — DataTable for the proxy HTTP/WS history.

Inherits ArrowBackendDataTable (widgets/data_table.py) and adds:
- Custom messages ContextMenuRequest, ScrolledToTop, CommentIconClicked
- on_event for the context menu and the comment icon
- watch_scroll_y for infinite scroll (loading older log pages)
"""

from __future__ import annotations

from textual import events as _events
from textual.message import Message

from pentool.core.logging import get_logger
from pentool.tui.widgets.data_table import ArrowBackendDataTable

logger = get_logger(__name__)


class ProxyDataTable(ArrowBackendDataTable):
    """DataTable for the Proxy HTTP/WS history with a context menu and infinite scroll."""

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

    def _get_cell_renderable(self, row_index, column_index):  # noqa: ANN201
        """Format Size (int64) into a human-readable form (KB/MB).

        All other columns keep the standard behaviour.
        """
        if row_index == -1:
            # header — via the base class
            return super()._get_cell_renderable(row_index, column_index)
        try:
            col = self.ordered_columns[column_index]
            label = str(col.label).strip()
            if label == "Size":
                from textual_fastdatatable.data_table import Coordinate

                raw = self.get_cell_at(Coordinate(row=row_index, column=column_index))
                if raw is not None:
                    from pentool.tui.widgets.proxy_helpers import format_size

                    return format_size(int(raw))
                return "-"
        except Exception as exc:
            # The Size column falls back to the raw backend value — the size is
            # then shown in bytes, unformatted, and cannot be eyeballed against
            # the neighbouring rows.
            logger.debug("proxy table: size cell not formatted: %s", exc)
        return super()._get_cell_renderable(row_index, column_index)

    # ── on_event: context menu + comment icon ────────────────────────────

    async def on_event(self, event: _events.Event) -> None:
        if isinstance(event, _events.MouseEvent) and not self._mouse_ready():
            event.stop()
            return
        if isinstance(event, _events.MouseDown) and (event.button == 3 or (event.button == 1 and event.ctrl)):
            await super().on_event(event)
            # The screen owns the menu; ask it via a message instead of
            # reaching up the DOM for a private method.
            self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
        elif isinstance(event, _events.MouseUp) and event.button == 1 and not event.ctrl:
            meta = getattr(event.style, "meta", None) if event.style else None
            await super().on_event(event)
            if meta and "row" in meta and "column" in meta:
                self.post_message(self.CommentIconClicked(meta["row"], meta["column"]))
        else:
            await super().on_event(event)

    # ── Column widths: Host and URL share the leftover width ─────────────

    #: The cards plan's "URL → 1fr": Host is clamped so a long hostname cannot
    #: push the URL out of view, URL absorbs the rest. The mechanism itself
    #: lives in the shared base (`ArrowBackendDataTable.fit_columns`) — another
    #: module opts in by declaring its own spec, no maths copied around.
    SPARE_COLUMNS = {"Host": (14, 26), "URL": (20, None)}

    # ── Infinite scroll ───────────────────────────────────────────────────

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if new_value <= 0 and old_value > 0 and self.id in ("request-list", "ws-request-list"):
            self.post_message(self.ScrolledToTop(self.id or ""))
