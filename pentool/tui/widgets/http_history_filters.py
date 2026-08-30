"""HTTP-history filter composition for the Proxy screen (Этап 6, history).

The Proxy screen hands a `filters` dict to ProxyService.get_history, which
resolves scope-only / websocket defaults (`_effective_filters`) and the
storage applies the rest. `build_history_filters` composes the screen-level
part of that dict that used to live inline in the mega-screen's
`_reload_table` — a thin, pure, unit-testable slice of the History
"controller" that keeps filter grammar out of the screen body.

Behavior must equal the old inline block exactly (a move, not a change):
- None/empty dict stays a bare dict (service treats empty as no filter).
- `show_comments` adds `has_comment: True`.
- `scope_only` is left untouched — ProxyService._effective_filters expands
  it into the concrete host list downstream.
"""

from __future__ import annotations


def build_history_filters(bar_filters: dict | None, show_comments: bool) -> dict:
    """Compose the filters dict sent to ProxyService.get_history.

    bar_filters   — the raw dict from FilterBar (may be None / empty).
    show_comments — when True, restrict to rows carrying a user comment.
    """
    f = dict(bar_filters) if bar_filters else {}
    if show_comments:
        f["has_comment"] = True
    return f
