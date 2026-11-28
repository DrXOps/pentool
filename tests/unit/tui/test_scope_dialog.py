"""ScopeDialog on `FormDialog` (step 7): hosts and regex lists, validation under the field.

The dialog used to carry its own Save/Escape wiring and a bottom validation line. It now declares
three `lines` fields; an invalid regex keeps the dialog open with the message under the field.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Static, TextArea

from pentool.tui.dialogs.scope_dialog import ScopeConfig, ScopeDialog, validate_patterns


class _Host(App):
    def compose(self) -> ComposeResult:
        yield Static("host")


async def _open(pilot, dialog) -> list:
    results: list = []
    pilot.app.push_screen(dialog, results.append)
    await pilot.pause()
    return results


class TestBasicMode:
    async def test_returns_the_host_list_without_blank_lines(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(["old.example"])
            results = await _open(pilot, dialog)
            area = dialog.query_one("#form-hosts", TextArea)
            area.text = "a.example\n\n  b.example  \n"
            dialog.action_submit()
            await pilot.pause()

        assert results == [["a.example", "b.example"]]

    async def test_initial_hosts_are_shown(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(["one.example", "two.example"])
            await _open(pilot, dialog)
            assert dialog.query_one("#form-hosts", TextArea).text == "one.example\ntwo.example"

    async def test_cancel_returns_none(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(["x.example"])
            results = await _open(pilot, dialog)
            await pilot.press("escape")
            await pilot.pause()

        assert results == [None]


class TestExtendedMode:
    async def test_returns_scope_config_with_regex_lists(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(extended=True)
            results = await _open(pilot, dialog)
            dialog.query_one("#form-hosts", TextArea).text = "api.example"
            dialog.query_one("#form-regex_include", TextArea).text = "/api/\n/v2/"
            dialog.query_one("#form-regex_exclude", TextArea).text = r"\.js$"
            dialog.action_submit()
            await pilot.pause()

        assert len(results) == 1
        config = results[0]
        assert isinstance(config, ScopeConfig)
        assert config.hosts == ["api.example"]
        assert config.regex_include == ["/api/", "/v2/"]
        assert config.regex_exclude == [r"\.js$"]
        assert config.matches("https://api.example/v2/users")
        assert not config.matches("https://api.example/v2/app.js")

    async def test_scope_config_input_enables_extended_mode(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(ScopeConfig(hosts=["a.example"], regex_include=["/api/"]))
            await _open(pilot, dialog)

            assert dialog.query_one("#form-regex_include", TextArea).text == "/api/"

    async def test_invalid_regex_keeps_the_dialog_open_with_the_message_under_the_field(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(extended=True)
            results = await _open(pilot, dialog)
            dialog.query_one("#form-regex_include", TextArea).text = "(["
            dialog.action_submit()
            await pilot.pause()

            assert results == [], "невалидный regex не должен закрывать диалог"
            error = str(dialog.query_one("#form-regex_include-error", Static).content)
            assert "Regex Include" in error and "invalid regex" in error
            assert "regex_include" in dialog.errors

    async def test_valid_regex_passes_validation(self) -> None:
        app = _Host()
        async with app.run_test() as pilot:
            dialog = ScopeDialog(extended=True)
            results = await _open(pilot, dialog)
            dialog.query_one("#form-regex_include", TextArea).text = r"\.(php|asp)$"
            dialog.action_submit()
            await pilot.pause()

        assert results and isinstance(results[0], ScopeConfig)


class TestHelpers:
    def test_validate_patterns_reports_only_bad_ones(self) -> None:
        assert validate_patterns(["/api/", "(["]) == ["(["]
        assert validate_patterns(["/api/"]) == []

    def test_host_list_alias_is_kept(self) -> None:
        assert ScopeConfig(hosts=["a"]).host_list == ["a"]
