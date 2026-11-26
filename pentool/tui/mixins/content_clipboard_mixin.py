"""ContentClipboardMixin — universal Copy/Paste for ContentPanel.

Handlers are declared by naming convention (``on_content_panel_copy_requested``)
rather than with ``@on(...)``. Textual collects ``@on`` handlers in
``__init_subclass__`` of the *concrete* class only (it walks ``class_dict``,
not the MRO — see ``textual/message_pump.py``), so an ``@on`` inside a plain
mixin is never registered and the handler silently never fires. Handlers
matched by name *are* resolved over the MRO, which is exactly what a mixin
needs. See docs/DECISIONS.md, ADR-3.

Screens may override ``_paste_text_to_panel`` for custom insertion.
"""

from __future__ import annotations

from pentool.tui.widgets.content_panel import ContentPanel


class ContentClipboardMixin:
    """Copy/Paste handlers for every ``ContentPanel`` on the screen.

    Copy — copies the current selection, or the whole content when nothing is
    selected. Paste — replaces the selection, or inserts at the cursor; a
    RichLog panel appends the clipboard text to its log.
    """

    def on_content_panel_copy_requested(self, event: ContentPanel.CopyRequested) -> None:
        """Copy ContentPanel text to the clipboard."""
        text = event.selection or event.text
        if not text:
            return
        from pentool.utils.copy_as import copy_to_clipboard

        if copy_to_clipboard(text):
            self._notify_clipboard("Copied")
        else:
            self._notify_clipboard("Copy failed — no clipboard backend", severity="warning")

    def on_content_panel_paste_requested(self, event: ContentPanel.PasteRequested) -> None:
        """Paste clipboard text into the ContentPanel that asked for it."""
        from pentool.utils.copy_as import paste_from_clipboard

        text = paste_from_clipboard()
        if not text:
            self._notify_clipboard("Nothing in clipboard", severity="warning")
            return
        self._paste_text_to_panel(event.panel, text)

    # ── Overridable ───────────────────────────────────────────────────────

    def _paste_text_to_panel(self, panel: ContentPanel, text: str) -> None:
        """Insert *text* into *panel*, replacing any active selection."""
        from rich.markup import escape
        from textual.widgets import RichLog, TextArea

        widget = panel.content_widget
        if isinstance(widget, TextArea):
            selection = widget.selection
            if selection is not None and selection.start != selection.end:
                widget.replace(text, selection.start, selection.end)
            else:
                widget.insert(text)
        elif isinstance(widget, RichLog):
            widget.write(escape(text))
        else:  # pragma: no cover — ContentPanel only composes the two above
            return
        self._notify_clipboard("Pasted")

    def _notify_clipboard(self, message: str, *, severity: str = "information") -> None:
        """Show a toast; a screen mounted without an App must not raise."""
        try:
            self.app.notify(message, severity=severity, timeout=2)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — notify is best-effort by design
            return
