"""Fallback shown in place of the Scanner module when the PRO package isn't installed.

Scanner (pentool/modules/scanner/, pentool/api/scanner_api.py,
pentool/tui/screens/scanner/) is a PRO-only module distributed separately —
see pentool.core.license.download_pro_package. A bare `pip install pentool`
does not include it, so pentool.tui.screens imports this instead and the
rest of the TUI (all FREE modules) still starts normally.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static


class ScannerUnavailableScreen(Widget):
    """Drop-in replacement for ScannerScreen when the PRO package is missing."""

    DEFAULT_CSS = """
    ScannerUnavailableScreen {
        align: center middle;
    }
    ScannerUnavailableScreen > Vertical {
        width: auto;
        height: auto;
        border: round $warning;
        padding: 2 4;
    }
    """

    def __init__(self, **kwargs) -> None:
        # ScannerScreen.__init__ accepts arbitrary **kwargs (e.g. id=...);
        # match that signature so app.py's ScannerScreen(id="screen-scanner")
        # works unchanged regardless of which class this name resolves to.
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🔒 Scanner is a PRO feature", markup=False)
            yield Static("")
            yield Static("Start a 14-day free trial (full PRO access):")
            yield Static("  pentool license trial")
            yield Static("")
            yield Static("Already have a key?")
            yield Static("  pentool license activate KEY")
            yield Static("")
            yield Static("Restart Pentool after activation.")
