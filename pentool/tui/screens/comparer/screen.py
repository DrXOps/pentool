"""Comparer screen — side-by-side diff of two texts."""

from __future__ import annotations

import os
import re
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static, TextArea

from pentool.core.logging import get_logger
from pentool.tui.hotkeys.defaults import COMPARER_BINDINGS
from pentool.tui.markup import esc
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.toolbar import Toolbar
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")


class ComparerScreen(ContentClipboardMixin, AppMixin, Widget):
    """Side-by-side text diff with difference highlighting."""

    DEFAULT_CSS = _CSS

    BINDINGS = COMPARER_BINDINGS

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_result = None

    def compose(self) -> ComposeResult:
        # ── Toolbar ────────────────────────────────────────────────────────────
        yield Toolbar(
            ToolbarButton("⇄ Compare", "btn-cmp-compare"),
            ToolbarButton("↑ Load Left", "btn-cmp-load-left"),
            ToolbarButton("↑ Load Right", "btn-cmp-load-right"),
            ToolbarButton("📋 Copy Diff", "btn-cmp-copy"),
            ToolbarButton("🗑 Clear", "btn-cmp-clear"),
        )

        # ── Stat bar ───────────────────────────────────────────────────────────
        with Horizontal(id="cmp-stat-bar"):
            yield Static("[dim]— Press Compare or Ctrl+Enter to diff —[/dim]", id="cmp-stats", markup=True)

        # ── Two TextAreas via ContentPanel ──────────────────────────────────────
        with Horizontal(id="cmp-edit-area"):
            with Vertical(id="cmp-left-col"):
                yield ContentPanel(
                    "Left",
                    widget_type="textarea",
                    buttons=["copy", "paste"],
                    id="cmp-left-panel",
                    classes="card",
                )
            yield ResizeHandle("cmp-left-col", "cmp-right-col", id="cmp-resize-h")
            with Vertical(id="cmp-right-col"):
                yield ContentPanel(
                    "Right",
                    widget_type="textarea",
                    buttons=["copy", "paste"],
                    id="cmp-right-panel",
                    classes="card",
                )

        yield ResizeHandle("cmp-edit-area", "cmp-diff-area", vertical=True, id="cmp-resize-v")

        # ── Diff output ────────────────────────────────────────────────────────
        # Панель дифа живёт внутри #cmp-diff-area и носит свой id: два узла с
        # одним id делают query_one("#cmp-diff-area", ContentPanel) исключением
        # WrongType, а не находкой.
        with Vertical(id="cmp-diff-area"):
            yield ContentPanel(
                "Diff",
                widget_type="richlog",
                wrap=False,
                max_lines=2000,
                buttons=["copy"],
                id="cmp-diff-panel",
                classes="card",
            )

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

            left = self.query_one("#cmp-left-panel", ContentPanel).content_widget.text
            right = self.query_one("#cmp-right-panel", ContentPanel).content_widget.text
            result = compare(left, right)
            self._last_result = result
            self._render_result(result)
        except NoMatches as exc:
            # Панели сравнения нет в дереве (экран ещё собирается) — читать
            # нечего, и Ctrl+Enter ничего не сделает.
            logger.debug("comparer: panel not mounted for compare: %s", exc)
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
            log = self.query_one("#cmp-diff-panel", ContentPanel).content_widget
            log.clear()
            for dl in result.lines:
                if dl.tag == "equal":
                    # Show only a few context lines around changes
                    log.write(f"[dim]  {esc(dl.left[:120])}[/dim]")
                elif dl.tag == "insert":
                    log.write(f"[green]+ {esc(dl.right[:120])}[/green]")
                elif dl.tag == "delete":
                    log.write(f"[red]- {esc(dl.left[:120])}[/red]")
                elif dl.tag == "replace":
                    log.write(f"[red]- {esc(dl.left[:120])}[/red]")
                    log.write(f"[green]+ {esc(dl.right[:120])}[/green]")
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
            self.query_one("#cmp-diff-panel", ContentPanel).clear_content()
            self.query_one("#cmp-stats", Static).update("[dim]— Press Compare or Ctrl+Enter to diff —[/dim]")
            self._last_result = None
        except NoMatches as exc:
            # Очистка не дошла до всех панелей: на экране остался прежний diff,
            # хотя кнопка нажата. Панели нет в дереве.
            logger.debug("comparer: panel not mounted for clear: %s", exc)

    # ── Public API (loading from other modules) ───────────────────────────────

    def load_left(self, text: str, label: str = "Left") -> None:
        try:
            panel = self.query_one("#cmp-left-panel", ContentPanel)
            w = panel.content_widget
            if isinstance(w, TextArea):
                w.load_text(text)
            panel.set_title(label)
        except Exception:
            # Текст не попал в левую панель: сравнивать нечего, а пользователь
            # считает, что данные загружены.
            logger.warning("load_left: text not shown", exc_info=True)

    def load_right(self, text: str, label: str = "Right") -> None:
        try:
            panel = self.query_one("#cmp-right-panel", ContentPanel)
            w = panel.content_widget
            if isinstance(w, TextArea):
                w.load_text(text)
            panel.set_title(label)
        except Exception:
            # Текст не попал в правую панель — то же, что и слева.
            logger.warning("load_right: text not shown", exc_info=True)

    def load_smart(self, text: str, label: str = "") -> None:
        try:
            left_panel = self.query_one("#cmp-left-panel", ContentPanel)
            left_text = left_panel.content_widget.text
            if not left_text.strip():
                self.load_left(text, label or "Left")
            else:
                self.load_right(text, label or "Right")
        except Exception:
            # Не удалось даже определить, свободна ли левая панель: выбор стороны
            # для сравнения сделан наугад.
            logger.warning("load_smart: side not resolved", exc_info=True)
