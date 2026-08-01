"""ProjectManager — handles project lifecycle for PentoolApp.

Extracted from PentoolApp to keep app.py focused on Textual wiring.
All methods delegate back to self._app for Textual-level operations
(push_screen, query_one, post_message, run_worker, notify).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

from pentool.core.database import init_db
from pentool.core.logging import get_logger
from pentool.tui.constants import (
    SCREEN_DASHBOARD,
    SCREEN_INTRUDER,
    SCREEN_PROXY,
    SCREEN_SCANNER,
    SCREEN_TARGET,
)
from pentool.tui.messages import ProxyClearHistory, ProxyLoadProject

if TYPE_CHECKING:
    from pentool.tui.app import PentoolApp

logger = get_logger(__name__)


class ProjectManager:
    """Manages project open/save/switch operations on behalf of PentoolApp."""

    def __init__(self, app: "PentoolApp") -> None:
        self._app = app

    # ── Shortcuts to app state ────────────────────────────────────────────────

    @property
    def _cfg(self):
        return self._app._cfg

    @property
    def _proxy(self):
        return self._app._proxy

    @property
    def _proxy_api(self):
        return self._app._proxy_api

    @property
    def _proxy_service(self):
        return self._app._proxy_service

    # ── Public actions (called from PentoolApp action_* methods) ─────────────

    def new_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".db"):
                path = path + ".db"
            self.switch_project_db(path, is_new=True)

        self._app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="New Project — Choose Location",
                start_dir=os.path.expanduser("~"),
            ),
            _on_path,
        )

    def open_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._app._project_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not os.path.exists(path):
                self._app.notify(f"File not found: {path}", severity="error", timeout=4)
                return
            self.switch_project_db(path, is_new=False)

        self._app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                title="Open Project",
                start_dir=start_dir,
                filter_ext=[".db"],
            ),
            _on_path,
        )

    def save_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._app._project_path or self._cfg.db_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".db"):
                path = path + ".db"
            import shutil
            src = self._cfg.db_path
            try:
                shutil.copy2(src, path)
                self._app._project_path = path
                self.update_project_name(path, saved=True)
                self._app.notify(f"Saved to {os.path.basename(path)}", timeout=3)
                try:
                    from pentool.tui.screens.dashboard.screen import DashboardScreen
                    dash = self._app.query_one(SCREEN_DASHBOARD, DashboardScreen)
                    dash.log_activity(
                        f'Project "{os.path.splitext(os.path.basename(path))[0]}" saved to {path}',
                        "ok"
                    )
                    dash._populate_projects()
                except Exception:
                    pass
            except Exception as e:
                self._app.notify(f"Save failed: {e}", severity="error", timeout=4)

        self._app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="Save Project As",
                start_dir=start_dir,
            ),
            _on_path,
        )

    def save_project_json(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._app._project_path or self._cfg.db_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".json"):
                path = path + ".json"
            self._do_save_json(path)

        self._app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="Export Project (JSON)",
                start_dir=start_dir,
            ),
            _on_path,
        )

    def open_project_json(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._app._project_path or self._cfg.db_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not os.path.exists(path):
                self._app.notify(f"File not found: {path}", severity="error", timeout=4)
                return
            self._do_load_json(path)

        self._app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                title="Import Project (JSON)",
                start_dir=start_dir,
                filter_ext=[".json"],
            ),
            _on_path,
        )

    # ── JSON save / load ──────────────────────────────────────────────────────

    def _do_save_json(self, path: str) -> None:
        """Collect data from all APIs and save to JSON v2."""
        from pentool.core.project import save_project
        try:
            # Proxy (scope, match/replace) — without http_history (read from SQLite)
            proxy_export = self._proxy_api.export_project_data()
            # HTTP history — read from SQLite via ProxyService
            try:
                if self._proxy_service is not None and self._proxy_service.is_storage_ready():
                    http_history = asyncio.run_coroutine_threadsafe(
                        self._proxy_service._storage.export_all_requests(),
                        self._app._loop,
                    ).result(timeout=30)
                    proxy_export["http_history"] = http_history
                    logger.info(
                        "_do_save_json: exported %d HTTP entries from SQLite",
                        len(http_history),
                    )
            except Exception as exc:
                logger.warning("_do_save_json: http_history export failed: %s", exc)
            # Scanner findings
            try:
                from pentool.tui.screens.scanner.screen import ScannerScreen
                scanner_screen = self._app.query_one(SCREEN_SCANNER, ScannerScreen)
                scanner_api = scanner_screen._scanner_api
                scanner_export = scanner_api.export_project_data() if scanner_api else {"findings": []}
            except Exception:
                scanner_export = {"findings": []}
            # Target sitemap
            try:
                from pentool.tui.screens.target.screen import TargetScreen
                target_screen = self._app.query_one(SCREEN_TARGET, TargetScreen)
                target_api = target_screen._get_api()
                target_export = target_api.export_project_data()
            except Exception:
                target_export = {"sitemap": {}}
            # Intruder results
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen
                intruder_screen = self._app.query_one(SCREEN_INTRUDER, IntruderScreen)
                intruder_api = getattr(intruder_screen, "_api", None)
                intruder_export = intruder_api.export_project_data() if intruder_api else {"results": []}
            except Exception:
                intruder_export = {"results": []}
            # Spider sessions (from EventBus history)
            spider_export = self._collect_spider_sessions()

            data = {
                **proxy_export,
                "scanner":  scanner_export,
                "intruder": intruder_export,
                "spider":   spider_export,
                "target":   target_export,
            }
            save_project(path, data)
            self.update_project_name(path)
            self._app.notify(f"Saved → {os.path.basename(path)}", timeout=3)
            logger.info("APP: project saved to JSON: %s", path)
        except Exception as exc:
            logger.error("_do_save_json error: %s", exc, exc_info=True)
            self._app.notify(f"Save failed: {exc}", severity="error", timeout=4)

    def _do_load_json(self, path: str) -> None:
        from pentool.core.project import load_project
        data, err = load_project(path)
        if err:
            self._app.notify(f"Load failed: {err}", severity="error", timeout=5)
            return
        try:
            # Proxy
            loaded_proxy, err_proxy = self._proxy_api.import_project_data(data)
            if err_proxy:
                logger.warning("import proxy: %s", err_proxy)
            # Scanner findings — restore via engine, then reload UI
            scanner_count = 0
            try:
                from pentool.tui.screens.scanner.screen import ScannerScreen
                scanner_screen = self._app.query_one(SCREEN_SCANNER, ScannerScreen)
                db_path = self._cfg.db_path
                scanner_api = scanner_screen._get_or_create_api(db_path)
                scanner_count = scanner_api.import_project_data(data.get("scanner", {}))
                scanner_screen._populate_from_db([])
                scanner_screen._load_findings_worker()
            except Exception as exc:
                logger.warning("import scanner: %s", exc)
            # Target sitemap
            target_count = 0
            try:
                from pentool.tui.screens.target.screen import TargetScreen
                target_screen = self._app.query_one(SCREEN_TARGET, TargetScreen)
                target_api = target_screen._get_api()
                target_count = target_api.import_project_data(data.get("target", {}))
                target_screen._load_sitemap()
            except Exception as exc:
                logger.warning("import target: %s", exc)
            # Intruder results
            intruder_count = 0
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen
                intruder_screen = self._app.query_one(SCREEN_INTRUDER, IntruderScreen)
                intruder_api = getattr(intruder_screen, "_api", None)
                if intruder_api:
                    intruder_count = intruder_api.import_project_data(data.get("intruder", {}))
            except Exception as exc:
                logger.warning("import intruder: %s", exc)

            self._app.post_message(ProxyLoadProject())
            self.update_project_name(path)

            total = loaded_proxy + scanner_count + target_count + intruder_count
            self._app.notify(
                f"Loaded {os.path.basename(path)} — "
                f"proxy: {loaded_proxy}, scanner: {scanner_count}, "
                f"target: {target_count}, intruder: {intruder_count}",
                timeout=5,
            )
            logger.info(
                "APP: project loaded from JSON: %s, total items: %d", path, total
            )
        except Exception as exc:
            logger.error("_do_load_json error: %s", exc, exc_info=True)
            self._app.notify(f"Load failed: {exc}", severity="error", timeout=4)

    # ── Project switch ────────────────────────────────────────────────────────

    def switch_project_db(self, path: str, is_new: bool = False) -> None:
        """Switch to a different .db file as the active project.

        If the proxy is running it is stopped first (with a notification),
        then the DB switch happens in a single exclusive worker so concurrent
        switch calls cannot race each other.
        """
        if is_new:
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Stop proxy before switching DB — avoids writing to the wrong file
        # and simplifies the concurrency story (one connection at a time).
        if self._proxy and self._proxy.is_running:
            self._app.notify(
                "Proxy остановлен для переключения проекта",
                severity="warning",
                timeout=4,
            )
            self._app._stop_proxy()

        self._cfg.db_path = path
        self._app._project_path = path
        self._app._project_loaded = True

        if self._proxy:
            self._proxy.db_path = path

        if is_new and self._proxy:
            try:
                self._proxy.clear_requests()
                self._proxy.scope = []
                self._proxy.match_replace_rules = []
            except Exception:
                pass

        # Single exclusive worker — no two switches can run in parallel.
        self._app.run_worker(
            self._do_switch(path, is_new),
            exclusive=True,
            thread=False,
        )

        self.update_project_name(path)
        action = "Создан" if is_new else "Открыт"
        self._app.notify(f"{action}: {os.path.basename(path)}", timeout=3)

        try:
            from pentool.tui.screens.dashboard.screen import DashboardScreen
            dash = self._app.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dash._populate_projects()
            verb = "создан" if is_new else "открыт"
            dash.log_activity(
                f'Project "{os.path.splitext(os.path.basename(path))[0]}" {verb} from {path}',
                "ok"
            )
        except Exception:
            pass

    # ── Internal async helpers ────────────────────────────────────────────────

    async def _do_switch(self, path: str, is_new: bool) -> None:
        """Single entry point for all project switches.

        Runs in an exclusive worker — no two switches can overlap.
        Order is strict:
          1. init_db (CREATE TABLE IF NOT EXISTS, migrations)
          2. switch_db on ProxyService (close old connection, open new one)
          3. clear in-memory proxy state if new project
          4. reload all screens sequentially (no nested run_worker)
        """
        # 1. Ensure schema exists (safe for both new and existing DBs)
        await self._init_new_db(path)

        # 2. Switch HttpStorage to the new DB — sequential, no races
        if self._proxy_service is not None:
            await self._proxy_service.switch_db(path)
            logger.info("_do_switch: storage switched to %s", path)

        # 3. Clear in-memory proxy requests for a new project
        if is_new:
            from pentool.tui.messages import ProxyClearHistory
            try:
                from pentool.tui.screens.proxy.screen import ProxyScreen
                screen = self._app.query_one(SCREEN_PROXY, ProxyScreen)
                screen.action_clear_list()
            except Exception:
                pass

        # 4. Reload all screens — all awaited, never spawning sub-workers
        await self._reload_project_screens(path)

    async def _reload_project_screens(self, path: str) -> None:
        """Reload data from DB into all screens. Called from _do_switch only."""

        # 1. ProxyScreen — must come after switch_db is fully done
        try:
            screen = self._app.query_one(SCREEN_PROXY, ProxyScreen)
            await screen._reload_from_storage()
            logger.info("_reload_project_screens: proxy reloaded from %s", path)
        except Exception as exc:
            logger.debug("_reload_project_screens proxy: %s", exc)

        # 2. ScannerScreen
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen
            scanner_screen = self._app.query_one(SCREEN_SCANNER, ScannerScreen)
            if scanner_screen._scanner_api is not None:
                scanner_screen._scanner_api._db_path = path
            scanner_screen._scanner_api = None
            scanner_screen._scanner_api = scanner_screen._get_or_create_api(path)
            scanner_screen._populate_from_db([])
            scanner_screen._load_findings_worker()
            logger.info("_reload_project_screens: scanner reloaded")
        except Exception as exc:
            logger.debug("_reload_project_screens scanner: %s", exc)

        # 3. TargetScreen
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target_screen = self._app.query_one(SCREEN_TARGET, TargetScreen)
            if target_screen._target_api is not None:
                try:
                    await target_screen._target_api.save()
                except Exception:
                    pass
            target_screen._target_api = None
            target_screen._get_api()
            target_screen._load_sitemap()
            logger.info("_reload_project_screens: target reloaded from %s", path)
        except Exception as exc:
            logger.debug("_reload_project_screens target: %s", exc)

        # 4. Dashboard
        try:
            from pentool.tui.screens.dashboard.screen import DashboardScreen
            dash = self._app.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dash.refresh_stats()
        except Exception as exc:
            logger.debug("_reload_project_screens dashboard: %s", exc)

    async def _init_new_db(self, path: str) -> None:
        try:
            await init_db(path)
        except Exception as exc:
            logger.warning("_init_new_db: %s", exc)

    # _switch_storage_db и _open_project_sequence оставлены для совместимости
    # с app.py (_reload_project_screens, _switch_storage_db, _open_project_sequence)
    async def _switch_storage_db(self, path: str) -> None:
        if self._proxy_service is not None:
            await self._proxy_service.switch_db(path)

    async def _open_project_sequence(self, path: str) -> None:
        await self._do_switch(path, is_new=False)

    # ── Spider sessions ───────────────────────────────────────────────────────

    def _collect_spider_sessions(self) -> dict:
        """Collect Spider session data from EventBus history."""
        from pentool.core.event_bus import get_event_bus
        from pentool.core.events import SpiderFinished
        sessions = []
        try:
            bus = get_event_bus()
            events = bus.get_history(event_type=SpiderFinished, limit=100)
            for ev in events:
                sessions.append({
                    "base_url":        getattr(ev, "base_url", ""),
                    "pages_count":     getattr(ev, "pages_count", 0),
                    "forms_count":     getattr(ev, "forms_count", 0),
                    "endpoints_count": getattr(ev, "endpoints_count", 0),
                    "timestamp":       getattr(ev, "timestamp", 0),
                })
        except Exception as exc:
            logger.debug("_collect_spider_sessions: %s", exc)
        return {"sessions": sessions}

    # ── Project name / statusbar ──────────────────────────────────────────────

    def update_project_name(self, path: str, saved: bool = True) -> None:
        name = os.path.basename(path) if path else "new project"
        if name.endswith(".db"):
            name = name[:-3]
        try:
            from pentool.tui.widgets.statusbar import StatusBar
            bar = self._app.query_one(StatusBar)
            bar.set_project(name, path, saved)
        except Exception:
            pass
        try:
            self._app.sub_title = f"project: {name}"
        except Exception:
            pass
        if path and path != "new project":
            try:
                self._cfg.add_recent_project(path)
            except Exception:
                pass


# Lazy import to avoid circular reference at module load
from pentool.tui.screens.proxy.screen import ProxyScreen  # noqa: E402
