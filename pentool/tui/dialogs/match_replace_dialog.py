"""Диалог управления правилами Match/Replace."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from pathlib import Path

_CSS = (Path(__file__).parent / "match_replace_dialog.tcss").read_text(encoding="utf-8")
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    Static,
)

from pentool.api.proxy_api import MatchReplaceRule
from pentool.tui.widgets.toolbar_button import ToolbarButton


_TARGET_OPTIONS = [("request", "Request"), ("response", "Response"), ("both", "Both")]
_SCOPE_OPTIONS  = [("all", "All"), ("headers", "Headers"), ("body", "Body")]


class MatchReplaceDialog(ModalScreen[list[MatchReplaceRule] | None]):
    """Диалог управления правилами автоматической замены."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, rules: list[MatchReplaceRule]) -> None:
        super().__init__()
        self._rules: list[MatchReplaceRule] = list(rules)
        self._selected_idx: int | None = None
        self._target_val: str = "both"
        self._scope_val: str = "all"

    def compose(self) -> ComposeResult:
        with Static(id="dialog"):
            with Static(id="title-bar"):
                yield Label("Match / Replace Rules", id="title")
                yield Button("✕", id="btn-close-title")

            yield DataTable(id="rules-table", cursor_type="row", zebra_stripes=True)

            with Horizontal(id="table-buttons"):
                yield ToolbarButton("+ Add",    "btn-add")
                yield ToolbarButton("✕ Del",    "btn-delete")
                yield ToolbarButton("▲ Up",     "btn-up")
                yield ToolbarButton("▼ Down",   "btn-down")

            with Static(id="form"):
                yield Label("Edit rule:", id="form-title")
                with Static(classes="form-row"):
                    yield Label("Match:", classes="form-label")
                    yield Input(placeholder="string or regex", id="input-match", compact=True)
                with Static(classes="form-row"):
                    yield Label("Replace:", classes="form-label")
                    yield Input(placeholder="replacement", id="input-replace", compact=True)
                with Static(classes="form-row"):
                    yield Label("Target:", classes="form-label")
                    yield ToolbarButton("Both ▼", "btn-sel-target", classes="sel-btn")
                with Static(classes="form-row"):
                    yield Label("Scope:", classes="form-label")
                    yield ToolbarButton("All ▼",  "btn-sel-scope",  classes="sel-btn")
                with Static(classes="form-row form-row-checks"):
                    yield Checkbox("Regex", id="chk-regex")
                    yield Checkbox("Enabled", value=True, id="chk-enabled")

            with Horizontal(id="bottom-buttons"):
                yield ToolbarButton("Apply",     "btn-apply")
                yield ToolbarButton("Save Rule", "btn-save")
                yield ToolbarButton("Cancel",    "btn-cancel")

    def on_mount(self) -> None:
        self._rebuild_table()

    # ── таблица ───────────────────────────────────────────────────────────────

    def _rebuild_table(self) -> None:
        table = self.query_one("#rules-table", DataTable)
        table.clear(columns=True)
        table.add_columns("En", "Target", "Scope", "Match", "Replace", "Regex")
        for rule in self._rules:
            en = "✓" if rule.enabled else "✗"
            table.add_row(
                en, rule.target, rule.scope,
                rule.match[:30], rule.replace[:20],
                "✓" if rule.is_regex else "✗",
                key=rule.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self._rules):
            self._selected_idx = idx
            self._load_rule_to_form(self._rules[idx])

    def _load_rule_to_form(self, rule: MatchReplaceRule) -> None:
        self.query_one("#input-match",  Input).value = rule.match
        self.query_one("#input-replace", Input).value = rule.replace
        self._target_val = rule.target
        self._scope_val  = rule.scope
        self._update_sel_labels()
        self.query_one("#chk-regex",   Checkbox).value = rule.is_regex
        self.query_one("#chk-enabled", Checkbox).value = rule.enabled

    def _update_sel_labels(self) -> None:
        target_label = dict(_TARGET_OPTIONS).get(self._target_val, self._target_val).title()
        scope_label  = dict(_SCOPE_OPTIONS).get(self._scope_val,  self._scope_val).title()
        try:
            self.query_one("#btn-sel-target", ToolbarButton).label = f"{target_label} ▼"
        except Exception:
            pass
        try:
            self.query_one("#btn-sel-scope", ToolbarButton).label = f"{scope_label} ▼"
        except Exception:
            pass

    def _read_form(self) -> MatchReplaceRule:
        match   = self.query_one("#input-match",  Input).value
        replace = self.query_one("#input-replace", Input).value
        is_regex = self.query_one("#chk-regex",   Checkbox).value
        enabled  = self.query_one("#chk-enabled", Checkbox).value
        return MatchReplaceRule(
            match=match,
            replace=replace,
            target=self._target_val,   # type: ignore[arg-type]
            scope=self._scope_val,     # type: ignore[arg-type]
            is_regex=is_regex,
            enabled=enabled,
        )

    # ── выпадающие меню Target / Scope ───────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-sel-target")
    def on_btn_sel_target(self, event: ToolbarButton.Pressed) -> None:
        items = [
            (val, ("✓ " if val == self._target_val else "  ") + label)
            for val, label in _TARGET_OPTIONS
        ]
        r = event.button.region
        self.app.show_context_menu(
            items, r.x, r.y + 1,
            callback=self._on_target_selected,
        )

    def _on_target_selected(self, val: str) -> None:
        self._target_val = val
        self._update_sel_labels()

    @on(ToolbarButton.Pressed, "#btn-sel-scope")
    def on_btn_sel_scope(self, event: ToolbarButton.Pressed) -> None:
        items = [
            (val, ("✓ " if val == self._scope_val else "  ") + label)
            for val, label in _SCOPE_OPTIONS
        ]
        r = event.button.region
        self.app.show_context_menu(
            items, r.x, r.y + 1,
            callback=self._on_scope_selected,
        )

    def _on_scope_selected(self, val: str) -> None:
        self._scope_val = val
        self._update_sel_labels()

    # ── кнопки таблицы ───────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close-title":
            self.action_cancel()

    @on(ToolbarButton.Pressed, "#btn-add")
    def on_btn_add(self, _: ToolbarButton.Pressed) -> None:
        rule = MatchReplaceRule(match="", replace="")
        self._rules.append(rule)
        self._selected_idx = len(self._rules) - 1
        self._rebuild_table()

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

    @on(ToolbarButton.Pressed, "#btn-save")
    def on_btn_save(self, _: ToolbarButton.Pressed) -> None:
        if self._selected_idx is not None:
            new_rule = self._read_form()
            new_rule.id = self._rules[self._selected_idx].id
            self._rules[self._selected_idx] = new_rule
            self._rebuild_table()

    @on(ToolbarButton.Pressed, "#btn-apply")
    def on_btn_apply(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(list(self._rules))

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def on_btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
