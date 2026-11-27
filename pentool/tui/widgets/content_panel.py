"""ContentPanel — universal block for RichLog/TextArea with a toolbar.

Replaces hand-rolled RichLog and TextArea with buttons across all screens:
- RichLog: scan-log, recon-log, feed-log, ws-msg-log, detail-log,
  dec-steps-log, cmp-diff-log, seq-analysis-log, diff-panel-log, lightpanda-body
- TextArea: editor-area, viewer-area, http-body, dec-input/dec-output,
  cmp-left/cmp-right, scope-area, seq-token-area
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from textual import on
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static, TextArea

from pentool.core.logging import get_logger
from pentool.tui.markup import esc
from pentool.tui.mixins.notify import NotifyMixin
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ContentPanel(NotifyMixin, Widget):
    """Container block: RichLog or TextArea + button toolbar in the header."""

    class CopyRequested(Message):
        """Request to copy the panel content to the clipboard."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, panel: "ContentPanel", text: str, selection: str | None = None) -> None:
            self.panel = panel
            self.text = text
            self.selection = selection  # selected text, None = copy everything
            super().__init__()

        @property
        def control(self) -> "ContentPanel":
            return self.panel

    class PasteRequested(Message):
        """Request to paste from the clipboard."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, panel: "ContentPanel") -> None:
            self.panel = panel
            super().__init__()

        @property
        def control(self) -> "ContentPanel":
            return self.panel

    class FormatToggleRequested(Message):
        """Request to toggle between raw and formatted."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, panel: "ContentPanel") -> None:
            self.panel = panel
            super().__init__()

        @property
        def control(self) -> "ContentPanel":
            return self.panel

    DEFAULT_CSS = (Path(__file__).parent / "content_panel.tcss").read_text(encoding="utf-8")

    # ── Panel icons ──────────────────────────────────────────────────────
    # The sets differ in font coverage: under WSL in Kitty some glyphs
    # (`⎙ ⎘ ⇄ ↩ ⬇`) are not drawn at all, while `✕` exists almost everywhere.
    # That is why the set is picked in Settings → Interface instead of being
    # hardcoded in a single line.
    ICON_SETS: ClassVar[dict[str, dict[str, str]]] = {
        "unicode": {
            "copy": "❐",
            "paste": "➔",
            "clear": "✕",
            "format": "✎",
            "special": "⏎",
            "wrap": "↔",
            "autoscroll": "⬇",
        },
        "ascii": {
            "copy": "[c]",
            "paste": "[p]",
            "clear": "[x]",
            "format": "[f]",
            "special": "[sp]",
            "wrap": "[w]",
            "autoscroll": "[end]",
        },
        "emoji": {
            "copy": "📋",
            "paste": "📥",
            "clear": "🗑",
            "format": "✨",
            "special": "⏎",
            "wrap": "↔",
            "autoscroll": "⬇",
        },
    }

    BUTTON_TOOLTIPS: ClassVar[dict[str, str]] = {
        "copy": "Copy to clipboard",
        "paste": "Paste from clipboard",
        "clear": "Clear this panel",
        "format": "Format / beautify",
        "special": "Insert special characters",
        "wrap": "Toggle line wrap",
        "autoscroll": "Scroll to the end",
    }

    BUTTON_SCOPE: ClassVar[list[str]] = ["copy"]

    #: Panel purpose → button set. One place decides which actions a panel offers,
    #: so a read-only viewer cannot accidentally get `clear` and an editor cannot
    #: lose `format`. Screens pass `role="..."` instead of listing buttons.
    ROLES: ClassVar[dict[str, tuple[str, ...]]] = {
        # Editable request/response text (Repeater editor, Intercept panel).
        "request-editable": ("copy", "paste", "clear", "special", "format"),
        "request-editable-plain": ("copy", "paste", "clear"),
        "request-with-format": ("copy", "paste", "format", "clear"),
        # Side-by-side comparison inputs (Comparer Left/Right).
        "compare-input": ("copy", "paste"),
        # Read-only text viewer (decoded output, HTTP views, details).
        "text-readonly": ("copy",),
        # Append-only journal: copying and clearing are both meaningful.
        "log": ("copy", "clear"),
        # Diff output: read and copy, nothing to clear or format.
        "diff": ("copy",),
        # Free-form editable text with copy/paste only.
        "text-editable": ("copy", "paste"),
    }

    @classmethod
    def button_label(cls, key: str) -> str:
        """Button icon for the icon set currently chosen in settings."""
        icon_set = "unicode"
        try:
            from pentool.core.config import get_config

            icon_set = getattr(get_config(), "panel_icons", "unicode") or "unicode"
        except Exception:
            logger.debug("content_panel: icon set not read, using unicode", exc_info=True)
            icon_set = "unicode"
        labels = cls.ICON_SETS.get(icon_set) or cls.ICON_SETS["unicode"]
        return labels.get(key, key)

    @classmethod
    def tooltips_enabled(cls) -> bool:
        try:
            from pentool.core.config import get_config

            return bool(getattr(get_config(), "tooltips_enabled", True))
        except Exception:
            logger.debug("content_panel: tooltips setting not read, default on", exc_info=True)
            return True

    _wrap_state: reactive[bool] = reactive(True)

    def __init__(
        self,
        title: str = "",
        *,
        widget_type: Literal["richlog", "textarea"] = "richlog",
        textarea_read_only: bool = False,
        textarea_language: str | None = None,
        textarea_soft_wrap: bool = True,
        wrap: bool = True,
        max_lines: int = 2000,
        initial_text: str = "",
        buttons: list[str] | None = None,
        role: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        if role is not None:
            if role not in self.ROLES:
                raise ValueError(f"unknown ContentPanel role {role!r}; known: {sorted(self.ROLES)}")
            buttons = list(self.ROLES[role])
        elif buttons is None:
            buttons = list(self.BUTTON_SCOPE)
        else:
            # Escape hatch for plugins with a custom set; the repository itself
            # always passes a role (guarded by tests/unit/tui/test_panel_roles.py).
            logger.debug("content_panel: explicit buttons= used instead of a role")
        self._panel_title = title
        self._widget_type = widget_type
        self._textarea_read_only = textarea_read_only
        self._textarea_language = textarea_language
        self._textarea_soft_wrap = textarea_soft_wrap
        self._wrap = wrap
        self._max_lines = max_lines
        self._initial_text = initial_text
        self._buttons = list(buttons)
        self._wrap_state = wrap

    def compose(self) -> ComposeResult:
        with Horizontal(classes="cp-title panel-title"):
            yield Static(esc(self.display_title))
            tip_on = self.tooltips_enabled()
            for bk in self._buttons:
                lbl = self.button_label(bk)
                tip = self.BUTTON_TOOLTIPS.get(bk) if tip_on else None
                if bk == "wrap":
                    yield ToolbarButton(
                        lbl if self._wrap_state else self.button_label("wrap"),
                        f"cp-btn-{bk}",
                        classes="variant-success" if self._wrap_state else "variant-warning",
                        tooltip=tip,
                    )
                else:
                    yield ToolbarButton(lbl, f"cp-btn-{bk}", tooltip=tip)
        with Vertical(id="cp-body"):
            if self._widget_type == "textarea":
                yield TextArea(
                    self._initial_text,
                    id="cp-body-widget",
                    read_only=self._textarea_read_only,
                    language=self._textarea_language,
                    soft_wrap=self._textarea_soft_wrap,
                )
            else:
                yield RichLog(
                    id="cp-body-widget",
                    highlight=True,
                    markup=True,
                    wrap=self._wrap,
                    max_lines=self._max_lines,
                )

    @property
    def content_widget(self) -> RichLog | TextArea:
        return self.query_one("#cp-body-widget")

    @property
    def content_mounted(self) -> bool:
        """True once the body widget exists in the DOM.

        A panel is mounted before its children: ``req_panel.mount(editor)``
        returns while ``#cp-body-widget`` is still being composed. Code that
        loads text right after mounting must ask this first — ``load_raw``
        used to swallow the resulting ``NoMatches`` and leave the editor empty
        while its own ``_raw_full`` said the request was loaded.
        """
        return bool(len(self.query("#cp-body-widget")))

    def get_text(self) -> str:
        w = self.content_widget
        if isinstance(w, TextArea):
            return w.text
        try:
            lines: list[str] = []
            for item in getattr(w, "lines", None) or []:
                t = getattr(item, "text", str(item))
                lines.append(str(t))
            return "\n".join(lines)
        except Exception:
            return ""

    def get_selected_text(self) -> str | None:
        """Return the selected text from the TextArea, or None if there is no selection."""
        w = self.content_widget
        if not isinstance(w, TextArea):
            return None
        sel = w.selection
        if sel is None:
            return None
        # selection.start/end are (row, col) tuples
        if sel.start == sel.end:
            return None
        try:
            text = w.text
            lines = text.splitlines(keepends=True)

            def _flat(pos: tuple[int, int]) -> int:
                row, col = pos
                idx = sum(len(lines[r]) for r in range(row))
                return idx + col

            return text[_flat(sel.start) : _flat(sel.end)]
        except Exception:
            return None

    def clear_content(self) -> None:
        w = self.content_widget
        if isinstance(w, TextArea):
            w.load_text("")
        else:
            w.clear()

    @property
    def display_title(self) -> str:
        """Title as drawn in the header: ``┌─ Request ─`` (cards plan, step 4).

        The frame is added here rather than by every caller so a dynamic title
        keeps working: `set_title` stores the bare text and only the rendering
        gets the brackets, e.g. ``┌─ Response · 200 OK · 1.2 KB ─``. The title
        itself is not re-cased — the Comparer puts file names in it.
        """
        return f"┌─ {self._panel_title} ─" if self._panel_title else ""

    def set_title(self, title: str) -> None:
        """Update the panel title (the Static inside .cp-title).

        The title is always text, never markup: file names end up in it
        (they may contain ``[``) as do response language tags in square
        brackets (``[html]``, ``[json]``) — without escaping Rich silently
        swallows them.
        """
        self._panel_title = title
        try:
            self.query_one(".cp-title > Static", Static).update(esc(self.display_title))
        except NoMatches as exc:
            # The title on screen lags behind what is actually loaded into the
            # panel: two panels side by side then look identical.
            logger.debug("content panel: title %r not shown: %s", title, exc)

    def write_to_log(self, text: str) -> None:
        if self._widget_type == "richlog":
            self.content_widget.write(text)

    @on(ToolbarButton.Pressed)
    def on_cp_toolbar_button(self, event: ToolbarButton.Pressed) -> None:
        btn = event.button
        btn_id = btn.id or ""

        if btn_id == "cp-btn-copy":
            sel_text = self.get_selected_text()
            if sel_text is not None:
                self.post_message(self.CopyRequested(self, sel_text, selection=sel_text))
            else:
                self.post_message(self.CopyRequested(self, self.get_text()))
        elif btn_id == "cp-btn-paste":
            self.post_message(self.PasteRequested(self))
        elif btn_id == "cp-btn-clear":
            self.clear_content()
        elif btn_id == "cp-btn-format":
            self.post_message(self.FormatToggleRequested(self))
        elif btn_id == "cp-btn-wrap":
            w = self.content_widget
            if isinstance(w, RichLog):
                self._wrap_state = not self._wrap_state
                w.wrap = self._wrap_state
                btn.label = self.button_label("wrap") if self._wrap_state else "╌"
                btn.add_class(f"variant-{'success' if self._wrap_state else 'warning'}")
                btn.remove_class(f"variant-{'warning' if self._wrap_state else 'success'}")
