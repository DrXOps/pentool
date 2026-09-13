"""Context Menu helper for ProxyScreen — right-click and copy-as actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pentool.core.logging import get_logger

if TYPE_CHECKING:
    from pentool.tui.screens.proxy.screen import ProxyScreen

logger = get_logger(__name__)


def open_context_menu(proxy_screen: ProxyScreen, x: int, y: int) -> None:
    """Open the Proxy request context menu at (x, y).

    Shares the `_cm_*` mixin (from RequestContextMenuMixin), so item flags
    are configured in the ProxyScreen class itself. We just build the
    screen-local items (mark/comment) and open.
    """
    req_id = proxy_screen._selected_req_id
    has_comment = bool(proxy_screen._current_comment)
    screen_items = [
        ("-", ""),
    ]
    if req_id:
        screen_items += [
            ("mark", "🎨 Mark color" if not has_comment else f"💬 Mark color (comment: {proxy_screen._current_comment[:20]})"),
            ("comment", "💬 Comment" if not has_comment else "✏️ Edit comment"),
        ]
    menu_items = proxy_screen._cm_build_items()
    # Insert screen items before the final send-to group
    send_idx = -1
    for i, (action, _) in enumerate(menu_items):
        if action == "send_repeater":
            send_idx = i
            break
    full_items = menu_items[:send_idx] + screen_items + menu_items[send_idx:]
    proxy_screen.app.show_context_menu(full_items, x, y, callback=lambda a: _cm_dispatch(proxy_screen, a))


def _cm_dispatch(proxy_screen: ProxyScreen, action: str) -> None:
    """Route context-menu actions."""
    if action == "mark":
        proxy_screen._mark_dialog()
    elif action == "comment":
        proxy_screen._comment_dialog()
    else:
        proxy_screen._cm_handle(action)