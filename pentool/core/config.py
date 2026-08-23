"""Application configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "pentool"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"

# Callback type: called when config changes
ConfigObserver = Callable[[dict], None]


@dataclass
class Config:
    """Application configuration with default values."""

    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8080
    cert_dir: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "certs"))
    db_path: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "pentool.db"))
    log_file: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "pentool.log"))
    log_level: str = "INFO"
    plugins_dir: str = field(default_factory=lambda: str(DEFAULT_CONFIG_DIR / "plugins"))
    scope: list[str] = field(default_factory=list)
    intercept_enabled: bool = False
    recent_projects: list[str] = field(default_factory=list)
    auto_save_enabled: bool = False
    auto_save_interval: int = 5  # minutes
    # ── Network / Scanner settings ─────────────────────────────────────────────
    default_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    request_timeout: int = 15         # seconds
    connect_timeout: int = 10         # seconds
    collaborator_url: str = ""        # Burp Collaborator / interactsh URL
    max_redirects: int = 10
    verify_ssl: bool = False          # verify SSL certificates in scanner
    # ── Scanner request marking ─────────────────────────────────────────────────
    scan_marker_enabled: bool = False
    scan_marker_name: str = "X-Scanner"
    scan_marker_value: str = "pentool/1.0"
    # ── Crash Reporting / Update Checker ────────────────────────────────────────
    send_crash_reports: bool = True   # send anonymous crash reports
    check_updates: bool = True        # check for updates on startup
    # ── UI ────────────────────────────────────────────────────────────────────────
    theme: str = "textual-dark"       # Textual theme name
    notifications_sound_enabled: bool = True  # play a short sound with customnotify() toasts

    # ── AI ────────────────────────────────────────────────────────────────────────
    ai_enabled: bool = False           # мастер-выключатель AI-помощника
    ai_model: str = ""                 # имя/путь к LLM-модели (GGUF)
    ai_mcp_host: str = "127.0.0.1"    # MCP-сервер хост
    ai_mcp_port: int = 0              # 0 = stdio, >0 = TCP
    ai_mcp_model_path: str = ""       # путь к GGUF-файлу
    ai_mcp_auto_start: bool = False   # автостарт MCP-сервера при запуске pentool

    # Observer list — not serialized
    _observers: list[ConfigObserver] = field(default_factory=list, init=False, repr=False, compare=False)

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
        """Convert to dict for serialization."""
        return {
            "proxy_host": self.proxy_host,
            "proxy_port": self.proxy_port,
            "cert_dir": self.cert_dir,
            "db_path": self.db_path,
            "log_file": self.log_file,
            "log_level": self.log_level,
            "plugins_dir": self.plugins_dir,
            "scope": self.scope,
            "intercept_enabled": self.intercept_enabled,
            "recent_projects": self.recent_projects,
            "auto_save_enabled": self.auto_save_enabled,
            "auto_save_interval": self.auto_save_interval,
            "default_user_agent": self.default_user_agent,
            "request_timeout": self.request_timeout,
            "connect_timeout": self.connect_timeout,
            "collaborator_url": self.collaborator_url,
            "max_redirects": self.max_redirects,
            "verify_ssl": self.verify_ssl,
            "scan_marker_enabled": self.scan_marker_enabled,
            "scan_marker_name": self.scan_marker_name,
            "scan_marker_value": self.scan_marker_value,
            "send_crash_reports": self.send_crash_reports,
            "check_updates": self.check_updates,
            "theme": self.theme,
            "notifications_sound_enabled": self.notifications_sound_enabled,
        }

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

    def save(self, path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        cfg = cls()
        for key, value in data.items():
            if hasattr(cfg, key) and not key.startswith("_"):
                setattr(cfg, key, value)
        # Remove non-existent paths from recent_projects on load
        before = len(cfg.recent_projects)
        cfg.recent_projects = [p for p in cfg.recent_projects if os.path.exists(p)]
        if len(cfg.recent_projects) != before:
            try:
                cfg.save()
            except Exception:
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
