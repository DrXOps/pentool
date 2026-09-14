"""BaseDialog — shared base class for all ModalScreen dialogs in pentool.

All dialogs should inherit BaseDialog (which itself inherits DialogCancelMixin
+ ModalScreen) to receive standard sizing, centering, and the Escape→cancel
binding.  CSS lives in a separate .tcss file; subclasses only override
DEFAULT_CSS if they need additional screen-level rules (rare — most dialogs
only need per-id rules in their own .tcss file).
"""

from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.screen import ModalScreen

from pentool.tui.mixins.dialog_cancel import DialogCancelMixin


_BASE_DIR = Path(__file__).parent


class BaseDialog(DialogCancelMixin, ModalScreen):
    """Standard dialog base: centred, sized, Escape-cancellable.

    Subclasses inherit:
      - ``DEFAULT_CSS`` (from ``base_dialog.tcss``)
      - ``action_cancel() → dismiss(None)`` (from DialogCancelMixin)
      - ``BINDINGS`` with Escape → cancel
    """

    DEFAULT_CSS = (_BASE_DIR / "base_dialog.tcss").read_text(encoding="utf-8")
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]