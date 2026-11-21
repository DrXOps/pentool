"""HintBarBase — base class for the bottom hint strips.

Subclasses override ``_build_markup()`` and call ``refresh()``.
Deliberately minimal: compose + set_text, no reactive.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.logging import get_logger

_log = get_logger(__name__)

_HINT_CSS = (Path(__file__).parent / "hintbar_base.tcss").read_text(encoding="utf-8")


class HintBarBase(Widget):
    """One-line hint strip — the subclass supplies ``_build_markup()``."""

    DEFAULT_CSS = _HINT_CSS

    def compose(self) -> ComposeResult:
        yield Static("", id="hint-content")

    def set_text(self, markup: str) -> None:
        """Update the displayed text (Rich‑markup)."""
        _log.info("HintBar set_text: %s", markup[:80])
        try:
            self.query_one("#hint-content", Static).update(markup)
        except NoMatches as exc:
            # The hint strip is left over from the previous module — so it teaches
            # keys that do not exist on this screen.
            _log.error("HintBar set_text FAILED: %s", exc)
