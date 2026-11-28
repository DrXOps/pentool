"""CommentDialog — view/edit the comment of a proxy history request.

Now a `FormDialog` (step 7): the layout, focus, Enter/Escape and the per-field error line come
from the shared component, and this class only declares the field and maps the result back to a
plain string (its callers store the value, not a dict).
"""

from __future__ import annotations

from pentool.tui.dialogs.form_dialog import FormDialog, FormField


class CommentDialog(FormDialog):
    """Dialog: view/edit the comment for the currently-selected request."""

    def __init__(self, initial_comment: str = "") -> None:
        super().__init__(
            "Comment",
            [FormField("comment", "Comment", default=initial_comment, placeholder="Add comment...")],
            submit_label="Save",
        )

    def _result(self, values: dict) -> str:
        return values["comment"]
