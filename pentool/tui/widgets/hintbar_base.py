"""HintBarBase — базовый класс для нижних строк подсказок.

Наследники переопределяют ``_build_markup()`` и вызывают ``refresh()``.
Достаточно минимально: compose + set_text, без reactive.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

_HINT_CSS = """
HintBarBase {
    height: 1;
    dock: none;
    background: $surface;
    padding: 0 1;
    color: $text-muted;
}
"""


class HintBarBase(Widget):
    """One-line hint strip —наследник задаёт ``_build_markup()``."""

    DEFAULT_CSS = _HINT_CSS

    def compose(self) -> ComposeResult:
        yield Static("", id="hint-content")

    def set_text(self, markup: str) -> None:
        """Update the displayed text (Rich‑markup)."""
        from pentool.core.logging import get_logger
        _log = get_logger(__name__)
        _log.info("HintBar set_text: %s", markup[:80])
        try:
            self.query_one("#hint-content", Static).update(markup)
        except Exception as exc:
            _log.error("HintBar set_text FAILED: %s", exc)