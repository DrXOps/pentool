"""Comparer screen — side-by-side diff of two texts."""

from __future__ import annotations

import os
import re
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static, TextArea

from pentool.tui.widgets.content_panel import ContentPanel

from pentool.core.logging import get_logger
from pentool.tui.hotkeys.defaults import COMPARER_BINDINGS
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")


class ComparerScreen(Widget):
    """Side-by-side text diff with difference highlighting."""

    DEFAULT_CSS = _CSS

    BINDINGS = COMPARER_BINDINGS

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_result = None

    def compose(self) -> ComposeResult:
        # ── Toolbar ────────────────────────────────────────────────────────────
        with Horizontal(id="cmp-toolbar"):
            yield ToolbarButton("⇄ Compare",     "btn-cmp-compare")
            yield Static(" │ ", classes="cmp-sep")
            yield ToolbarButton("↑ Load Left",   "btn-cmp-load-left")
            yield Static(" │ ", classes="cmp-sep")
            yield ToolbarButton("↑ Load Right",  "btn-cmp-load-right")
            yield Static(" │ ", classes="cmp-sep")
            yield ToolbarButton("📋 Copy Diff",   "btn-cmp-copy")
            yield Static(" │ ", classes="cmp-sep")
            yield ToolbarButton("🗑 Clear",       "btn-cmp-clear")

        # ── Stat bar ───────────────────────────────────────────────────────────
        with Horizontal(id="cmp-stat-bar"):
            yield Static("[dim]— Press Compare or Ctrl+Enter to diff —[/dim]",
                         id="cmp-stats", markup=True)

        # ── Two TextAreas via ContentPanel ──────────────────────────────────────
        with Horizontal(id="cmp-edit-area"):
            with Vertical(id="cmp-left-col"):
                yield ContentPanel("Left", widget_type="textarea", buttons=["copy", "paste"],
                                   id="cmp-left-panel")
            yield ResizeHandle("cmp-left-col", "cmp-right-col", id="cmp-resize-h")
            with Vertical(id="cmp-right-col"):
                yield ContentPanel("Right", widget_type="textarea", buttons=["copy", "paste"],
                                   id="cmp-right-panel")

        yield ResizeHandle("cmp-edit-area", "cmp-diff-area", vertical=True,
                           id="cmp-resize-v")

        # ── Diff output ────────────────────────────────────────────────────────
        with Vertical(id="cmp-diff-area"):
            yield Static("Diff", id="cmp-diff-label", classes="cmp-col-label")
            yield ContentPanel("", widget_type="richlog", wrap=False, max_lines=2000, buttons=["copy"])

        
    # ── ContentPanel handlers ─────────────────────────────────────────────────

    @on(ContentPanel.CopyRequested)
    def on_cmp_copy(self, event: ContentPanel.CopyRequested) -> None:
        """Копирование из ContentPanel в буфер."""
        text = event.selection or event.text
        if text:
            from pentool.utils.copy_as import copy_to_clipboard
            if copy_to_clipboard(text):
                self.app.notify("Copied", timeout=2)

    @on(ContentPanel.PasteRequested)
    def on_cmp_paste(self, event: ContentPanel.PasteRequested) -> None:
        """Вставка в ContentPanel из буфера обмена."""
        from pentool.utils.copy_as import paste_from_clipboard
        clipboard = paste_from_clipboard()
        if clipboard:
            panel = event.panel
            w = panel.content_widget
            if isinstance(w, TextArea):
                sel = w.selection
                is_selected = (
                    sel is not None
                    and sel.start != sel.end
                )
                if is_selected:
                    start_row, start_col = sel.start
                    end_row, end_col = sel.end
                    lines = w.text.splitlines(keepends=True)
                    if start_row == end_row:
                        line = lines[start_row]
                        lines[start_row] = line[:start_col] + clipboard + line[end_col:]
                    else:
                        lines[start_row] = lines[start_row][:start_col] + clipboard
                        lines = lines[:start_row + 1] + lines[end_row:]
                        if end_row < len(lines):
                            lines[end_row] = lines[end_row][end_col:]
                        else:
                            lines.append('')
                    w.load_text(''.join(lines))
                else:
                    w.load_text(clipboard)
        else:
            self.app.notify("Nothing in clipboard", severity="warning")

    # ── Toolbar ───────────────────────────────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-cmp-compare")
    def on_btn_cmp_compare(self, _: ToolbarButton.Pressed) -> None:
        self.action_compare()

    @on(ToolbarButton.Pressed, "#btn-cmp-load-left")
    def on_btn_cmp_load_left(self, _: ToolbarButton.Pressed) -> None:
        self._load_from_file("left")

    @on(ToolbarButton.Pressed, "#btn-cmp-load-right")
    def on_btn_cmp_load_right(self, _: ToolbarButton.Pressed) -> None:
        self._load_from_file("right")

    @on(ToolbarButton.Pressed, "#btn-cmp-copy")
    def on_btn_cmp_copy(self, _: ToolbarButton.Pressed) -> None:
        self._copy_diff()

    @on(ToolbarButton.Pressed, "#btn-cmp-clear")
    def on_btn_cmp_clear(self, _: ToolbarButton.Pressed) -> None:
        self.action_clear()

    def _load_from_file(self, side: str) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path or not os.path.exists(path):
                return
            try:
                text = Path(path).read_text(encoding="utf-8", errors="replace")
                panel_id = f"cmp-{side}-panel"
                panel = self.query_one(f"#{panel_id}", ContentPanel)
                w = panel.content_widget
                if isinstance(w, TextArea):
                    w.load_text(text)
                panel.set_title(os.path.basename(path))
            except Exception as exc:
                self.err(exc, "Load failed")

        self.app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                title=f"Load {side.capitalize()}",
            ),
            _on_path,
        )

    def _copy_diff(self) -> None:
        try:
            from pentool.utils.copy_as import copy_to_clipboard
            if self._last_result is None:
                self.app.notify("Run Compare first", severity="warning")
                return
            text = self._last_result.rich_text()
            # Strip markup before copying
            plain = re.sub(r"\[/?[^\]]+\]", "", text)
            if copy_to_clipboard(plain):
                self.app.notify("Diff copied", timeout=2)
        except Exception as exc:
            self.err(exc, "Copy failed")

    # ── Compare ───────────────────────────────────────────────────────────────

    def action_compare(self) -> None:
        """Run the comparison and display the result."""
        try:
            from pentool.api.comparer_api import compare
            left  = self.query_one("#cmp-left-panel", ContentPanel).content_widget.text
            right = self.query_one("#cmp-right-panel", ContentPanel).content_widget.text
            result = compare(left, right)
            self._last_result = result
            self._render_result(result)
        except Exception as exc:
            self.err(exc, "Compare error")

    def _render_result(self, result) -> None:
        """Render diff to the log and statistics to the stat-bar."""
        try:
            # Stat bar
            s = result.stats
            stat_text = (
                f"[green]+{s.added_lines} added[/green]   "
                f"[red]-{s.removed_lines} removed[/red]   "
                f"[yellow]~{s.changed_lines} changed[/yellow]   "
                f"[dim]={s.equal_lines} equal[/dim]   "
                f"[cyan]Similarity: {s.similarity_pct}%[/cyan]   "
                f"[dim]Left: {s.total_left} lines  Right: {s.total_right} lines[/dim]"
            )
            self.query_one("#cmp-stats", Static).update(stat_text)

            # Diff log
            log = self.query_one("#cmp-diff-area", ContentPanel).content_widget
            log.clear()
            for dl in result.lines:
                if dl.tag == "equal":
                    # Show only a few context lines around changes
                    log.write(f"[dim]  {dl.left[:120]}[/dim]")
                elif dl.tag == "insert":
                    log.write(f"[green]+ {dl.right[:120]}[/green]")
                elif dl.tag == "delete":
                    log.write(f"[red]- {dl.left[:120]}[/red]")
                elif dl.tag == "replace":
                    log.write(f"[red]- {dl.left[:120]}[/red]")
                    log.write(f"[green]+ {dl.right[:120]}[/green]")
        except Exception as exc:
            logger.debug("_render_result: %s", exc)

    # ── Clear ─────────────────────────────────────────────────────────────────

    def action_clear(self) -> None:
        try:
            for panel_id in ("cmp-left-panel", "cmp-right-panel"):
                panel = self.query_one(f"#{panel_id}", ContentPanel)
                w = panel.content_widget
                if isinstance(w, TextArea):
                    w.load_text("")
                panel.set_title({"cmp-left-panel": "Left", "cmp-right-panel": "Right"}[panel_id])
            self.query_one("#cmp-diff-area", ContentPanel).clear_content()
            self.query_one("#cmp-stats",    Static).update(
                "[dim]— Press Compare or Ctrl+Enter to diff —[/dim]"
            )
            self._last_result = None
        except Exception as exc:
            logger.debug("action_clear: %s", exc)

    # ── Public API (loading from other modules) ───────────────────────────────

    def load_left(self, text: str, label: str = "Left") -> None:
        try:
            panel = self.query_one("#cmp-left-panel", ContentPanel)
            w = panel.content_widget
            if isinstance(w, TextArea):
                w.load_text(text)
            panel.set_title(label)
        except Exception as exc:
            logger.debug("load_left: %s", exc)

    def load_right(self, text: str, label: str = "Right") -> None:
        try:
            panel = self.query_one("#cmp-right-panel", ContentPanel)
            w = panel.content_widget
            if isinstance(w, TextArea):
                w.load_text(text)
            panel.set_title(label)
        except Exception as exc:
            logger.debug("load_right: %s", exc)

    def load_smart(self, text: str, label: str = "") -> None:
        try:
            left_panel = self.query_one("#cmp-left-panel", ContentPanel)
            left_text = left_panel.content_widget.text
            if not left_text.strip():
                self.load_left(text, label or "Left")
            else:
                self.load_right(text, label or "Right")
        except Exception as exc:
            logger.debug("load_smart: %s", exc)
