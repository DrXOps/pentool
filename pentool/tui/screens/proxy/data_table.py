"""_ProxyDataTable — DataTable for Proxy HTTP History with overscroll + messages."""

from __future__ import annotations

from textual import events as _events
from textual.message import Message
from textual_fastdatatable import DataTable as _BaseDataTable


class ProxyDataTable(_BaseDataTable):
    """DataTable for Proxy HTTP History.

    For Ctrl+left-click we post a custom ContextMenuRequest message so that
    ProxyScreen can open the context menu without relying on event bubbling.
    (Right-click button=3 does not reach Textual in a VTE terminal.)
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
        trigger to load an older page of history from SQLite — see
        ProxyScreen._load_more_history() / _load_more_ws_history().
        """
        def __init__(self, table_id: str) -> None:
            super().__init__()
            self.table_id = table_id

    class CommentIconClicked(Message):
        """Posted on a single left-click landing in the Host column — used
        to open the comment dialog directly when the row has a 💬 marker,
        without requiring Enter/double-click first."""
        def __init__(self, row_index: int, column_index: int) -> None:
            super().__init__()
            self.row_index = row_index
            self.column_index = column_index

    async def on_event(self, event: _events.Event) -> None:
        # Crash guard: while the table is being rebuilt (we swap `backend` in
        # _load_more_history / _flush_pending_rows on every live request) or a
        # sheet is mid (re)mount, the widget may momentarily have `parent is
        # None` / a zeroed region. If a MouseDown lands in that instant, Textual's
        # Screen._forward_event assumes `container = content_widget.parent` is a
        # live node and dereferences it → AttributeError: 'NoneType' has no
        # attribute 'region' → the whole App dies ("TUI just vanished"). Swallow
        # the event instead of letting that crash tear down the app; the click is
        # irrelevant on a table that isn't laid out yet anyway. We still handle
        # movement/scroll (non-mouse events) normally below.
        if isinstance(event, _events.MouseEvent) and not self._mouse_ready():
            event.stop()
            return
        if isinstance(event, _events.MouseDown) and (
            event.button == 3 or (event.button == 1 and event.ctrl)
        ):
            # Call the base handler first (moves cursor to the row)
            await super().on_event(event)
            # Post our own message — it always bubbles to the parent
            self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
        elif isinstance(event, _events.MouseUp) and event.button == 1 and not event.ctrl:
            # Plain left-click release — figure out which cell it landed on
            # via the same style.meta mechanism textual_fastdatatable itself
            # uses for cursor placement, then let the base class handle the
            # click as usual (cursor move, RowSelected, etc).
            meta = getattr(event.style, "meta", None) if event.style else None
            await super().on_event(event)
            if meta and "row" in meta and "column" in meta:
                self.post_message(self.CommentIconClicked(meta["row"], meta["column"]))
        else:
            await super().on_event(event)

    def _mouse_ready(self) -> bool:
        """True when the table has a live parent and a laid-out region, i.e. a
        click can be resolved to a row safely. Textual's Screen._forward_event
        requires a non-None `container` (widget parent) to build a SelectStart;
        if we swallow the event while not ready, we avoid the
        `AttributeError: 'NoneType' object has no attribute 'region'` crash
        (see the guard in on_event)."""
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
        # Both the HTTP History (id="request-list") and the WS History
        # (id="ws-request-list") tables support scroll-up-to-load-more; the WS
        # one used to load the whole history (now page-capped at 300) and had
        # no pagination — older WS rows were unreachable. Both now share the
        # same scroll-up pagination path.
        if new_value <= 0 and old_value > 0 and self.id in ("request-list", "ws-request-list"):
            self.post_message(self.ScrolledToTop(self.id or ""))