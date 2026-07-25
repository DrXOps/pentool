"""Экран настроек приложения."""

from __future__ import annotations

from enum import Enum

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from pathlib import Path

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Static,
    TabbedContent,
    TabPane,
)

from pentool.tui.screens.settings.hotkeys import HotkeySettingsScreen
from pentool.tui.widgets.toolbar_button import ToolbarButton


class UIMode(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"


class OptionCycler(Static):
    """Кнопка-переключатель опций — клик циклически меняет значение."""

    DEFAULT_CSS = _CSS

    class Changed(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, options: list[tuple[str, str]], initial: str = "", **kwargs) -> None:
        """options: list of (label, value)"""
        super().__init__("", **kwargs)
        self._options = options  # [(label, value), ...]
        self._idx = 0
        for i, (_, v) in enumerate(options):
            if v == initial:
                self._idx = i
                break

    def on_mount(self) -> None:
        self._update_label()

    def _update_label(self) -> None:
        label, _ = self._options[self._idx]
        self.update(label)

    @property
    def value(self) -> str:
        _, v = self._options[self._idx]
        return v

    def set_value(self, value: str) -> None:
        for i, (_, v) in enumerate(self._options):
            if v == value:
                self._idx = i
                self._update_label()
                return

    def on_click(self) -> None:
        self._idx = (self._idx + 1) % len(self._options)
        self._update_label()
        self.post_message(self.Changed(self.value))


class SettingsScreen(Widget):
    """Диалог настроек: Interface / Proxy / Hotkeys / Project.

    Монтируется как обычный экран-виджет; открывается через ContentSwitcher.
    """

    DEFAULT_CSS = _CSS

    _THEMES = [("Dark", "dark"), ("Light", "light")]
    _MODES = [("Advanced", "advanced"), ("Basic", "basic")]

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
                        yield Static("Auto-save path:", classes="row-label")
                        yield Input(placeholder="project.json", id="set-autosave-path", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Auto-save interval:", classes="row-label")
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
                        yield Checkbox("Add custom header to all scan requests", id="set-scan-marker-enabled", value=False)
                    with Horizontal(classes="row"):
                        yield Static("Header Name:", classes="row-label")
                        yield Input(value="X-Scanner", id="set-scan-marker-name", compact=True)
                    with Horizontal(classes="row"):
                        yield Static("Header Value:", classes="row-label")
                        yield Input(value="pentool/1.0", id="set-scan-marker-value", compact=True)
                    yield ToolbarButton("Save", "settings-save-network")

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
                        "Buy PRO: https://pentool.dev/pricing",
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
            pass
        try:
            from pentool.core.config import get_config
            cfg = get_config()
            enabled = getattr(cfg, "auto_save_enabled", False)
            interval = getattr(cfg, "auto_save_interval", 5)
            self.query_one("#set-autosave-enabled", Checkbox).value = enabled
            self.query_one("#set-autosave-interval", Input).value = str(interval)
        except Exception:
            pass
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
            pass

    # ── License UI ─────────────────────────────────────────────────────────────

    def _refresh_license_ui(self) -> None:
        try:
            from pentool.core.license import get_session_license, get_machine_id
            info = get_session_license()
            mid = get_machine_id()

            # Status
            status_w = self.query_one("#license-status", Static)
            plan_w   = self.query_one("#license-plan", Static)
            exp_w    = self.query_one("#license-expires", Static)
            mid_w    = self.query_one("#license-machine-id", Static)
            feat_w   = self.query_one("#license-features", Static)
            err_w    = self.query_one("#license-error", Static)

            if info.valid and info.plan != "free":
                status_w.update("● PRO")
                status_w.remove_class("license-status-free")
                status_w.add_class("license-status-pro")
                plan_w.update(info.plan.upper())
                exp_w.update(info.expires_text)
                feat_w.update("\n".join(f"  ✓ {f}" for f in info.features) if info.features else "  (none)")
            else:
                status_w.update("● FREE")
                status_w.remove_class("license-status-pro")
                status_w.add_class("license-status-free")
                plan_w.update("Free")
                exp_w.update("—")
                feat_w.update("  (activate PRO to unlock additional features)")

            mid_w.update(mid[:16] + "…" if len(mid) > 16 else mid)

            if info.error:
                err_w.update(f"[red]{info.error}[/red]")
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
                except Exception:
                    pass
        except Exception:
            pass

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
        # Определяем источник события по иерархии widget
        try:
            # event.control — источник сообщения (стандартный атрибут Textual Message)
            widget = event.control  # type: ignore[attr-defined]
            wid = widget.id if widget else None
        except Exception:
            wid = None

        if wid == "set-theme":
            self._apply_theme(event.value)
        elif wid == "set-ui-mode":
            try:
                self._apply_ui_mode(UIMode(event.value))
            except Exception:
                pass

    def _apply_theme(self, theme: str) -> None:
        try:
            self.app.dark = (theme == "dark")  # type: ignore[attr-defined]
        except Exception:
            pass

    def _save_interface_settings(self) -> None:
        """Применить тему и UI-режим и сохранить в конфиг."""
        # Применяем тему
        try:
            theme_val = self.query_one("#set-theme", OptionCycler).value
            self._apply_theme(theme_val)
        except Exception:
            pass

        # Применяем UI-режим
        try:
            mode_val = self.query_one("#set-ui-mode", OptionCycler).value
            self._apply_ui_mode(UIMode(mode_val))
        except Exception:
            pass

        self.app.notify("Interface settings applied", timeout=2)  # type: ignore[attr-defined]

    def _apply_ui_mode(self, mode: UIMode) -> None:
        """Показать/скрыть вкладки в зависимости от режима сложности."""
        try:
            from pentool.tui.widgets.module_tabs import ModuleTabs
            tabs_widget = self.app.query_one(ModuleTabs)  # type: ignore[attr-defined]
            tabs_widget.set_mode(mode.value)
        except Exception:
            pass

    def _save_proxy_settings(self) -> None:
        try:
            from pentool.core.config import get_config
            cfg = get_config()
            host = self.query_one("#set-proxy-host", Input).value.strip()
            port_str = self.query_one("#set-proxy-port", Input).value.strip()
            changes: dict = {}
            if host and host != cfg.proxy_host:
                changes["proxy_host"] = host
            if port_str.isdigit() and int(port_str) != cfg.proxy_port:
                changes["proxy_port"] = int(port_str)
            if changes:
                cfg.update(**changes)
            cfg.save()
            self.app.notify("Proxy settings saved (restart proxy to apply)", timeout=3)  # type: ignore[attr-defined]
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error", timeout=4)  # type: ignore[attr-defined]

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
                pass
            try:
                interval_str = self.query_one("#set-autosave-interval", Input).value.strip()
                if interval_str.isdigit():
                    interval = max(1, int(interval_str))
                    if interval != getattr(cfg, "auto_save_interval", 5):
                        changes["auto_save_interval"] = interval
            except Exception:
                pass
            if changes:
                cfg.update(**changes)
            cfg.save()
            self.app.notify("Project settings saved", timeout=2)  # type: ignore[attr-defined]
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error", timeout=4)  # type: ignore[attr-defined]

    def _open_ca_cert(self) -> None:
        try:
            self.app.action_open_ca_cert()  # type: ignore[attr-defined]
        except Exception:
            pass

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
                pass

            try:
                req_str = self.query_one("#set-req-timeout", Input).value.strip()
                if req_str.isdigit():
                    v = max(1, int(req_str))
                    if v != cfg.request_timeout:
                        changes["request_timeout"] = v
            except Exception:
                pass

            try:
                conn_str = self.query_one("#set-conn-timeout", Input).value.strip()
                if conn_str.isdigit():
                    v = max(1, int(conn_str))
                    if v != cfg.connect_timeout:
                        changes["connect_timeout"] = v
            except Exception:
                pass

            try:
                redir_str = self.query_one("#set-max-redirects", Input).value.strip()
                if redir_str.isdigit():
                    v = max(0, int(redir_str))
                    if v != cfg.max_redirects:
                        changes["max_redirects"] = v
            except Exception:
                pass

            try:
                ssl_v = self.query_one("#set-verify-ssl", Checkbox).value
                if ssl_v != cfg.verify_ssl:
                    changes["verify_ssl"] = ssl_v
            except Exception:
                pass

            try:
                collab = self.query_one("#set-collaborator-url", Input).value.strip()
                if collab != cfg.collaborator_url:
                    changes["collaborator_url"] = collab
            except Exception:
                pass

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
                pass

            if changes:
                cfg.update(**changes)
            cfg.save()
            self.app.notify("Network settings saved", timeout=2)  # type: ignore[attr-defined]
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error", timeout=4)  # type: ignore[attr-defined]

    # ── License actions ────────────────────────────────────────────────────────

    def _do_activate_license(self) -> None:
        try:
            key = self.query_one("#license-key-input", Input).value.strip()
        except Exception:
            key = ""
        if not key:
            self.app.notify("Enter a license key first", severity="warning", timeout=3)  # type: ignore[attr-defined]
            return
        self.run_worker(self._async_activate(key), exclusive=True, name="license-activate")

    async def _async_activate(self, key: str) -> None:
        """Асинхронный воркер активации."""
        from pentool.core.license import activate_license, refresh_session_license
        self.app.notify("Activating license…", timeout=2)  # type: ignore[attr-defined]
        try:
            info = await activate_license(key)
            refresh_session_license(info)
            if info.valid:
                self.app.notify(f"✓ License activated: {info.plan.upper()}", timeout=4)  # type: ignore[attr-defined]
            else:
                self.app.notify(f"✗ Activation failed: {info.error}", severity="error", timeout=5)  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"✗ Error: {exc}", severity="error", timeout=5)  # type: ignore[attr-defined]
        self.call_after_refresh(self._refresh_license_ui)

    def _do_deactivate_license(self) -> None:
        """Деактивировать лицензию (удалить кэш)."""
        from pentool.core.license import deactivate_license, refresh_session_license
        try:
            deactivate_license()
            refresh_session_license()
            self.app.notify("License deactivated", timeout=3)  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"Deactivation error: {exc}", severity="error", timeout=4)  # type: ignore[attr-defined]
        self._refresh_license_ui()
