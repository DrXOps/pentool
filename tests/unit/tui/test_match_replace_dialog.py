"""MatchReplace dialogs: the rule editor is a `FormDialog`, the manager keeps the list (step 7).

The editor used to be an inline form whose target/scope "dropdowns" were `ToolbarButton`s with
hand-maintained labels: the label and the saved value could disagree. The form now uses real
`Select` fields, and the manager opens it per rule (Add / Edit / row click).
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from pentool.modules.match_replace import MatchReplaceRule
from pentool.tui.dialogs.match_replace_dialog import MatchReplaceDialog, MatchReplaceRuleDialog
from pentool.tui.widgets.toolbar_button import ToolbarButton


class _Host(App):
    def compose(self) -> ComposeResult:
        yield Static("host")


async def _open(pilot, dialog) -> list:
    results: list = []
    pilot.app.push_screen(dialog, results.append)
    await pilot.pause()
    return results


def _rule(match: str = "foo", replace: str = "bar", **kwargs) -> MatchReplaceRule:
    return MatchReplaceRule(match=match, replace=replace, **kwargs)


class TestRuleEditor:
    async def test_submit_returns_a_rule_with_all_fields(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = MatchReplaceRuleDialog(_rule())
            results = await _open(pilot, dialog)
            dialog.query_one("#form-match", Input).value = "secret"
            dialog.query_one("#form-replace", Input).value = "redacted"
            dialog.action_submit()
            await pilot.pause()

        assert len(results) == 1
        rule = results[0]
        assert isinstance(rule, MatchReplaceRule)
        assert (rule.match, rule.replace) == ("secret", "redacted")
        assert rule.target == "both", "по умолчанию правило применяется к запросу и ответу"
        assert rule.scope == "all"
        assert rule.enabled is True

    async def test_existing_rule_is_prefilled(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = MatchReplaceRuleDialog(_rule(target="response", scope="headers", is_regex=True, enabled=False))
            await _open(pilot, dialog)

            assert dialog.query_one("#form-match", Input).value == "foo"
            assert dialog.query_one("#form-target").value == "response"
            assert dialog.query_one("#form-scope").value == "headers"
            assert dialog.errors == {}

    async def test_an_empty_rule_is_allowed_for_later_editing(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = MatchReplaceRuleDialog()
            results = await _open(pilot, dialog)
            dialog.action_submit()
            await pilot.pause()

        assert results and results[0].match == "" and results[0].replace == ""


class TestManager:
    async def test_table_shows_the_rules_and_apply_returns_them(self) -> None:
        rules = [_rule("a"), _rule("b")]
        app = _Host()
        async with app.run_test() as pilot:
            dialog = MatchReplaceDialog(rules)
            results = await _open(pilot, dialog)

            table = dialog.query_one("#rules-table")
            assert table.row_count == 2

            dialog.query_one("#btn-apply", ToolbarButton).on_click()
            await pilot.pause()

        assert results == [rules], "Apply возвращает тот же список правил"

    async def test_cancel_returns_none(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = MatchReplaceDialog([_rule()])
            results = await _open(pilot, dialog)
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]

    async def test_add_opens_the_editor_and_append_the_rule(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            manager = MatchReplaceDialog([])
            await _open(pilot, manager)

            manager.query_one("#btn-add", ToolbarButton).on_click()
            await pilot.pause()
            editor = app.screen
            assert isinstance(editor, MatchReplaceRuleDialog), "Add должен открыть редактор правила"
            editor.query_one("#form-match", Input).value = "new"
            editor.action_submit()
            await pilot.pause()

            assert manager.query_one("#rules-table").row_count == 1

    async def test_editing_keeps_the_rule_id(self) -> None:
        original = _rule("old")
        app = _Host()
        async with app.run_test() as pilot:
            manager = MatchReplaceDialog([original])
            await _open(pilot, manager)

            manager._open_editor(0)
            await pilot.pause()
            editor = app.screen
            editor.query_one("#form-match", Input).value = "new"
            editor.action_submit()
            await pilot.pause()

            assert manager._rules[0].match == "new"
            assert manager._rules[0].id == original.id, "id правила должен сохраняться при правке"

    async def test_delete_removes_the_selected_rule(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            manager = MatchReplaceDialog([_rule("a"), _rule("b")])
            await _open(pilot, manager)
            manager._selected_idx = 0
            manager.query_one("#btn-delete", ToolbarButton).on_click()
            await pilot.pause()

            assert [rule.match for rule in manager._rules] == ["b"]
            assert manager.query_one("#rules-table").row_count == 1
