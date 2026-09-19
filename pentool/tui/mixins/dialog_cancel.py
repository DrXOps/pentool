"""DialogCancelMixin — shared action_cancel for ModalScreen subclasses."""

from __future__ import annotations


class DialogCancelMixin:
    """Mixin: standard action_cancel dismiss(None) for ModalScreen."""

    def action_cancel(self) -> None:
        """Dismiss the modal and return None to the caller."""
        self.dismiss(None)  # type: ignore[attr-defined]
