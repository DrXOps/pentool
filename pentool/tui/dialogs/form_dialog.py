"""FormDialog — one declarative dialog for the simple forms of the TUI (step 7).

Sixteen hand-written dialogs each repeated the same layout: a title, one or more inputs, a
Save/Cancel row, and — in about half of them — no validation at all: an empty field dismissed
the dialog with `""`, a non-numeric thread count crashed the handler, and the error message (if
any) was a toast far from the field that caused it.

`FormDialog` takes a list of `FormField` and owns the whole cycle: layout, focus, per-field
errors under the field, Enter submits, Escape cancels, and the result is a `dict` keyed by field
name. A dialog that needs a different result type overrides `_result(values)` — that is how the
existing `TextInputDialog`/`CommentDialog` keep returning a plain string.

The dialogs that are pickers or informational panels (file selector, scope editor, colour
picker, certificate instructions) stay on `BaseDialog`: a form is a set of named values, not a
list of choices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Checkbox, Input, Label, Select, Static

from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "form_dialog.tcss").read_text(encoding="utf-8")

FieldKind = Literal["text", "int", "bool", "select", "secret"]


@dataclass
class FormField:
    """One field of a form: how to draw it, what it holds, how to validate it."""

    name: str
    label: str
    kind: FieldKind = "text"
    default: Any = ""
    placeholder: str = ""
    #: `(label, value)` pairs for a `select` field.
    options: list[tuple[str, str]] = field(default_factory=list)
    required: bool = False
    #: Extra rule: return an error message, or None when the value is fine.
    validate: Callable[[Any], str | None] | None = None
    help: str = ""


class FormDialog(BaseDialog[dict[str, Any] | None]):
    """A modal form: named fields in, a `dict` of values out (or None on cancel)."""

    DEFAULT_CSS = _CSS
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        fields: list[FormField],
        *,
        submit_label: str = "Save",
        description: str = "",
    ) -> None:
        super().__init__()
        if not fields:
            raise ValueError("FormDialog needs at least one field")
        names = [f.name for f in fields]
        if len(set(names)) != len(names):
            raise ValueError(f"FormDialog field names must be unique: {names}")
        self._form_title = title
        self._fields = list(fields)
        self._submit_label = submit_label
        self._description = description
        self._errors: dict[str, str] = {}

    # ── Layout ────────────────────────────────────────────────────────────

    def _wid(self, name: str) -> str:
        return f"form-{name}"

    def _field_widget(self, spec: FormField) -> Any:
        wid = self._wid(spec.name)
        if spec.kind == "bool":
            return Checkbox(spec.label, value=bool(spec.default), id=wid)
        if spec.kind == "select":
            # Textual 8 marks "no selection" with `Select.NULL`, not with an empty string.
            return Select(
                spec.options,
                value=spec.default if spec.default not in (None, "") else Select.NULL,
                allow_blank=not spec.required,
                id=wid,
            )
        return Input(
            str(spec.default or ""),
            id=wid,
            placeholder=spec.placeholder,
            password=spec.kind == "secret",
            compact=True,
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="form-dialog"):
            yield Static(f"[bold]{self._form_title}[/bold]", id="form-dialog-title")
            if self._description:
                yield Static(self._description, id="form-dialog-desc", classes="hint")
            for spec in self._fields:
                if spec.kind != "bool":
                    marker = " *" if spec.required else ""
                    yield Label(f"{spec.label}{marker}", classes="field-label")
                yield self._field_widget(spec)
                if spec.kind != "bool":
                    yield Static("", id=f"{self._wid(spec.name)}-error", classes="field-error")
                if spec.help:
                    yield Static(spec.help, classes="field-help")
            with Horizontal(id="form-dialog-buttons"):
                yield ToolbarButton(self._submit_label, "btn-form-submit")
                yield ToolbarButton("Cancel", "btn-form-cancel")

    def on_mount(self) -> None:
        # Focus the first editable field: the user opened the dialog to type in it.
        for spec in self._fields:
            if spec.kind in {"text", "int", "secret"}:
                self.query_one(f"#{self._wid(spec.name)}", Input).focus()
                return

    # ── Collect and validate ──────────────────────────────────────────────

    def _raw_value(self, spec: FormField) -> Any:
        widget = self.query_one(f"#{self._wid(spec.name)}")
        if isinstance(widget, Checkbox):
            return widget.value
        if isinstance(widget, Select):
            return None if widget.value is Select.NULL else widget.value
        return widget.value.strip()

    def _coerce(self, spec: FormField, raw: Any) -> tuple[Any, str | None]:
        if spec.kind == "int" and raw != "":
            try:
                return int(raw), None
            except (TypeError, ValueError):
                return raw, f"{spec.label}: enter a whole number"
        return raw, None

    def _check(self, spec: FormField, value: Any) -> str | None:
        if spec.required and (value is None or value == ""):
            return f"{spec.label} is required"
        if spec.validate is not None:
            message = spec.validate(value)
            if message:
                return f"{spec.label}: {message}"
        return None

    def _collect(self) -> tuple[dict[str, Any], dict[str, str]]:
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for spec in self._fields:
            raw = self._raw_value(spec)
            value, error = self._coerce(spec, raw)
            values[spec.name] = value
            message = error or self._check(spec, value)
            if message:
                errors[spec.name] = message
        return values, errors

    @property
    def errors(self) -> dict[str, str]:
        """Per-field errors of the last submit attempt (empty after a valid one)."""
        return dict(self._errors)

    def _show_errors(self, errors: dict[str, str]) -> None:
        self._errors = dict(errors)
        for spec in self._fields:
            if spec.kind == "bool":
                continue  # a checkbox has no error line: its label is the message
            error_widget = self.query_one(f"#{self._wid(spec.name)}-error", Static)
            error_widget.update(f"[red]{errors.get(spec.name, '')}[/red]")
        for spec in self._fields:
            if spec.name in errors and spec.kind in {"text", "int", "secret"}:
                self.query_one(f"#{self._wid(spec.name)}", Input).focus()
                break

    def _result(self, values: dict[str, Any]) -> Any:
        """Map the collected values to this dialog's result. Subclasses change this."""
        return values

    def action_submit(self) -> None:
        values, errors = self._collect()
        if errors:
            self._show_errors(errors)
            return
        self._errors = {}
        self.dismiss(self._result(values))

    # ── Events ────────────────────────────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-form-submit")
    def _on_submit(self, _: ToolbarButton.Pressed) -> None:
        self.action_submit()

    @on(ToolbarButton.Pressed, "#btn-form-cancel")
    def _on_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    @on(Input.Submitted)
    def _on_input_submitted(self, _: Input.Submitted) -> None:
        self.action_submit()
