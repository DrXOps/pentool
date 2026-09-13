"""Scope handler — open/edit/save/load proxy scope."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pentool.core.logging import get_logger

if TYPE_CHECKING:
    from pentool.tui.screens.proxy.screen import ProxyScreen

logger = get_logger(__name__)


def _norm_host(pattern: str) -> str:
    """Strip a wildcard prefix for Target scope sync."""
    return pattern.strip().lstrip("*.")


async def open_scope(proxy_screen: ProxyScreen) -> None:
    """Open Scope dialog and apply result."""
    proxy = proxy_screen._get_proxy()
    current = proxy.scope if proxy else []

    from pentool.tui.dialogs.scope_dialog import ScopeDialog

    def _apply(result: list[str] | None) -> None:
        if result is not None and proxy is not None:
            old_scope = set(current or [])
            new_scope = set(result)
            proxy.set_scope(result)
            # Persist to DB
            proxy_screen.run_worker(_save_scope_setting(proxy_screen, result))
            # Mirror to global Config
            try:
                from pentool.core.config import get_config
                cfg = get_config()
                cfg.scope = list(result)
                cfg.save()
            except Exception as e:
                logger.warning("open_scope: failed to save scope to config: %s", e)
            # Mirror to TargetScreen
            for pattern in new_scope - old_scope:
                host = _norm_host(pattern)
                if host:
                    proxy_screen._sync_target_host_scope(host, True)
            for pattern in old_scope - new_scope:
                host = _norm_host(pattern)
                if host:
                    proxy_screen._sync_target_host_scope(host, False)
            # Update ScopeToggle state in FilterBar
            scope_toggle_was_active = False
            try:
                from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
                filter_bar = proxy_screen.query_one("#filter-bar", FilterBar)
                st = filter_bar.query_one("#fb-scope", ScopeToggle)
                scope_toggle_was_active = st.active
                st.set_scope_empty(not bool(result))
            except Exception:
                pass
            if scope_toggle_was_active and result:
                proxy_screen.run_worker(proxy_screen._reload_table({"scope_only": True}))
            elif not result:
                proxy_screen.run_worker(proxy_screen._reload_table(None))
            if result is not None:
                n = len(result)
                proxy_screen.app.notify(
                    f"Scope updated: {n} host{'s' if n != 1 else ''}",
                    timeout=3,
                )

    proxy_screen.app.push_screen(ScopeDialog(current), _apply)


async def _save_scope_setting(proxy_screen: ProxyScreen, hosts: list[str]) -> None:
    """Save proxy scope per-project (DB)."""
    try:
        from pentool.core.db_schema import set_project_setting
        db_path = proxy_screen._get_db_path()
        if db_path:
            await set_project_setting(db_path, "proxy.scope", json.dumps(hosts))
    except Exception as exc:
        logger.debug("_save_scope_setting: %s", exc)


async def load_scope_setting(proxy_screen: ProxyScreen, is_new: bool = False) -> None:
    """Load persisted scope for the current project."""
    proxy = proxy_screen._get_proxy()
    if proxy is None:
        return
    hosts: list[str] | None = None
    try:
        from pentool.core.db_schema import get_project_setting
        db_path = proxy_screen._get_db_path()
        raw = await get_project_setting(db_path, "proxy.scope", None) if db_path else None
        if raw is not None:
            hosts = json.loads(raw)
    except Exception as exc:
        logger.debug("load_scope_setting: %s", exc)
        hosts = None
    if hosts is None and not is_new:
        try:
            from pentool.core.config import get_config
            hosts = list(get_config().scope)
        except Exception:
            hosts = []
    if hosts is None:
        hosts = []
    logger.info("PROXY: load_scope_setting -> %d host(s)", len(hosts))
    proxy.set_scope(hosts)
    try:
        from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
        filter_bar = proxy_screen.query_one("#filter-bar", FilterBar)
        filter_bar.query_one("#fb-scope", ScopeToggle).set_scope_empty(not bool(hosts))
    except Exception:
        pass


async def load_enforce_scope_setting(proxy_screen: ProxyScreen) -> None:
    """Load persisted 'skip out-of-scope' flag for the current project."""
    proxy = proxy_screen._get_proxy()
    if proxy is None:
        return
    enabled: bool = False
    try:
        from pentool.core.db_schema import get_project_setting
        db_path = proxy_screen._get_db_path()
        raw = await get_project_setting(db_path, "proxy.enforce_scope", None) if db_path else None
        if raw is not None:
            enabled = json.loads(raw)
    except Exception:
        pass
    logger.info("PROXY: load_enforce_scope_setting -> enforce=%s", enabled)
    proxy.set_enforce_scope(enabled)
    if enabled:
        proxy_screen._sync_enforce_scope_button(True)


async def save_enforce_scope_setting(proxy_screen: ProxyScreen, enabled: bool) -> None:
    """Save enforce-scope flag per-project (DB)."""
    try:
        from pentool.core.db_schema import set_project_setting
        db_path = proxy_screen._get_db_path()
        if db_path:
            await set_project_setting(db_path, "proxy.enforce_scope", "1" if enabled else "0")
    except Exception as exc:
        logger.debug("save_enforce_scope_setting: %s", exc)


async def save_scope_setting(proxy_screen: ProxyScreen, hosts: list[str]) -> None:
    """Save proxy scope per-project (DB)."""
    try:
        from pentool.core.db_schema import set_project_setting
        db_path = proxy_screen._get_db_path()
        if db_path:
            await set_project_setting(db_path, "proxy.scope", json.dumps(hosts))
    except Exception as exc:
        logger.debug("save_scope_setting: %s", exc)