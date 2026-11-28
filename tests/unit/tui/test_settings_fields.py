"""Declarative settings fields (`FieldSpec`) — one rule per field instead of a handler per field.

The four panes (proxy, project, network, privacy) collected their values by hand with slightly
different rules. These tests pin the shared rule and the integrity of the specs: an int is
digits-only and clamped, an empty required text is skipped, a missing widget is a logged problem
rather than a lost save, and every spec still names a widget the screen composes and a key the
config actually has.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from textual.css.query import NoMatches

from pentool.core.config import Config
from pentool.tui.screens.settings.fields import (
    INTERFACE,
    NETWORK,
    PRIVACY,
    PROJECT,
    PROXY,
    FieldSpec,
    SectionSpec,
    collect_changes,
    read_section,
    render_field,
    render_rows,
)

SCREEN_SOURCE = Path(__file__).resolve().parents[3] / "pentool" / "tui" / "screens" / "settings" / "screen.py"


class _Widget:
    def __init__(self, value) -> None:
        self.value = value


class _Screen:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def query_one(self, selector: str):
        widget_id = selector.lstrip("#")
        if widget_id not in self._values:
            raise NoMatches(selector)
        return _Widget(self._values[widget_id])


def _cfg(**kwargs) -> SimpleNamespace:
    defaults = {
        "proxy_host": "127.0.0.1",
        "proxy_port": 8080,
        "auto_save_enabled": False,
        "auto_save_interval": 5,
        "default_user_agent": "pentool",
        "request_timeout": 15,
        "connect_timeout": 10,
        "max_redirects": 10,
        "verify_ssl": False,
        "tooltips_enabled": True,
        "panel_icons": "unicode",
        "collaborator_url": "",
        "scan_marker_enabled": False,
        "scan_marker_name": "X-Scanner",
        "scan_marker_value": "pentool/1.0",
        "send_crash_reports": True,
        "check_updates": True,
        "auto_scope": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestCoerce:
    def test_int_requires_digits_and_clamps(self) -> None:
        spec = FieldSpec("proxy_port", "set-proxy-port", "int", minimum=1, maximum=65535)
        assert spec.coerce("8081") == (8081, None)
        assert spec.coerce(" 8081 ") == (8081, None)
        assert spec.coerce("0") == (1, None), "нижняя граница применяется"
        assert spec.coerce("99999") == (65535, None), "верхняя граница применяется"
        value, error = spec.coerce("8o80")
        assert value is None and "not a number" in error

    def test_negative_number_is_not_digits(self) -> None:
        value, error = FieldSpec("n", "set-n", "int", minimum=0).coerce("-5")
        assert value is None and error, "минус не проходит isdigit — поле пропускается"

    def test_text_can_be_optional_or_required(self) -> None:
        optional = FieldSpec("collaborator_url", "set-collaborator-url", "text")
        required = FieldSpec("proxy_host", "set-proxy-host", "text", require_text=True)
        assert optional.coerce("  ") == ("", None), "очистить URL — законное изменение"
        assert required.coerce("  ")[0] is None
        assert required.coerce(" 10.0.0.1 ")[0] == "10.0.0.1"

    def test_bool_passes_through(self) -> None:
        assert FieldSpec("verify_ssl", "set-verify-ssl", "bool").coerce(0) == (False, None)


class TestReadSection:
    def test_only_changed_values_are_returned(self) -> None:
        cfg = _cfg(proxy_port=8080)
        screen = _Screen({"set-proxy-host": "127.0.0.1", "set-proxy-port": "9090"})
        changes, problems = read_section(screen, PROXY, cfg)

        assert changes == {"proxy_port": 9090}, "same values must not be written back"
        assert problems == []

    def test_missing_widget_is_a_problem_not_a_crash(self) -> None:
        cfg = _cfg()
        screen = _Screen({"set-proxy-port": "9090"})
        changes, problems = read_section(screen, PROXY, cfg)

        assert changes == {"proxy_port": 9090}, "остальные поля всё равно сохраняются"
        assert any("set-proxy-host" in p and "not mounted" in p for p in problems)

    def test_invalid_int_is_reported_and_skipped(self) -> None:
        cfg = _cfg()
        screen = _Screen({"set-autosave-enabled": True, "set-autosave-interval": "soon"})
        changes, problems = read_section(screen, PROJECT, cfg)

        assert changes == {"auto_save_enabled": True}
        assert any("not a number" in p for p in problems)

    def test_empty_required_text_is_skipped(self) -> None:
        cfg = _cfg(default_user_agent="pentool")
        values = dict.fromkeys(
            (
                "set-req-timeout",
                "set-conn-timeout",
                "set-max-redirects",
                "set-scan-marker-name",
                "set-scan-marker-value",
                "set-collaborator-url",
                "set-user-agent",
            ),
            "",
        )
        values.update({"set-req-timeout": "15", "set-conn-timeout": "10", "set-max-redirects": "10"})
        screen = _Screen(values)
        changes, problems = read_section(screen, NETWORK, cfg)

        assert "default_user_agent" not in changes
        assert any("default_user_agent" in p for p in problems)

    def test_option_and_bool_fields_are_collected(self) -> None:
        cfg = _cfg(panel_icons="unicode", tooltips_enabled=True, send_crash_reports=True)
        network_values = {spec.widget_id: getattr(cfg, spec.key) for spec in NETWORK.fields}
        changes, _ = read_section(_Screen(network_values), NETWORK, cfg)
        interface_values = {spec.widget_id: getattr(cfg, spec.key) for spec in INTERFACE.fields}
        interface_values.update({"set-panel-icons": "emoji", "set-tooltips": False})
        interface_changes, _ = read_section(_Screen(interface_values), INTERFACE, cfg)
        privacy_changes, _ = read_section(
            _Screen({"set-send-crash-reports": False, "set-check-updates": True, "set-auto-scope": False}), PRIVACY, cfg
        )

        assert interface_changes["panel_icons"] == "emoji"
        assert interface_changes["tooltips_enabled"] is False
        assert privacy_changes == {"send_crash_reports": False}

    def test_collect_changes_uses_the_given_config(self) -> None:
        cfg = _cfg(auto_scope=False)
        screen = _Screen({"set-send-crash-reports": True, "set-check-updates": True, "set-auto-scope": True})

        assert collect_changes(screen, PRIVACY, cfg) == {"auto_scope": True}


class TestSpecsMatchTheCode:
    @pytest.mark.parametrize("section", [PROXY, PROJECT, NETWORK, PRIVACY, INTERFACE], ids=lambda s: s.name)
    def test_every_widget_id_reaches_the_compose(self, section: SectionSpec) -> None:
        """Either the pane renders the section's rows, or it composes the id itself.

        Every section is rendered from `render_rows(<SECTION>.fields…)`; only a spec that a
        pane composes by hand (none today) would be accepted through a literal `id=` instead.
        """
        source = SCREEN_SOURCE.read_text(encoding="utf-8")
        rendered_from_section = f"render_rows({section.name.upper()}.fields" in source
        for spec in section.fields:
            composed = f'id="{spec.widget_id}"' in source
            assert rendered_from_section or composed, (
                f"{section.name}: #{spec.widget_id} is neither rendered from the section "
                "nor composed anywhere — the field would silently stop being saved"
            )

    @pytest.mark.parametrize("section", [PROXY, PROJECT, NETWORK, PRIVACY, INTERFACE], ids=lambda s: s.name)
    def test_every_key_exists_on_the_config(self, section: SectionSpec) -> None:
        cfg = Config()
        for spec in section.fields:
            assert hasattr(cfg, spec.key), f"{section.name}: Config has no attribute {spec.key!r}"

    def test_option_choices_match_the_screen_lists(self) -> None:
        """The spec's choices must be the pane's list, or the two would drift apart."""
        from pentool.tui.screens.settings.screen import SettingsScreen

        spec = next(field for field in INTERFACE.fields if field.widget_id == "set-panel-icons")
        assert list(spec.choices) == list(SettingsScreen._PANEL_ICONS)

    def test_widget_ids_are_unique_across_sections(self) -> None:
        ids = [spec.widget_id for section in (PROXY, PROJECT, NETWORK, PRIVACY, INTERFACE) for spec in section.fields]
        assert len(ids) == len(set(ids)), "two fields sharing a widget id would fight over one widget"


class TestRendering:
    """Rows are built from the specs, so a pane cannot drift from its section."""

    async def test_rows_carry_the_spec_ids_and_the_config_values(self) -> None:
        from textual.app import App, ComposeResult
        from textual.containers import Vertical
        from textual.widgets import Checkbox, Input

        cfg = _cfg(proxy_port=9090, verify_ssl=True)

        class _RowsApp(App):
            def compose(self) -> ComposeResult:
                with Vertical():
                    yield from render_rows(PROXY.fields, cfg)
                    yield from render_rows(NETWORK.fields[4:5], cfg)

        app = _RowsApp()
        async with app.run_test():
            assert app.query_one("#set-proxy-host", Input).value == "127.0.0.1"
            assert app.query_one("#set-proxy-port", Input).value == "9090"
            ssl = app.query_one("#set-verify-ssl", Checkbox)
            assert ssl.value is True
            assert str(ssl.label) == "Verify SSL certificates", "подпись чекбокса берётся из спека"

    async def test_render_field_covers_bool_int_text_and_option(self) -> None:
        from textual.app import App, ComposeResult
        from textual.containers import Vertical
        from textual.widgets import Checkbox, Input

        cfg = _cfg(panel_icons="emoji", request_timeout=42)

        class _FieldsApp(App):
            def compose(self) -> ComposeResult:
                with Vertical():
                    # int, bool and option: the three widget types the panes use.
                    yield render_field(NETWORK.fields[1], cfg)
                    yield render_field(NETWORK.fields[4], cfg)
                    yield render_field(INTERFACE.fields[1], cfg)

        app = _FieldsApp()
        async with app.run_test():
            assert app.query_one("#set-req-timeout", Input).value == "42"
            assert isinstance(app.query_one("#set-verify-ssl"), Checkbox)
            assert app.query_one("#set-panel-icons").value == "emoji"


class TestSettingsScreenMounts:
    """The real screen renders every pane from its section (not just the helpers in isolation)."""

    async def test_panes_are_rendered_and_prefilled_from_the_config(self) -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Checkbox, Input

        from pentool.core.config import get_config
        from pentool.tui.screens.settings.screen import SettingsScreen

        class _SettingsHost(App):
            def compose(self) -> ComposeResult:
                yield SettingsScreen()

        cfg = get_config()
        app = _SettingsHost()
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            screen = app.query_one(SettingsScreen)
            assert screen.query_one("#set-proxy-host", Input).value == cfg.proxy_host
            assert screen.query_one("#set-proxy-port", Input).value == str(cfg.proxy_port)
            assert screen.query_one("#set-autosave-interval", Input).value == str(cfg.auto_save_interval)
            assert isinstance(screen.query_one("#set-verify-ssl", Checkbox), Checkbox)
            assert isinstance(screen.query_one("#set-send-crash-reports", Checkbox), Checkbox)
            assert screen.query_one("#set-panel-icons").value == (cfg.panel_icons or "unicode")
