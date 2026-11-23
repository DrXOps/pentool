"""One factory for static sub-tabs (Utils / Settings / Recon) — T-030, part 2.

Modules that hold a fixed set of panes (three tools, four recon tables, settings
categories) each built their own `TabbedContent(initial=...)` and kept the active pane
in a private attribute. Consequences: the choice was forgotten on restart, and the
"which pane is active" logic was written four times.

`static_tabs()` builds the strip; `remembered_tab()` / `remember_tab()` keep the choice in
the config (`Config.last_subtabs`), so every module behaves the same way.

Document-tab modules (Intruder, and later Scanner/Repeater) keep using
`TabbedContentPanel`: they create and close tabs with their own persisted state.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane

from pentool.core.logging import get_logger

logger = get_logger(__name__)

#: Called to build the body of one static pane.
TabBuilder = Callable[[], Widget]


def static_tabs(
    container_id: str,
    tabs: Sequence[tuple[str, str, TabBuilder]],
    *,
    initial: str | None = None,
) -> ComposeResult:
    """Build a `TabbedContent` of fixed panes.

    Args:
        container_id: DOM id of the TabbedContent (used by header chips and hotkeys).
        tabs: `(tab_id, label, build_body)` in strip order.
        initial: tab to open; defaults to the first one. Pass `remembered_tab(...)`
            here to restore the user's last choice.
    """
    if not tabs:
        raise ValueError("static_tabs() needs at least one tab")
    first_id = tabs[0][0]
    with TabbedContent(initial=initial or first_id, id=container_id):
        for tab_id, label, build_body in tabs:
            with TabPane(label, id=tab_id):
                yield build_body()


def remembered_tab(app: object, module_id: str, tabs: Sequence[tuple[str, str, TabBuilder]]) -> str:
    """The pane this module was last on, or its first pane.

    A remembered id that no longer exists (a pane was renamed or removed) falls back to
    the first pane instead of opening an empty strip.
    """
    valid = {tab_id for tab_id, _label, _build in tabs}
    default = tabs[0][0]
    try:
        from pentool.core.config import get_config

        remembered = (getattr(get_config(), "last_subtabs", None) or {}).get(module_id, "")
    except Exception as exc:  # noqa: BLE001 - config is optional at import time
        logger.debug("static_tabs: remembered pane for %s not read: %s", module_id, exc)
        return default
    if remembered in valid:
        return remembered
    if remembered:
        logger.debug("static_tabs: %s remembered unknown pane %r, using %s", module_id, remembered, default)
    return default


def remember_tab(app: object, module_id: str, tab_id: str, *, save: bool = True) -> None:
    """Store the active pane of *module_id* so the next run opens the same one."""
    try:
        from pentool.core.config import get_config

        config = get_config()
        current = dict(getattr(config, "last_subtabs", None) or {})
        if current.get(module_id) == tab_id:
            return
        current[module_id] = tab_id
        config.last_subtabs = current
        if save:
            config.save()
    except Exception as exc:  # noqa: BLE001 - remembering a pane must never break a screen
        logger.debug("static_tabs: could not remember pane %s for %s: %s", tab_id, module_id, exc)


"""`remembered_pane()` — the same memory for screens that build panes inline.

Settings and Recon build their TabPanes with nested `with` blocks, so the builder-based
`static_tabs()` does not fit. They still get the same behaviour: one function reads the
remembered pane, `remember_tab()` writes it. This keeps "the active sub-tab survives a
restart" identical across Utils, Settings and Recon.
"""


def remembered_pane(app: object, module_id: str, valid_ids: Sequence[str]) -> str:
    """The pane this module was last on, or the first valid one.

    Args:
        app: the running app (kept for symmetry with `remembered_tab`).
        module_id: key in `Config.last_subtabs` ("settings", "recon", …).
        valid_ids: pane ids that exist in this build, in strip order.
    """
    if not valid_ids:
        raise ValueError("remembered_pane() needs at least one pane id")
    default = valid_ids[0]
    try:
        from pentool.core.config import get_config

        remembered = (getattr(get_config(), "last_subtabs", None) or {}).get(module_id, "")
    except Exception as exc:  # noqa: BLE001 - config is optional
        logger.debug("remembered_pane: %s not read: %s", module_id, exc)
        return default
    if remembered in valid_ids:
        return remembered
    if remembered:
        logger.debug("remembered_pane: %s had %r, which no longer exists", module_id, remembered)
    return default
