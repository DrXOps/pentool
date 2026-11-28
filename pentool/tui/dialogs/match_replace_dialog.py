"""Dialog for managing Match/Replace rules.

The rule *editor* is a `FormDialog` (`MatchReplaceRuleDialog`, step 7): match/replace text,
target and scope as selects, the two flags as checkboxes. The manager keeps the list: a table,
add/delete/reorder and Apply/Cancel.

Editing used to happen in an always-visible form under the table whose two "dropdowns" were
`ToolbarButton`s with hand-maintained labels — the labels and the saved values could disagree
(the rule was saved with one target while the button showed another), which is exactly what a
form with real `Select` fields fixes.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Label, Static

from pentool.api.proxy_api import MatchReplaceRule
from pentool.core.logging import get_logger
from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.dialogs.form_dialog import FormDialog, FormField
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "match_replace_dialog.tcss").read_text(encoding="utf-8")

_TARGET_OPTIONS = [("Request", "request"), ("Response", "response"), ("Both", "both")]
_SCOPE_OPTIONS = [("All", "all"), ("Headers", "headers"), ("Body", "body")]


class MatchReplaceRuleDialog(FormDialog):
    """Edit one rule; returns `MatchReplaceRule` (the id is assigned by the manager)."""

    def __init__(self, rule: MatchReplaceRule | None = None) -> None:
        current = rule or MatchReplaceRule(match="", replace="")
        super().__init__(
            "Edit rule",
            [
                FormField("match", "Match", default=current.match, placeholder="string or regex"),
                FormField("replace", "Replace", default=current.replace, placeholder="replacement"),
                FormField("target", "Target", kind="select", options=_TARGET_OPTIONS, default=current.target),
                FormField("scope", "Scope", kind="select", options=_SCOPE_OPTIONS, default=current.scope),
                FormField("is_regex", "Regex", kind="bool", default=current.is_regex),
                FormField("enabled", "Enabled", kind="bool", default=current.enabled),
            ],
            submit_label="Save",
            description="An empty match rule does nothing and can be left for later.",
        )

    def _result(self, values: dict) -> MatchReplaceRule:
        return MatchReplaceRule(
            match=values["match"],
            replace=values["replace"],
            target=values["target"] or "both",
            scope=values["scope"] or "all",
            is_regex=values["is_regex"],
            enabled=values["enabled"],
        )


class MatchReplaceDialog(BaseDialog[list[MatchReplaceRule] | None]):
    """Dialog for managing automatic replacement rules."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, rules: list[MatchReplaceRule]) -> None:
        super().__init__()
        self._rules: list[MatchReplaceRule] = list(rules)
        self._selected_idx: int | None = None

    def compose(self) -> ComposeResult:
        with Static(id="dialog"):
            with Static(id="title-bar"):
                yield Label("Match / Replace Rules", id="title")
                yield Button("✕", id="btn-close-title")

            yield DataTable(id="rules-table", cursor_type="row", zebra_stripes=True)

            with Horizontal(id="table-buttons"):
                yield ToolbarButton("+ Add", "btn-add")
                yield ToolbarButton("✕ Del", "btn-delete")
                yield ToolbarButton("▲ Up", "btn-up")
                yield ToolbarButton("▼ Down", "btn-down")
                yield ToolbarButton("✎ Edit", "btn-edit")

            with Horizontal(id="bottom-buttons"):
                yield ToolbarButton("Apply", "btn-apply")
                yield ToolbarButton("Cancel", "btn-cancel")

    def on_mount(self) -> None:
        self._rebuild_table()

    # ── table ─────────────────────────────────────────────────────────────────

    def _rebuild_table(self) -> None:
        table = self.query_one("#rules-table", DataTable)
        table.clear(columns=True)
        table.add_columns("En", "Target", "Scope", "Match", "Replace", "Regex")
        for rule in self._rules:
            en = "✓" if rule.enabled else "✗"
            table.add_row(
                en,
                rule.target,
                rule.scope,
                rule.match[:30],
                rule.replace[:20],
                "✓" if rule.is_regex else "✗",
                key=rule.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self._rules):
            self._selected_idx = idx
            self._open_editor(idx)

    # ── editor ────────────────────────────────────────────────────────────────

    def _open_editor(self, idx: int | None) -> None:
        current = self._rules[idx] if idx is not None else None

        def _applied(result: MatchReplaceRule | None) -> None:
            if result is None:
                return
            if idx is None:
                self._rules.append(result)
                self._selected_idx = len(self._rules) - 1
            else:
                result.id = self._rules[idx].id
                self._rules[idx] = result
                self._selected_idx = idx
            self._rebuild_table()

        self.app.push_screen(MatchReplaceRuleDialog(current), _applied)

    @on(ToolbarButton.Pressed, "#btn-add")
    def on_btn_add(self, _: ToolbarButton.Pressed) -> None:
        self._open_editor(None)

    @on(ToolbarButton.Pressed, "#btn-edit")
    def on_btn_edit(self, _: ToolbarButton.Pressed) -> None:
        if self._selected_idx is not None and 0 <= self._selected_idx < len(self._rules):
            self._open_editor(self._selected_idx)

    @on(ToolbarButton.Pressed, "#btn-delete")
    def on_btn_delete(self, _: ToolbarButton.Pressed) -> None:
        if self._selected_idx is not None and self._rules:
            self._rules.pop(self._selected_idx)
            self._selected_idx = None
            self._rebuild_table()

    @on(ToolbarButton.Pressed, "#btn-up")
    def on_btn_up(self, _: ToolbarButton.Pressed) -> None:
        if self._selected_idx is not None and self._selected_idx > 0:
            i = self._selected_idx
            self._rules[i - 1], self._rules[i] = self._rules[i], self._rules[i - 1]
            self._selected_idx = i - 1
            self._rebuild_table()

    @on(ToolbarButton.Pressed, "#btn-down")
    def on_btn_down(self, _: ToolbarButton.Pressed) -> None:
        if self._selected_idx is not None and self._selected_idx < len(self._rules) - 1:
            i = self._selected_idx
            self._rules[i + 1], self._rules[i] = self._rules[i], self._rules[i + 1]
            self._selected_idx = i + 1
            self._rebuild_table()

    @on(ToolbarButton.Pressed, "#btn-apply")
    def on_btn_apply(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(list(self._rules))

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def on_btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close-title":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
