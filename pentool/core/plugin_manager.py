"""Pentool plugin system: base classes and load manager."""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import click

logger = logging.getLogger(__name__)

# Current Plugin API version. Plugins with api_version > CURRENT are incompatible.
CURRENT_API_VERSION = 1

# User plugins directory (PRO plugins are installed here)
USER_PLUGINS_DIR = Path.home() / ".pentool" / "plugins"


class BasePlugin:
    """Base class for all Pentool plugins.

    Each plugin must declare class attributes:
        name             — unique ID (snake_case)
        version          — version string ("1.0")
        author           — author name
        description      — short description
        api_version      — Plugin API version (currently 1)
        required_feature — feature string from LicenseInfo.features, or ""
                           (empty string = free plugin, no PRO required)
    """

    name: str = ""
    version: str = "0.1"
    author: str = ""
    description: str = ""
    api_version: int = CURRENT_API_VERSION
    required_feature: str = ""   # "" = free; "scanner_pro" / "reports_pro" / ...


class BaseCheck:
    """Base class for an individual check (active or passive).

    Used in modules/scanner/ and scanner plugins.
    """

    name: str = ""
    description: str = ""
    severity: str = "info"      # critical | high | medium | low | info
    passive: bool = False       # True -> runs on every proxy request

    async def scan(self, target: Any, http_client: Any, **kwargs) -> list:
        return []


class BaseScanner(BasePlugin):
    """Base class for a scanner plugin.

    A scanner plugin groups several BaseChecks under one name.
    Example: XSSScanner registers reflected_xss, dom_xss, etc.
    """

    checks: list[type[BaseCheck]] = []

    async def scan(self, target: Any, http_client: Any, **kwargs) -> list:
        results = []
        for check_cls in self.checks:
            check = check_cls()
            try:
                findings = await check.scan(target, http_client, **kwargs)
                results.extend(findings)
            except Exception as exc:
                logger.warning("Check %s failed: %s", check_cls.name, exc)
        return results


@dataclass
class PluginScreen:
    """Screen registered by a plugin."""
    name: str
    widget_class: type
    hotkey: str | None = None
    plugin_name: str = ""


@dataclass
class PluginCommand:
    """CLI command registered by a plugin."""
    group_name: str
    command: Any               # click.Command
    plugin_name: str = ""


class PluginHook:
    """Object passed to register(hook) of each plugin.

    Through it a plugin declares its contributions to TUI, CLI, and scanner.
    """

    def __init__(self, plugin_name: str) -> None:
        self._plugin_name = plugin_name
        self._screens: list[PluginScreen] = []
        self._commands: list[PluginCommand] = []
        self._scanners: list[type[BaseScanner]] = []
        self._passive_checks: list[type[BaseCheck]] = []

    def register_screen(
        self,
        name: str,
        widget_class: type,
        hotkey: str | None = None,
    ) -> None:
        self._screens.append(
            PluginScreen(name=name, widget_class=widget_class,
                         hotkey=hotkey, plugin_name=self._plugin_name)
        )
        logger.debug("Plugin '%s': registered screen '%s'", self._plugin_name, name)

    def register_cli_command(self, group_name: str, command: Any) -> None:
        self._commands.append(
            PluginCommand(group_name=group_name, command=command,
                          plugin_name=self._plugin_name)
        )
        logger.debug("Plugin '%s': registered CLI command '%s' -> group '%s'",
                     self._plugin_name, command.name, group_name)

    def register_scanner(self, scanner_class: type[BaseScanner]) -> None:
        self._scanners.append(scanner_class)
        logger.debug("Plugin '%s': registered scanner '%s'",
                     self._plugin_name, scanner_class.name)

    def register_passive_check(self, check_class: type[BaseCheck]) -> None:
        self._passive_checks.append(check_class)
        logger.debug("Plugin '%s': registered passive check '%s'",
                     self._plugin_name, check_class.name)


@dataclass
class PluginMeta:
    """Metadata about a loaded plugin."""
    name: str
    path: str
    version: str = "?"
    author: str = ""
    description: str = ""
    required_feature: str = ""  # "" = free
    loaded: bool = True         # False = blocked by license


class PluginManager:
    """Loads and stores all registered plugins."""

    def __init__(self) -> None:
        self._screens: list[PluginScreen] = []
        self._commands: list[PluginCommand] = []
        self._scanners: list[type[BaseScanner]] = []
        self._passive_checks: list[type[BaseCheck]] = []
        self._loaded: list[str] = []
        self._meta: list[PluginMeta] = []

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_plugins(self, dirs: list[str], *, warn_untrusted: bool = True) -> None:
        """Scan directories and load plugins.

        Plugins with required_feature are checked via get_session_license().
        If the license does not cover the feature — plugin is skipped with WARNING log.

        Args:
            dirs:           List of paths to plugin directories.
            warn_untrusted: Log a warning for non-standard paths.
        """
        builtin_dir = str(
            Path(__file__).parent.parent / "plugins" / "builtin"
        )
        for dir_path in dirs:
            is_builtin = Path(dir_path).resolve() == Path(builtin_dir).resolve()
            for py_file in sorted(Path(dir_path).glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                if warn_untrusted and not is_builtin:
                    logger.warning(
                        "Loading plugin from untrusted source: %s", py_file
                    )
                self._load_file(py_file)

    def load_user_plugins(self) -> None:
        if USER_PLUGINS_DIR.exists():
            self.load_plugins([str(USER_PLUGINS_DIR)], warn_untrusted=False)
        else:
            logger.debug("User plugins dir not found: %s", USER_PLUGINS_DIR)

        # Obfuscated PRO package downloaded via 'pentool license trial'/'activate'
        # (see pentool.core.license.download_pro_package). Its plugins directory
        # mirrors the builtin layout: pro/pentool/plugins/builtin/*.py
        from pentool.core.license import PRO_PACKAGE_DIR
        pro_plugins_dir = PRO_PACKAGE_DIR / "pentool" / "plugins" / "builtin"
        if pro_plugins_dir.exists():
            self.load_plugins([str(pro_plugins_dir)], warn_untrusted=False)
        else:
            logger.debug("PRO package plugins dir not found: %s", pro_plugins_dir)

    def _load_file(self, path: Path) -> None:
        module_name = f"_pentool_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning("Cannot load plugin: %s", path)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            if not hasattr(module, "register"):
                logger.warning("Plugin has no register(): %s", path)
                return

            # Determine plugin name and metadata
            plugin_name = path.stem
            plugin_cls = self._find_plugin_class(module)
            version = getattr(plugin_cls, "version", "?") if plugin_cls else "?"
            author = getattr(plugin_cls, "author", "") if plugin_cls else ""
            description = getattr(plugin_cls, "description", "") if plugin_cls else ""
            required_feature = getattr(plugin_cls, "required_feature", "") if plugin_cls else ""

            # Check api_version compatibility
            if plugin_cls is not None:
                api_ver = getattr(plugin_cls, "api_version", 1)
                if api_ver > CURRENT_API_VERSION:
                    logger.warning(
                        "Plugin '%s' requires api_version=%d, current=%d — skipped",
                        plugin_name, api_ver, CURRENT_API_VERSION,
                    )
                    self._meta.append(PluginMeta(
                        name=plugin_name, path=str(path),
                        version=version, author=author,
                        description=f"Requires Plugin API v{api_ver}",
                        required_feature=required_feature, loaded=False,
                    ))
                    return

            # License check for PRO plugins
            if required_feature:
                if not self._check_license_feature(required_feature):
                    logger.warning(
                        "Plugin '%s' requires license feature '%s' — skipped (license not active)",
                        plugin_name, required_feature,
                    )
                    self._meta.append(PluginMeta(
                        name=plugin_name, path=str(path),
                        version=version, author=author,
                        description=description,
                        required_feature=required_feature, loaded=False,
                    ))
                    return

            hook = PluginHook(plugin_name)
            module.register(hook)

            self._screens.extend(hook._screens)
            self._commands.extend(hook._commands)
            self._scanners.extend(hook._scanners)
            self._passive_checks.extend(hook._passive_checks)
            self._loaded.append(str(path))
            self._meta.append(PluginMeta(
                name=plugin_name, path=str(path),
                version=version, author=author, description=description,
                required_feature=required_feature, loaded=True,
            ))
            logger.info("Loaded plugin: %s", path.name)

        except Exception as exc:
            logger.error("Failed to load plugin %s: %s", path, exc)

    @staticmethod
    def _find_plugin_class(module: Any) -> type | None:
        """Find the first BasePlugin subclass in a module."""
        for cls_name in dir(module):
            cls = getattr(module, cls_name)
            if (isinstance(cls, type)
                    and issubclass(cls, BasePlugin)
                    and cls is not BasePlugin
                    and cls is not BaseScanner):
                return cls
        return None

    @staticmethod
    def _check_license_feature(feature: str) -> bool:
        try:
            from pentool.core.license import get_session_license
            info = get_session_license()
            return info.has_feature(feature)
        except Exception:
            return False

    # ── Getters ───────────────────────────────────────────────────────────────

    def get_screens(self) -> list[PluginScreen]:
        return list(self._screens)

    def get_commands(self) -> list[PluginCommand]:
        return list(self._commands)

    def get_scanners(self) -> list[type[BaseScanner]]:
        return list(self._scanners)

    def get_passive_checks(self) -> list[type[BaseCheck]]:
        return list(self._passive_checks)

    def loaded_plugins(self) -> list[str]:
        return list(self._loaded)

    def get_meta(self) -> list[PluginMeta]:
        """List of metadata for all plugins (loaded and blocked)."""
        return list(self._meta)

    def is_feature_available(self, feature: str) -> bool:
        return self._check_license_feature(feature)
