"""Application configuration management."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "pentool"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"
LOGS_DIR = DEFAULT_CONFIG_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Callback type: called when config changes
ConfigObserver = Callable[[dict], None]


@dataclass
class Config:
    """Application configuration with default values."""

    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8080
    cert_dir: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "certs"))
    db_path: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "pentool.db"))
    log_file: str = field(default_factory=lambda: str(LOGS_DIR / "pentool.log"))
    log_level: str = "INFO"
    plugins_dir: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "plugins"))
    scope: list[str] = field(default_factory=list)
    intercept_enabled: bool = False
    #: Directory for projects created by `--url` runs and `pentool project`. Lives next to
    #: the config file when `--config` points elsewhere (see `Config.load`).
    projects_dir: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "projects"))
    # Proxy backend: 'daemon' (isolated subprocess, default) or 'memory'
    # (legacy ProxyServer on a daemon thread in the TUI process — fallback).
    proxy_engine: str = "daemon"
    recent_projects: list[str] = field(default_factory=list)
    auto_save_enabled: bool = True
    auto_save_interval: int = 2  # minutes
    # ── Network / Scanner settings ─────────────────────────────────────────────
    default_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    request_timeout: int = 15  # seconds
    connect_timeout: int = 10  # seconds
    collaborator_url: str = ""  # Burp Collaborator / interactsh URL
    max_redirects: int = 10
    verify_ssl: bool = False  # verify SSL certificates in scanner
    # ── Scanner request marking ─────────────────────────────────────────────────
    scan_marker_enabled: bool = False
    scan_marker_name: str = "X-Scanner"
    scan_marker_value: str = "pentool/1.0"
    # ── Crash Reporting / Update Checker ────────────────────────────────────────
    send_crash_reports: bool = True  # send anonymous crash reports
    check_updates: bool = True  # check for updates on startup
    # ── UI ────────────────────────────────────────────────────────────────────────
    theme: str = "textual-dark"  # Textual theme name
    #: Remembered static sub-tab per module: {"utils": "utils-sequencer", ...}.
    #: Written by `tui/widgets/static_tabs.py`; unknown values fall back to the first pane.
    last_subtabs: dict[str, str] = field(default_factory=dict)
    notifications_sound_enabled: bool = True  # play a short sound with customnotify() toasts

    # ── AI ────────────────────────────────────────────────────────────────────────
    ai_enabled: bool = False  # master switch for the AI assistant

    # Interface: hover tooltips and the icon set used in panels.
    # Icons: unicode (default) | ascii | emoji — font coverage
    # differs between terminals, so the set is chosen in Settings → Interface.
    tooltips_enabled: bool = True
    panel_icons: str = "unicode"
    # Resize handle thickness in cells — the same for both orientations,
    # otherwise the vertical and horizontal ones look different.
    resize_handle_thickness: int = 1
    ai_model: str = ""  # LLM model name / path (GGUF)
    ai_mcp_host: str = "127.0.0.1"  # MCP server host
    ai_mcp_port: int = 0  # 0 = stdio, >0 = TCP
    ai_mcp_model_path: str = ""  # path to the GGUF file
    ai_mcp_auto_start: bool = False  # auto-start the MCP server when pentool launches
    # Debug — verbose logging of the scan pipeline and the AI worker
    scan_debug: bool = False  # show/hide the verbose scan output
    # Auto-Scope — add the host to Scope automatically when sending to a module
    auto_scope: bool = False  # when True — the host from the context menu goes to Scope

    # ── Per-module logging rules (NamedLogger) ──────────────────────────────────
    logging_rules: dict[str, str] = field(default_factory=dict)

    # Observer list — not serialized
    _observers: list[ConfigObserver] = field(default_factory=list, init=False, repr=False, compare=False)
    #: File this config was loaded from, so `save()` writes back to it instead of the
    #: default path (a `--config /tmp/run/config.yaml` run must not edit the user's file).
    _source_path: Path | None = field(default=None, init=False, repr=False, compare=False)

    def add_observer(self, cb: ConfigObserver) -> None:
        """Subscribe to configuration changes.

        Args:
            cb: Function of form cb(changed_fields: dict) -> None.
        """
        if cb not in self._observers:
            self._observers.append(cb)

    def remove_observer(self, cb: ConfigObserver) -> None:
        """Unsubscribe from configuration changes."""
        try:
            self._observers.remove(cb)
        except ValueError:
            pass

    def notify_observers(self, changed_fields: dict) -> None:
        """Notify all observers about changes.

        Args:
            changed_fields: Dict of changed fields {name: new_value}.
        """
        for cb in list(self._observers):
            try:
                cb(changed_fields)
            except Exception:
                pass

    def update(self, **kwargs: Any) -> None:
        changed: dict = {}
        for key, value in kwargs.items():
            if hasattr(self, key) and not key.startswith("_"):
                if getattr(self, key) != value:
                    setattr(self, key, value)
                    changed[key] = value
        if changed:
            self.notify_observers(changed)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization.

        Uses dataclasses.fields() so every field is included automatically —
        no more manual enumeration that drifts out of sync (the bug that caused
        ai_* and scan_debug fields to be duplicated here).
        Excludes _observers (not serializable — contains weakrefs/callbacks).
        """
        import dataclasses as _dc

        return {f.name: getattr(self, f.name) for f in _dc.fields(self) if not f.name.startswith("_")}

    def add_recent_project(self, path: str) -> None:
        path = str(path)
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[:10]
        try:
            self.save()
        except Exception:
            pass

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else (self._source_path or DEFAULT_CONFIG_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)

    #: Paths that follow the config file when `--config` points outside the default dir.
    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "Config":
        target = Path(path)
        cfg = cls()
        # An explicitly supplied config file makes the run self-contained: paths that
        # still hold their built-in `~/.config/pentool/...` value move next to the file,
        # so `--config /tmp/run/config.yaml` stops writing state into the user's home.
        # Values written in the file always win (applied below).
        default_cfg = cls()
        if target.resolve() != DEFAULT_CONFIG_PATH.resolve():
            base = target.resolve().parent
            relocated = {
                "db_path": base / "pentool.db",
                "cert_dir": base / "certs",
                "plugins_dir": base / "plugins",
                "log_file": base / "logs" / "pentool.log",
                "projects_dir": base / "projects",
            }
            for name, value in relocated.items():
                if getattr(cfg, name) == getattr(default_cfg, name):
                    setattr(cfg, name, str(value))
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
            for key, value in data.items():
                if hasattr(cfg, key) and not key.startswith("_"):
                    setattr(cfg, key, value)
        cfg._source_path = target
        # Normalize proxy backend — tolerate junk/legacy values in config.yaml
        if cfg.proxy_engine not in ("daemon", "memory"):
            cfg.proxy_engine = "daemon"
        # Remove non-existent paths from recent_projects on load
        before = len(cfg.recent_projects)
        cfg.recent_projects = [p for p in cfg.recent_projects if os.path.exists(p)]
        if len(cfg.recent_projects) != before:
            try:
                cfg.save()
            except Exception:  # logging-ok: optional list cleanup, it repeats on the next load
                pass
        return cfg


# Global config instance (initialized on startup)
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config) -> None:
    global _config
    _config = config


@contextmanager
def override_config(config: Config | None):
    """Context manager: temporarily replace global config singleton, restore on exit."""
    global _config
    prev = _config
    _config = config
    try:
        yield _config
    finally:
        _config = prev
