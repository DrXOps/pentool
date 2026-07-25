"""DialogCancelMixin — shared action_cancel for ModalScreen subclasses."""

from __future__ import annotations


class DialogCancelMixin:
    """Mixin that provides a standard action_cancel for ModalScreen subclasses.

    Usage::

        class MyDialog(DialogCancelMixin, ModalScreen[MyResult | None]):
            BINDINGS = [Binding("escape", "cancel", "Cancel")]
            ...

    The mixin calls ``self.dismiss(None)``, which is the conventional
    return value for all cancellable dialogs in this project.
    """

    def action_cancel(self) -> None:
        """Dismiss the modal and return None to the caller."""
        self.dismiss(None)  # type: ignore[attr-defined]
