"""Application settings screen."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from textual import on
from textual.app import ComposeResult, InvalidThemeError
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, Input, Static, Switch, TabbedContent, TabPane

from pentool.core.error_guard import err
from pentool.core.logging import get_logger
from pentool.tui.markup import esc
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.screens.settings.hotkeys import HotkeySettingsScreen
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.option_cycler import OptionCycler
from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)


class UIMode(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"


class SettingsScreen(AppMixin, Widget):
    """Settings dialog: Interface / Proxy / Hotkeys / Project.

    Mounted as a regular screen-widget; opened via ContentSwitcher.
    """

    DEFAULT_CSS = _CSS

    # Debounce timer for live theme preview — fires 150ms after last click
    _theme_debounce: Timer | None = None

    _THEMES = [
        ("Dark", "textual-dark"),
        ("Light", "textual-light"),
        ("Nord", "nord"),
        ("Dracula", "dracula"),
        ("Gruvbox", "gruvbox"),
        ("Tokyo Night", "tokyo-night"),
        ("Catppuccin", "catppuccin-mocha"),
        ("Solarized Dark", "solarized-dark"),
        ("Monokai", "monokai"),
    ]
    _MODES = [("Advanced", "advanced"), ("Basic", "basic")]
    # Набор иконок панелей: покрытие шрифтов различается (см. ContentPanel.ICON_SETS)
    _PANEL_ICONS = [("Unicode", "unicode"), ("ASCII", "ascii"), ("Emoji", "emoji")]

    def compose(self) -> ComposeResult:
        with TabbedContent(id="settings-tabs"):
            with TabPane("Interface", id="tab-interface"):
                with Vertical(classes="settings-pane"):
                    yield Static("Interface Settings", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("Theme:", classes="row-label")
                        yield OptionCycler(self._THEMES, initial="dark", id="set-theme")
                    with Horizontal(classes="row"):
                        yield Static("UI Mode:", classes="row-label")
                        yield OptionCycler(self._MODES, initial="advanced", id="set-ui-mode")
                    with Horizontal(classes="row"):
                        yield Static("Hints on hover:", classes="row-label")
                        yield Checkbox("Show tooltips", id="set-tooltips", value=True)
                    with Horizontal(classes="row"):
                        yield Static("Panel icons:", classes="row-label")
                        yield OptionCycler(self._PANEL_ICONS, initial="unicode", id="set-panel-icons")
                    yield ToolbarButton("Save", "settings-save")

            with TabPane("Proxy", id="tab-proxy"):
                with Vertical(classes="settings-pane"):
                    yield Static("Proxy Settings", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("Listen host:", classes="row-label")
                        yield Input(value="127.0.0.1", id="set-proxy-host", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Listen port:", classes="row-label")
                        yield Input(value="8080", id="set-proxy-port", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Upstream proxy:", classes="row-label")
                        yield Input(placeholder="http://proxy:8080", id="set-upstream", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("CA certificate:", classes="row-label")
                        yield Button("Install CA cert", id="settings-open-ca")
                    yield ToolbarButton("Save", "settings-save-proxy")

            with TabPane("Hotkeys", id="tab-hotkeys"):
                yield HotkeySettingsScreen(id="hotkey-settings")

            with TabPane("Project", id="tab-project"):
                with Vertical(classes="settings-pane"):
                    yield Static("Project Settings", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("Auto-save interval (min):", classes="row-label")
                        yield Input(placeholder="0 = disabled", id="set-autosave-interval", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Auto-save enabled:", classes="row-label")
                        yield Checkbox("Enable auto-save", id="set-autosave-enabled", value=False)
                    yield ToolbarButton("Save", "settings-save-project")

            with TabPane("Network", id="tab-network"):
                with Vertical(classes="settings-pane"):
                    yield Static("Network / Scanner Settings", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("User-Agent:", classes="row-label")
                        yield Input(
                            placeholder="Mozilla/5.0 ...",
                            id="set-user-agent",
                            compact=True,
                        )
                    with Horizontal(classes="row"):
                        yield Static("Request timeout (s):", classes="row-label")
                        yield Input(value="15", id="set-req-timeout", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Connect timeout (s):", classes="row-label")
                        yield Input(value="10", id="set-conn-timeout", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Max redirects:", classes="row-label")
                        yield Input(value="10", id="set-max-redirects", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Verify SSL:", classes="row-label")
                        yield Checkbox("Verify SSL certificates", id="set-verify-ssl", value=False)
                    with Horizontal(classes="row"):
                        yield Static("Collaborator URL:", classes="row-label")
                        yield Input(
                            placeholder="https://xxx.oastify.com",
                            id="set-collaborator-url",
                            compact=True,
                        )
                    yield Static("─" * 40, classes="license-sep")
                    with Horizontal(classes="row"):
                        yield Static("Scan Marker Header:", classes="row-label")
                        yield Checkbox(
                            "Add custom header to all scan requests",
                            id="set-scan-marker-enabled",
                            value=False,
                        )
                    with Horizontal(classes="row"):
                        yield Static("Header Name:", classes="row-label")
                        yield Input(value="X-Scanner", id="set-scan-marker-name", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Header Value:", classes="row-label")
                        yield Input(value="pentool/1.0", id="set-scan-marker-value", compact=True)
                    yield ToolbarButton("Save", "settings-save-network")

            with TabPane("Privacy", id="tab-privacy"):
                with Vertical(classes="settings-pane"):
                    yield Static("Privacy & Updates", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("Crash Reporting:", classes="row-label")
                        yield Checkbox(
                            "Send anonymous crash reports",
                            id="set-send-crash-reports",
                            value=True,
                        )
                    yield Static(
                        "Crash reports contain only the error type and stack trace.\n"
                        "No URLs, IPs, tokens, or personal data are included.",
                        classes="settings-hint",
                    )
                    yield Static("─" * 40, classes="license-sep")
                    with Horizontal(classes="row"):
                        yield Static("Auto-update check:", classes="row-label")
                        yield Checkbox(
                            "Check for updates at startup",
                            id="set-check-updates",
                            value=True,
                        )
                    yield Static(
                        "Checks GitHub releases for a newer version on startup.\n"
                        "Run `pentool update` to install an available update.",
                        classes="settings-hint",
                    )
                    yield Static("─" * 40, classes="license-sep")
                    with Horizontal(classes="row"):
                        yield Static("Auto Scope:", classes="row-label")
                        yield Checkbox(
                            "Add hosts to scope automatically",
                            id="set-auto-scope",
                            value=False,
                        )
                    yield Static(
                        "When enabled: sending a request to Repeater, starting a crawl\n"
                        "or a scan will automatically add the target host to scope\n"
                        "and trigger tech detection. Disabled by default.",
                        classes="settings-hint",
                    )
                    yield ToolbarButton("Save", "settings-save-privacy")

            with TabPane("AI", id="tab-ai"):
                with Vertical(classes="settings-pane"):
                    yield Static("AI Assistant", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("AI Assistant:", classes="row-label")
                        yield Switch(id="set-ai-enabled", value=False)
                    yield Static(
                        "AI can help with scanning: picking checks, bypassing WAF, "
                        "searching for non-obvious endpoints.\n"
                        "Requires an installed LLM model. The MCP server is started "
                        "separately from the Dashboard or `pentool ai start`.",
                        classes="settings-hint",
                    )
                    yield Static("─" * 40, classes="license-sep")
                    with Horizontal(classes="row"):
                        yield Static("MCP port:", classes="row-label")
                        yield Input(placeholder="0 = stdio", id="set-ai-mcp-port", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Model:", classes="row-label")
                        yield Input(id="set-ai-model-path", compact=True)
                    yield Static(
                        "Path to the model's GGUF file. If empty, ~/.pentool/ai/models/ is used.",
                        classes="settings-hint",
                    )
                    # Commit 0f563b3 dropped this button when the enabled switch
                    # became live-saving, but _save_ai_settings() stayed behind
                    # the selector: MCP port and model path loaded from config
                    # and could never be written back. Same shape as the
                    # Intruder buttons lost in cb11bfd (test_on_selectors_resolve).
                    yield ToolbarButton("Save", "settings-save-ai")

            with TabPane("License", id="tab-license"):
                with Vertical(classes="settings-pane"):
                    yield Static("License", classes="section-title")
                    with Horizontal(classes="row"):
                        yield Static("Status:", classes="row-label")
                        yield Static("● FREE", id="license-status", classes="license-status-free")
                    with Horizontal(classes="row"):
                        yield Static("Plan:", classes="row-label")
                        yield Static("Free", id="license-plan")
                    with Horizontal(classes="row"):
                        yield Static("Expires:", classes="row-label")
                        yield Static("—", id="license-expires")
                    with Horizontal(classes="row"):
                        yield Static("Machine ID:", classes="row-label")
                        yield Static("", id="license-machine-id", classes="license-mono")
                    yield Static("─" * 40, classes="license-sep")
                    with Horizontal(classes="row"):
                        yield Static("License Key:", classes="row-label")
                        yield Input(
                            placeholder="XXXX-XXXX-XXXX-XXXX",
                            id="license-key-input",
                            compact=True,
                        )
                    with Horizontal(classes="license-buttons-row"):
                        yield ToolbarButton("Activate", "btn-license-activate")
                        yield ToolbarButton("Deactivate", "btn-license-deactivate")
                    yield Static("", id="license-error", classes="license-error")
                    yield Static("─" * 40, classes="license-sep")
                    yield Static("Features:", classes="license-features-title")
                    yield Static("", id="license-features")
                    yield Static(
                        "Buy PRO: https://pentool.pro/pricing",
                        id="license-buy-link",
                        classes="license-buy",
                    )

    def on_mount(self) -> None:
        self._load_current_config()
        self._refresh_license_ui()

    def _load_current_config(self) -> None:
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            self.query_one("#set-proxy-host", Input).value = cfg.proxy_host
            self.query_one("#set-proxy-port", Input).value = str(cfg.proxy_port)
        except Exception:
            # Поле останется пустым, а Save запишет пустую строку поверх
            # сохранённого хоста — то есть молчание здесь дороже, чем кажется.
            logger.warning("settings: proxy fields not prefilled", exc_info=True)
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            enabled = getattr(cfg, "auto_save_enabled", False)
            interval = getattr(cfg, "auto_save_interval", 5)
            self.query_one("#set-autosave-enabled", Checkbox).value = enabled
            self.query_one("#set-autosave-interval", Input).value = str(interval)
        except Exception:
            logger.warning("settings: auto-save fields not prefilled", exc_info=True)
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            self.query_one("#set-user-agent", Input).value = getattr(cfg, "default_user_agent", "")
            self.query_one("#set-req-timeout", Input).value = str(getattr(cfg, "request_timeout", 15))
            self.query_one("#set-conn-timeout", Input).value = str(getattr(cfg, "connect_timeout", 10))
            self.query_one("#set-max-redirects", Input).value = str(getattr(cfg, "max_redirects", 10))
            self.query_one("#set-verify-ssl", Checkbox).value = getattr(cfg, "verify_ssl", False)
            self.query_one("#set-collaborator-url", Input).value = getattr(cfg, "collaborator_url", "")
            self.query_one("#set-scan-marker-enabled", Checkbox).value = getattr(cfg, "scan_marker_enabled", False)
            self.query_one("#set-scan-marker-name", Input).value = getattr(cfg, "scan_marker_name", "X-Scanner")
            self.query_one("#set-scan-marker-value", Input).value = getattr(cfg, "scan_marker_value", "pentool/1.0")
        except Exception:
            # Девять полей в одном блоке: без записи не видно, что Save
            # отправит значения по умолчанию вместо сохранённых.
            logger.warning("settings: request/scan fields not prefilled", exc_info=True)
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            self.query_one("#set-send-crash-reports", Checkbox).value = getattr(cfg, "send_crash_reports", True)
            self.query_one("#set-check-updates", Checkbox).value = getattr(cfg, "check_updates", True)
            self.query_one("#set-auto-scope", Checkbox).value = getattr(cfg, "auto_scope", False)
        except Exception:
            logger.warning("settings: checkbox fields not prefilled", exc_info=True)
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            saved_theme = getattr(cfg, "theme", "textual-dark")
            cycler = self.query_one("#set-theme", OptionCycler)
            # Set OptionCycler to the saved theme value
            for label, val in self._THEMES:
                if val == saved_theme:
                    cycler.set_value(val)
                    break
            self.query_one("#set-tooltips", Checkbox).value = getattr(cfg, "tooltips_enabled", True)
            icons_val = getattr(cfg, "panel_icons", "unicode") or "unicode"
            icons_cycler = self.query_one("#set-panel-icons", OptionCycler)
            for _label, val in self._PANEL_ICONS:
                if val == icons_val:
                    icons_cycler.set_value(val)
                    break
        except Exception:
            # Циклер останется на первой теме списка, а сохранённая тема —
            # другой; без записи это выглядит как «настройка слетела».
            logger.warning("settings: theme cycler not prefilled", exc_info=True)

        # ── AI settings load ────────────────────────────────────────────────────────────
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            self.query_one("#set-ai-enabled", Switch).value = getattr(cfg, "ai_enabled", False)
            self.query_one("#set-ai-mcp-port", Input).value = str(getattr(cfg, "ai_mcp_port", 0) or 0)
            model_path = getattr(cfg, "ai_mcp_model_path", "") or ""
            if model_path:
                self.query_one("#set-ai-model-path", Input).value = model_path
        except Exception:
            logger.warning("settings: AI fields not prefilled", exc_info=True)

    # ── License UI ─────────────────────────────────────────────────────────────

    def _refresh_license_ui(self) -> None:
        try:
            from pentool.core.license import get_machine_id, get_session_license

            info = get_session_license()
            mid = get_machine_id()

            # Status
            status_w = self.query_one("#license-status", Static)
            plan_w = self.query_one("#license-plan", Static)
            exp_w = self.query_one("#license-expires", Static)
            mid_w = self.query_one("#license-machine-id", Static)
            feat_w = self.query_one("#license-features", Static)
            err_w = self.query_one("#license-error", Static)

            if info.valid and info.plan != "free":
                status_w.update("● PRO")
                status_w.remove_class("license-status-free")
                status_w.add_class("license-status-pro")
                plan_w.update(esc(info.plan.upper()))
                exp_w.update(esc(info.expires_text))
                feat_w.update("\n".join(f"  ✓ {esc(f)}" for f in info.features) if info.features else "  (none)")
            else:
                status_w.update("● FREE")
                status_w.remove_class("license-status-pro")
                status_w.add_class("license-status-free")
                plan_w.update("Free")
                exp_w.update("—")
                feat_w.update("  (activate PRO to unlock additional features)")

            mid_w.update(mid[:16] + "…" if len(mid) > 16 else mid)

            if info.error:
                err_w.update(f"[red]{esc(info.error)}[/red]")
                err_w.add_class("visible")
            else:
                err_w.update("")
                err_w.remove_class("visible")

            # Pre-fill key input if cached
            if info.license_key:
                try:
                    inp = self.query_one("#license-key-input", Input)
                    if not inp.value:
                        inp.value = info.license_key
                except NoMatches:
                    # Поле просто останется пустым — пользователю придётся
                    # ввести ключ заново; это не потеря, но и не норма.
                    logger.warning("settings: license key not prefilled", exc_info=True)
        except Exception:
            # Панель лицензии останется в состоянии, собранном в compose —
            # то есть покажет «FREE» независимо от того, что на диске.
            logger.warning("settings: license panel not refreshed", exc_info=True)

    @on(ToolbarButton.Pressed, "#settings-save")
    def on_btn_settings_save(self, _: ToolbarButton.Pressed) -> None:
        self._save_interface_settings()

    @on(ToolbarButton.Pressed, "#settings-save-proxy")
    def on_btn_settings_save_proxy(self, _: ToolbarButton.Pressed) -> None:
        self._save_proxy_settings()

    @on(ToolbarButton.Pressed, "#settings-save-project")
    def on_btn_settings_save_project(self, _: ToolbarButton.Pressed) -> None:
        self._save_project_settings()

    @on(ToolbarButton.Pressed, "#settings-save-network")
    def on_btn_settings_save_network(self, _: ToolbarButton.Pressed) -> None:
        self._save_network_settings()

    @on(ToolbarButton.Pressed, "#settings-save-privacy")
    def on_btn_settings_save_privacy(self, _: ToolbarButton.Pressed) -> None:
        self._save_privacy_settings()

    @on(ToolbarButton.Pressed, "#settings-save-ai")
    def on_btn_settings_save_ai(self, _: ToolbarButton.Pressed) -> None:
        self._save_ai_settings()

    @on(ToolbarButton.Pressed, "#btn-license-activate")
    def on_btn_license_activate(self, _: ToolbarButton.Pressed) -> None:
        self._do_activate_license()

    @on(ToolbarButton.Pressed, "#btn-license-deactivate")
    def on_btn_license_deactivate(self, _: ToolbarButton.Pressed) -> None:
        self._do_deactivate_license()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "settings-open-ca":
            self._open_ca_cert()

    def on_option_cycler_changed(self, event: OptionCycler.Changed) -> None:
        # Determine the event source via event.control (returns the OptionCycler)
        try:
            widget = event.control
            wid = widget.id if widget else None
        except Exception:
            # Без id не сработает ни одна ветка — то есть переключение темы и
            # режима UI молча перестанет применяться. `event.control` —
            # свойство Textual, и падать там может только сам фреймворк, так
            # что причина должна остаться целиком.
            logger.exception("settings: cycler event source unknown")
            wid = None

        if wid == "set-theme":
            # Debounced live preview — does NOT save to config until Save is clicked.
            self._apply_theme_debounced(event.value)
        elif wid == "set-ui-mode":
            try:
                self._apply_ui_mode(UIMode(event.value))
            except ValueError as exc:
                # Значение из списка, которого нет в UIMode: режим останется
                # прежним. Молча — это выглядит как «переключатель не работает».
                logger.debug("settings: UI mode %r not applied: %s", event.value, exc)

    def _apply_theme_debounced(self, theme: str) -> None:
        """Schedule a theme preview after a short debounce (150 ms).

        Cancels any pending timer so rapid OptionCycler clicks do not fire
        refresh_css() on every click — only after the user settles on a value.
        """
        if self._theme_debounce is not None:
            try:
                self._theme_debounce.stop()
            except Exception:
                # Таймер уже сработал — его нечего останавливать. Ссылку всё
                # равно обнуляем ниже, поэтому здесь достаточно следа.
                logger.warning("settings: theme debounce timer already gone", exc_info=True)
            self._theme_debounce = None
        # set_timer fires once after the delay
        self._theme_debounce = self.set_timer(0.15, lambda: self._do_apply_theme(theme))

    def _do_apply_theme(self, theme: str) -> None:
        """Actually set app.theme — called after the debounce delay fires.

        Does NOT save to config; saving happens only when the user clicks Save
        so that we don't spam sync file-IO on every click.
        """
        self._theme_debounce = None
        try:
            # Guard: skip if Textual already has this theme (avoids double refresh_css).
            if getattr(self.app, "theme", None) != theme:
                self.app.theme = theme  # type: ignore[attr-defined]
        except Exception as exc:
            # Пользователь кликнул тему и ждёт предпросмотра; отказ Textual
            # принять имя темы иначе не виден вообще.
            logger.debug("settings: theme preview %r not applied: %s", theme, exc)

    def _apply_theme(self, theme: str) -> None:
        """Apply theme immediately (no debounce) and persist to config via async worker.

        Called only from _save_interface_settings (the Save button), so it is
        safe to do both the Textual theme switch and the config write here.
        """
        try:
            if getattr(self.app, "theme", None) != theme:
                self.app.theme = theme  # type: ignore[attr-defined]
        except InvalidThemeError as exc:
            # Save уже записал тему в конфиг — то есть файл и экран разойдутся.
            logger.debug("settings: theme %r not applied on save: %s", theme, exc)
        # Persist in a thread worker so yaml.dump + file.write don't block the event loop.
        self.run_worker(self._async_save_theme(theme), exclusive=False, thread=False)

    async def _async_save_theme(self, theme: str) -> None:
        """Write the theme to config on a thread so disk IO doesn't stall the UI."""
        import asyncio

        loop = asyncio.get_running_loop()
        try:
            from pentool.core.config import get_config

            def _save() -> None:
                get_config().update(theme=theme)
                get_config().save()

            await loop.run_in_executor(None, _save)
        except Exception as exc:
            # Тема применена на экране, но не попала в config.yaml — после
            # перезапуска вернётся прежняя. Пользователь этого не увидит.
            logger.warning("settings: theme %r not saved to disk: %s", theme, exc)

    def _save_interface_settings(self) -> None:
        """Apply theme and UI mode, then persist to config asynchronously."""
        # Apply theme (immediate + async save)
        try:
            theme_val = self.query_one("#set-theme", OptionCycler).value
            self._apply_theme(theme_val)
        except NoMatches:
            # Ниже всё равно покажем «applied» — поэтому запись единственное
            # место, где видно, что применилось не всё. Поля темы нет в дереве.
            logger.warning("settings: theme not read on save", exc_info=True)
        except Exception:
            # Поле есть, но тема не применилась: конфиг сохранён, экран — нет.
            logger.exception("settings: theme not applied on save")

        # Apply UI mode (no config write needed — ModuleTabs handles it)
        try:
            mode_val = self.query_one("#set-ui-mode", OptionCycler).value
            self._apply_ui_mode(UIMode(mode_val))
        except NoMatches:
            logger.warning("settings: UI mode selector not found on save", exc_info=True)
        except ValueError as exc:
            # В поле режима значение вне UIMode — вкладки останутся прежними,
            # хотя «applied» уже показано.
            logger.debug("settings: UI mode %r not applied on save: %s", mode_val, exc)

        self.app.notify("Interface settings applied", timeout=2)  # type: ignore[attr-defined]

    def _apply_ui_mode(self, mode: UIMode) -> None:
        """Show/hide tabs depending on the complexity mode."""
        try:
            from pentool.tui.widgets.module_tabs import ModuleTabs

            tabs_widget = self.app.query_one(ModuleTabs)  # type: ignore[attr-defined]
            tabs_widget.set_mode(mode.value)
        except NoMatches as exc:
            # Набор вкладок останется прежним: пользователь выбрал Advanced, а
            # вкладки не появились — «переключатель не работает». Вкладок нет
            # в дереве (приложение ещё собирается или уже разбирается).
            logger.debug("settings: module tabs mode %r not applied: %s", mode.value, exc)

    async def _async_save_config(self, changes: dict, notify_msg: str) -> None:
        """Apply *changes* to config and flush to disk in an executor thread.

        Using run_in_executor keeps yaml.dump + file.write off the event loop so
        the UI stays responsive during saves.
        """
        import asyncio

        try:
            from pentool.core.config import get_config

            cfg = get_config()
            loop = asyncio.get_running_loop()

            def _do_save() -> None:
                if changes:
                    cfg.update(**changes)
                cfg.save()

            await loop.run_in_executor(None, _do_save)
            self.app.notify(notify_msg, timeout=2)  # type: ignore[attr-defined]
        except Exception as e:
            err(e, "Save failed", self)

    # ── Generic settings save helper ──────────────────────────────────────────

    def _save_settings(self, changes: dict, msg: str) -> None:
        """Fire an async save worker with *changes* and *msg*.

        Shared by the per-section save methods to eliminate the 5× clone of the
        try/cfg/run_worker pattern.
        """
        if not changes:
            return
        self.run_worker(
            self._async_save_config(changes, msg),
            exclusive=False,
            thread=False,
        )

    def _collect_proxy_changes(self) -> dict:
        from pentool.core.config import get_config

        cfg = get_config()
        host = self.query_one("#set-proxy-host", Input).value.strip()
        port_str = self.query_one("#set-proxy-port", Input).value.strip()
        changes: dict = {}
        if host and host != cfg.proxy_host:
            changes["proxy_host"] = host
        if port_str.isdigit() and int(port_str) != cfg.proxy_port:
            changes["proxy_port"] = int(port_str)
        return changes

    def _save_proxy_settings(self) -> None:
        try:
            self._save_settings(self._collect_proxy_changes(), "Proxy settings saved (restart proxy to apply)")
        except Exception as e:
            err(e, "Save failed", self)

    def _save_project_settings(self) -> None:
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            changes: dict = {}
            try:
                enabled = self.query_one("#set-autosave-enabled", Checkbox).value
                if enabled != getattr(cfg, "auto_save_enabled", False):
                    changes["auto_save_enabled"] = enabled
            except Exception:
                # Поле не прочитано — значит, его новое значение не сохранится,
                # а уведомление ниже всё равно скажет «saved».
                logger.warning("settings: auto_save_enabled not collected", exc_info=True)
            try:
                interval_str = self.query_one("#set-autosave-interval", Input).value.strip()
                if interval_str.isdigit():
                    interval = max(1, int(interval_str))
                    if interval != getattr(cfg, "auto_save_interval", 5):
                        changes["auto_save_interval"] = interval
            except Exception:
                logger.warning("settings: auto_save_interval not collected", exc_info=True)
            self._save_settings(changes, "Project settings saved")
        except Exception as e:
            err(e, "Save failed", self)

    def _open_ca_cert(self) -> None:
        try:
            from pentool.tui.screens.proxy.screen import ProxyScreen

            proxy_screen = self.app.require_module_screen("proxy", ProxyScreen)
            proxy_screen.action_open_ca_cert()
        except Exception as e:
            err(e, "Install CA cert failed", self)

    def _save_network_settings(self) -> None:
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            changes: dict = {}

            try:
                ua = self.query_one("#set-user-agent", Input).value.strip()
                if ua and ua != cfg.default_user_agent:
                    changes["default_user_agent"] = ua
            except Exception:
                logger.warning("settings: default_user_agent not collected", exc_info=True)

            try:
                req_str = self.query_one("#set-req-timeout", Input).value.strip()
                if req_str.isdigit():
                    v = max(1, int(req_str))
                    if v != cfg.request_timeout:
                        changes["request_timeout"] = v
            except Exception:
                logger.warning("settings: request_timeout not collected", exc_info=True)

            try:
                conn_str = self.query_one("#set-conn-timeout", Input).value.strip()
                if conn_str.isdigit():
                    v = max(1, int(conn_str))
                    if v != cfg.connect_timeout:
                        changes["connect_timeout"] = v
            except Exception:
                logger.warning("settings: connect_timeout not collected", exc_info=True)

            try:
                redir_str = self.query_one("#set-max-redirects", Input).value.strip()
                if redir_str.isdigit():
                    v = max(0, int(redir_str))
                    if v != cfg.max_redirects:
                        changes["max_redirects"] = v
            except Exception:
                logger.warning("settings: max_redirects not collected", exc_info=True)

            try:
                ssl_v = self.query_one("#set-verify-ssl", Checkbox).value
                if ssl_v != cfg.verify_ssl:
                    changes["verify_ssl"] = ssl_v
            except NoMatches:
                logger.warning("settings: verify_ssl not collected", exc_info=True)

            # Интерфейс: подсказки и набор иконок. Собираются здесь же, чтобы
            # уходить общим путём сохранения (свой `cfg.save()` в тестах писал
            # в реальный config.yaml и ломал изоляцию).
            try:
                hints_v = self.query_one("#set-tooltips", Checkbox).value
                if hints_v != getattr(cfg, "tooltips_enabled", True):
                    changes["tooltips_enabled"] = bool(hints_v)
            except NoMatches:
                logger.warning("settings: tooltips field not collected", exc_info=True)
            try:
                icons_v = self.query_one("#set-panel-icons", OptionCycler).value
                if icons_v != getattr(cfg, "panel_icons", "unicode"):
                    changes["panel_icons"] = str(icons_v)
            except NoMatches:
                logger.warning("settings: panel icons field not collected", exc_info=True)

            try:
                collab = self.query_one("#set-collaborator-url", Input).value.strip()
                if collab != cfg.collaborator_url:
                    changes["collaborator_url"] = collab
            except Exception:
                logger.warning("settings: collaborator_url not collected", exc_info=True)

            try:
                marker_en = self.query_one("#set-scan-marker-enabled", Checkbox).value
                if marker_en != cfg.scan_marker_enabled:
                    changes["scan_marker_enabled"] = marker_en
                marker_name = self.query_one("#set-scan-marker-name", Input).value.strip()
                if marker_name and marker_name != cfg.scan_marker_name:
                    changes["scan_marker_name"] = marker_name
                marker_val = self.query_one("#set-scan-marker-value", Input).value.strip()
                if marker_val != cfg.scan_marker_value:
                    changes["scan_marker_value"] = marker_val
            except Exception:
                logger.warning("settings: scan-marker fields not collected", exc_info=True)

            self._save_settings(changes, "Network settings saved")
        except Exception as e:
            err(e, "Save failed", self)

    def _save_privacy_settings(self) -> None:
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            changes: dict = {}

            try:
                crash_v = self.query_one("#set-send-crash-reports", Checkbox).value
                if crash_v != getattr(cfg, "send_crash_reports", True):
                    changes["send_crash_reports"] = crash_v
            except Exception:
                logger.warning("settings: send_crash_reports not collected", exc_info=True)

            try:
                upd_v = self.query_one("#set-check-updates", Checkbox).value
                if upd_v != getattr(cfg, "check_updates", True):
                    changes["check_updates"] = upd_v
            except Exception:
                logger.warning("settings: check_updates not collected", exc_info=True)

            try:
                scope_v = self.query_one("#set-auto-scope", Checkbox).value
                if scope_v != getattr(cfg, "auto_scope", False):
                    changes["auto_scope"] = scope_v
            except Exception:
                logger.warning("settings: auto_scope not collected", exc_info=True)

            self._save_settings(changes, "Privacy settings saved")
        except Exception as e:
            err(e, "Save failed", self)

    @on(Switch.Changed, "#set-ai-enabled")
    def _on_ai_switch_changed(self, event: Switch.Changed) -> None:
        """Live-save at switch toggle — сохраняет только ai_enabled."""
        changes = {"ai_enabled": event.switch.value}
        self._save_settings(changes, "AI toggled")

    def _save_ai_settings(self) -> None:
        """Save the AI settings."""
        try:
            from pentool.services.ai.factory import AI_MODELS_DIR

            cfg = getattr(self.app, "_cfg", None)
            if cfg is None:
                self.err(Exception("Config not loaded"), "Config not loaded")
                return

            changes: dict[str, object] = {}
            try:
                port_v = self.query_one("#set-ai-mcp-port", Input).value.strip()
                changes["ai_mcp_port"] = int(port_v) if port_v else 0
            except Exception:
                # Порт остаётся прежним, хотя пользователь его менял: молчание
                # превращает это в «настройка не сохранилась».
                logger.warning("settings: ai_mcp_port not collected", exc_info=True)
            try:
                model_v = self.query_one("#set-ai-model-path", Input).value.strip()
                if model_v:
                    changes["ai_mcp_model_path"] = model_v
                elif AI_MODELS_DIR.exists():
                    models = list(AI_MODELS_DIR.iterdir())
                    if models:
                        changes["ai_mcp_model_path"] = str(models[0])
            except Exception:
                logger.warning("settings: ai_mcp_model_path not collected", exc_info=True)

            self._save_settings(changes, "AI settings saved")
        except Exception as e:
            err(e, "Save failed", self)

    # ── License actions ────────────────────────────────────────────────────────

    def _do_activate_license(self) -> None:
        try:
            key = self.query_one("#license-key-input", Input).value.strip()
        except NoMatches:
            # Пустой ключ ниже даст понятное «Enter a license key first» —
            # это правильный пользовательский исход, но причина другая.
            logger.warning("settings: license key input unreadable", exc_info=True)
            key = ""
        if not key:
            self.app.notify("Enter a license key first", severity="warning", timeout=3)  # type: ignore[attr-defined]
            return
        self.run_worker(self._async_activate(key), exclusive=True, name="license-activate")

    async def _async_activate(self, key: str) -> None:
        """Async activation worker."""
        from pentool.core.license import activate_license, reassign_license, refresh_session_license

        self.app.notify("Activating license…", timeout=2)  # type: ignore[attr-defined]
        try:
            info = await activate_license(key)
            if not info.valid and ("slots in use" in info.error or "bound to another machine" in info.error):
                # Предложить сбросить старую привязку
                from pentool.tui.dialogs.confirm import ConfirmDialog

                confirmed = await self.app.push_screen_widget(  # type: ignore[attr-defined]
                    ConfirmDialog(
                        title="License already in use",
                        message=(
                            f"This key is already activated on another machine.\n\n"
                            f"{esc(info.error)}\n\n"
                            "Do you want to deactivate the old machine and "
                            "activate this one instead?"
                        ),
                        confirm_text="Yes, reassign to this machine",
                        cancel_text="Cancel",
                    )
                )
                if confirmed:
                    self.app.notify("Reassigning license…", timeout=2)  # type: ignore[attr-defined]
                    info = await reassign_license(key)
                else:
                    refresh_session_license(info)
                    self.call_after_refresh(self._refresh_license_ui)
                    return
            refresh_session_license(info)
            if info.valid:
                plan = esc(info.plan.upper())
                self.app.notify(f"✓ License activated: {plan}", timeout=4)  # type: ignore[attr-defined]
            else:
                self.err(Exception(info.error), "License activation failed")
        except Exception as exc:
            err(exc, "License activation failed", self)
        self.call_after_refresh(self._refresh_license_ui)

    def _do_deactivate_license(self) -> None:
        """Deactivate the license online (notify server then remove cached data)."""
        self.run_worker(self._async_deactivate(), exclusive=True, name="license-deactivate")

    async def _async_deactivate(self) -> None:
        """Async deactivation worker."""
        from pentool.core.license import deactivate_license, refresh_session_license

        self.app.notify("Deactivating license…", timeout=2)  # type: ignore[attr-defined]
        try:
            await deactivate_license()
            refresh_session_license()
            self.app.notify("✓ License deactivated", timeout=3)  # type: ignore[attr-defined]
        except Exception as exc:
            err(exc, "Deactivation error", self)
        self.call_after_refresh(self._refresh_license_ui)
