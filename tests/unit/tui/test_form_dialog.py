"""FormDialog — one declarative form for the TUI dialogs (step 7).

The dialog owns layout, focus, per-field validation and the result type, so a caller declares
fields instead of hand-writing compose/handlers. These tests drive the real widgets in a mounted
app: values come back typed, errors appear under the field that caused them, Enter submits and
Escape cancels.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Input, Select, Static

from pentool.tui.dialogs.form_dialog import FormDialog, FormField


class _Host(App):
    def compose(self) -> ComposeResult:
        yield Static("host")


async def _open(pilot, dialog: FormDialog) -> list:
    results: list = []
    pilot.app.push_screen(dialog, results.append)
    await pilot.pause()
    return results


def _fields() -> list[FormField]:
    return [
        FormField("name", "Name", default=""),
        FormField("count", "Count", kind="int", default="10"),
        FormField("enabled", "Enabled", kind="bool", default=True),
        FormField("mode", "Mode", kind="select", options=[("Fast", "fast"), ("Safe", "safe")], default="safe"),
    ]


class TestSubmit:
    async def test_enter_returns_typed_values(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Settings", _fields())
            results = await _open(pilot, dialog)
            dialog.query_one("#form-name", Input).value = "alpha"
            await pilot.press("enter")
            await pilot.pause()

        # Select keeps its default, the int is converted, the checkbox keeps its value.
        assert results == [{"name": "alpha", "count": 10, "enabled": True, "mode": "safe"}]

    async def test_empty_select_is_none_not_blank(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            fields = [FormField("mode", "Mode", kind="select", options=[("Fast", "fast")])]
            dialog = FormDialog("Pick", fields)
            results = await _open(pilot, dialog)
            # A select-only form has no text field to focus, and Enter on a Select opens its
            # overlay — submit through the dialog action, which is what Save does.
            dialog.action_submit()
            await pilot.pause()

        assert results == [{"mode": None}]

    async def test_secret_field_is_masked(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Token", [FormField("token", "Token", kind="secret")])
            await _open(pilot, dialog)
            widget = dialog.query_one("#form-token", Input)
            assert widget.password is True, "secret values must not be shown on screen"

    async def test_custom_result_type_via_override(self) -> None:
        class _Single(FormDialog):
            def _result(self, values):
                return values["value"]

        app = _Host()
        async with app.run_test() as pilot:
            dialog = _Single("One", [FormField("value", "Value", default="x")])
            results = await _open(pilot, dialog)
            await pilot.press("enter")
            await pilot.pause()

        assert results == ["x"], "a single-field dialog may keep returning a scalar"

    async def test_duplicate_or_missing_fields_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            FormDialog("Bad", [])
        with pytest.raises(ValueError):
            FormDialog("Bad", [FormField("a", "A"), FormField("a", "B")])


class TestValidation:
    async def test_non_numeric_int_keeps_the_dialog_open_with_an_error(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Settings", _fields())
            results = await _open(pilot, dialog)
            dialog.query_one("#form-count", Input).value = "ten"
            await pilot.press("enter")
            await pilot.pause()

            error = str(dialog.query_one("#form-count-error", Static).content)
            assert "whole number" in error
            assert "whole number" in dialog.errors["count"]
            assert results == [], "an invalid form must not dismiss"

            dialog.query_one("#form-count", Input).value = "42"
            await pilot.press("enter")
            await pilot.pause()

        assert results and results[0]["count"] == 42

    async def test_required_field_reports_the_label(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Name", [FormField("name", "Name", required=True)])
            results = await _open(pilot, dialog)
            await pilot.press("enter")
            await pilot.pause()

            assert "Name is required" in str(dialog.query_one("#form-name-error", Static).content)
            assert dialog.errors == {"name": "Name is required"}
            assert results == []

    async def test_custom_validator_message_names_the_field(self) -> None:
        def _even(value):
            if isinstance(value, int) and value % 2:
                return "must be even"
            return None

        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Count", [FormField("n", "Count", kind="int", default="3", validate=_even)])
            results = await _open(pilot, dialog)
            await pilot.press("enter")
            await pilot.pause()

            assert "Count: must be even" in str(dialog.query_one("#form-n-error", Static).content)
            assert dialog.errors == {"n": "Count: must be even"}
            assert results == []

    async def test_errors_clear_after_a_valid_submit(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Name", [FormField("name", "Name", required=True)])
            results = await _open(pilot, dialog)
            await pilot.press("enter")
            await pilot.pause()
            dialog.query_one("#form-name", Input).value = "ok"
            await pilot.press("enter")
            await pilot.pause()

        assert results == [{"name": "ok"}]


class TestCancelAndLayout:
    async def test_escape_returns_none(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Settings", _fields())
            results = await _open(pilot, dialog)
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]

    async def test_description_and_help_are_rendered(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            fields = [FormField("name", "Name", help="Shown in the tab title")]
            dialog = FormDialog("Title", fields, description="What this form is for")
            await _open(pilot, dialog)

            texts = [str(w.content) for w in dialog.query(Static)]
            assert any("What this form is for" in t for t in texts)
            assert any("Shown in the tab title" in t for t in texts)

    async def test_checkbox_and_select_are_mounted(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = FormDialog("Settings", _fields())
            await _open(pilot, dialog)

            assert dialog.query_one("#form-enabled", Checkbox).value is True
            assert dialog.query_one("#form-mode", Select).value == "safe"


class TestMigrations:
    """The dialogs that were re-built on FormDialog keep their public result type."""

    async def test_comment_dialog_returns_the_string(self) -> None:
        from pentool.tui.dialogs.comment_dialog import CommentDialog

        app = _Host()
        async with app.run_test() as pilot:
            dialog = CommentDialog("old")
            results = await _open(pilot, dialog)
            dialog.query_one("#form-comment", Input).value = "reviewed"
            await pilot.press("enter")
            await pilot.pause()

        assert results == ["reviewed"]

    async def test_comment_dialog_accepts_an_empty_comment(self) -> None:
        from pentool.tui.dialogs.comment_dialog import CommentDialog

        app = _Host()
        async with app.run_test() as pilot:
            dialog = CommentDialog("old")
            results = await _open(pilot, dialog)
            dialog.query_one("#form-comment", Input).value = ""
            await pilot.press("enter")
            await pilot.pause()

        assert results == [""], "clearing a comment is a valid edit, not a cancel"
