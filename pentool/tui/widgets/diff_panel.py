"""DiffPanel — side/bottom-agnostic panel that shows a unified diff between
two text snapshots (e.g. Repeater's "last sent" request vs. the current
editor content). Reuses the same compare() engine as the Comparer module so
the diff wording/coloring stays consistent across the app.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog, Static

from pentool.core.logging import get_logger

_CSS = (Path(__file__).parent / "diff_panel.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)


class DiffPanel(Widget):
    """Collapsible panel rendering a unified-style diff of two texts."""

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        yield Static("Diff vs. last sent", id="diff-panel-title")
        yield RichLog(id="diff-panel-log", highlight=True, markup=True, wrap=False, max_lines=2000)

    def show_diff(self, old_text: str, new_text: str) -> None:
        """Render a diff of old_text (last sent) -> new_text (current)."""
        try:
            from pentool.api.comparer_api import compare
            result = compare(old_text or "", new_text or "")
            log = self.query_one("#diff-panel-log", RichLog)
            log.clear()
            for dl in result.lines:
                if dl.tag == "equal":
                    log.write(f"[dim]  {dl.left[:200]}[/dim]")
                elif dl.tag == "insert":
                    log.write(f"[green]+ {dl.right[:200]}[/green]")
                elif dl.tag == "delete":
                    log.write(f"[red]- {dl.left[:200]}[/red]")
                elif dl.tag == "replace":
                    log.write(f"[red]- {dl.left[:200]}[/red]")
                    log.write(f"[green]+ {dl.right[:200]}[/green]")
            s = result.stats
            self.query_one("#diff-panel-title", Static).update(
                f"Diff vs. last sent  [green]+{s.added_lines}[/green] "
                f"[red]-{s.removed_lines}[/red] [yellow]~{s.changed_lines}[/yellow]"
            )
        except Exception as exc:
            logger.debug("DiffPanel.show_diff: %s", exc)

    def clear(self) -> None:
        try:
            self.query_one("#diff-panel-log", RichLog).clear()
            self.query_one("#diff-panel-title", Static).update("Diff vs. last sent")
        except Exception:
            pass

    def toggle(self) -> bool:
        """Toggle visibility. Returns the new visible state."""
        visible = "-visible" in self.classes
        if visible:
            self.remove_class("-visible")
        else:
            self.add_class("-visible")
        return not visible
