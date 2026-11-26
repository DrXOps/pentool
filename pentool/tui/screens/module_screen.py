"""ModuleScreen — the base every module screen shares.

Why: the audit (docs/audit/2026-11-21-tui-report.md, E2/D10) found eight screens inheriting
different mixin sets, so each cross-cutting duty was re-implemented on the spot — six
copies of the header refresh, six `if/elif` chains for header actions, two incompatible
`reload_from_project` implementations, eleven screens reaching into `App`'s private
fields.

The base is deliberately small. It provides what *every* module needs — the app helpers,
one `header_action` dispatch, one notification entry point — and nothing else: mixins a
screen does not use stay out of its MRO, because an over-broad base is the same problem
in a different costume.

Screens with renameable tabs keep `BaseModuleScreen` as a second parent: tabs are a
separate concern and not every module has them.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from textual import on
from textual.widget import Widget

from pentool.core.logging import get_logger
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.widgets.content_panel import ContentPanel

logger = get_logger(__name__)


@runtime_checkable
class ProjectReloadable(Protocol):
    """Contract for screens that hold project data (structural, not a base class).

    A screen that owns a database handle implements all three:

    ``async reload_from_project(db_path: str)``
        Re-read everything from the newly opened project. Called right after the app
        switched its own storage; the screen must not switch the database itself.
    ``reset_for_new_project()``
        Drop in-memory state (rows, tables, selections) before a new project is opened.
    ``async close_storage()``
        Close the handle the screen holds. Called when a project is closed.

    Why a contract and not a defaulted base method: a default ``reload_from_project``
    that does nothing would silently keep showing the previous project's data — the
    exact failure mode (F-014) the audit found in two screens.
    """

    async def reload_from_project(self, db_path: str) -> None:  # pragma: no cover - contract
        raise NotImplementedError

    def reset_for_new_project(self) -> None:  # pragma: no cover - contract
        raise NotImplementedError

    async def close_storage(self) -> None:  # pragma: no cover - contract
        raise NotImplementedError


class ModuleScreen(AppMixin, Widget):
    """Base class for a top-level module screen.

    Subclasses declare :attr:`ACTIONS` — the mapping between the ids their
    ``header_spec()`` offers and the methods that run them. Keys must match the
    ``HeaderAction(action=...)`` ids, so a typo shows up in the debug log instead of a
    button that does nothing.
    """

    #: ``header action id → method name`` (no arguments, called on this screen).
    ACTIONS: dict[str, str] = {}

    #: Redraw the header after a mapped action ran.
    refresh_after_action: bool = True

    @on(ContentPanel.FormatToggleRequested)
    def on_panel_format_requested(self, event: ContentPanel.FormatToggleRequested) -> None:
        """The ✨ tool of a panel: beautify the body it shows.

        The panel draws this tool for every body panel, but no screen except Decoder had a
        handler (and that one was a no-op), so the only working "beautify" was a header
        button. One handler here makes the in-window tool real for all screens.
        """
        widget = getattr(event.panel, "content_widget", None)
        beautify = getattr(widget, "beautify_body", None)
        if beautify is None:
            self.notify_to_user("Nothing to format in this panel", severity="warning")
            return
        try:
            changed = bool(beautify())
        except Exception as exc:  # noqa: BLE001 - a formatting failure must not kill the screen
            logger.warning("format: beautify failed", exc_info=True)
            self.notify_to_user(f"Format failed: {exc}", severity="error")
            return
        if changed:
            self.notify_to_user("Formatted")
        else:
            self.notify_to_user("Nothing to beautify — no valid JSON/XML body found", severity="warning")

    def header_action(self, action_id: str) -> None:
        """Run the method registered for this header action.

        One dispatch for the whole layer: the `if action_id == …` chains that grew in
        individual screens drifted (different refresh rules, different logging). A
        screen with genuinely special behaviour overrides this method and delegates to
        the mapped methods — it does not grow a chain again (guard:
        ``tests/unit/tui/test_header_action_dispatch.py``).
        """
        method_name = self.ACTIONS.get(action_id)
        if method_name is None:
            logger.debug("%s: header action %r is not mapped", type(self).__name__, action_id)
            return
        handler: Callable[[], Any] | None = getattr(self, method_name, None)
        if handler is None:
            logger.warning(
                "%s: header action %r maps to missing method %r",
                type(self).__name__,
                action_id,
                method_name,
            )
            return
        handler()
        if self.refresh_after_action:
            self.refresh_header()

    def notify_to_user(self, message: str, severity: str = "information", timeout: float | None = None) -> None:
        """Show a notification through the app, tolerating a screen without one."""
        notify = getattr(getattr(self, "app", None), "notify", None)
        if callable(notify):
            notify(message, severity=severity, timeout=timeout)
