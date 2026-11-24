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

from textual.css.query import NoMatches

from pentool.core.db_schema import init_db
from pentool.core.error_guard import err as _err
from pentool.core.logging import get_logger
from pentool.tui import module_catalog
from pentool.tui.messages import ProxyLoadProject

if TYPE_CHECKING:
    from pentool.tui.app import PentoolApp

logger = get_logger(__name__)

#: Modules whose screens hold project data and must be refreshed on a switch.
#: Ordered as in the module catalog so logs and the deferred-reload queue read the same.
_RELOADABLE_MODULES: tuple[str, ...] = module_catalog.reloadable_ids()


class ProjectManager:
    """Manages project open/save/switch operations on behalf of PentoolApp."""

    def __init__(self, app: "PentoolApp") -> None:
        self._app = app
        #: Project the app is currently switching to / working with. ``reload_screen``
        #: reads these because it is called from two places: the switch itself and
        #: the deferred reload after a lazy screen mount.
        self._current_path: str = ""
        self._current_is_new: bool = False

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
            if os.path.exists(path):
                # Creating a project on an existing database used to overwrite it
                # without a word (T-003): one wrong click in the file picker was
                # enough to lose a project. Ask, and go back to the picker on "no".
                self._confirm_overwrite(path)
                return
            self.switch_project_db(path, is_new=True)

        self._app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="New Project — Choose Location",
                start_dir=os.path.expanduser("~"),
            ),
            _on_path,
        )

    def _confirm_overwrite(self, path: str) -> None:
        """Ask before replacing an existing project database."""
        from pentool.tui.dialogs.confirm import ConfirmDialog

        def _on_answer(confirmed: bool | None) -> None:
            if not confirmed:
                # Nothing was touched: back to where the user can pick another name.
                self.new_project()
                return
            self.switch_project_db(path, is_new=True)

        self._app.push_screen(
            ConfirmDialog(
                title="Database already exists",
                message=(
                    f"{path}\n\nThis file is already a project database. Creating a project here replaces its contents."
                ),
                confirm_text="Overwrite",
                cancel_text="Choose another",
            ),
            _on_answer,
        )

    def open_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        current = self._app._project_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not os.path.exists(path):
                _err(FileNotFoundError(path), f"File not found: {path}")
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

                    dash = self._app.require_module_screen("dashboard", DashboardScreen)
                    dash.log_activity(
                        f'Project "{os.path.splitext(os.path.basename(path))[0]}" saved to {path}',
                        "ok",
                    )
                    dash._populate_projects()
                except Exception:
                    # The file was saved (the notification above is already shown),
                    # but the feed and the project list do not reflect it — a
                    # mismatch between "Saved" and an empty dashboard list.
                    logger.warning("project: save not reflected on dashboard", exc_info=True)
            except Exception as e:
                _err(e, "Save failed")

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
                _err(FileNotFoundError(path), f"File not found: {path}")
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
                        self._proxy_service.export_all_requests(),
                        self._app._loop,
                    ).result(timeout=30)
                    proxy_export["http_history"] = http_history
                    logger.info(
                        "_do_save_json: exported %d HTTP entries from SQLite",
                        len(http_history),
                    )
            except Exception:
                # Proxy history did not make it into the project file: after
                # loading it will be gone. This is loss on export, not cosmetics.
                logger.warning("_do_save_json: http_history export failed", exc_info=True)
            # Scanner findings
            try:
                from pentool.tui.screens.scanner.screen import ScannerScreen

                scanner_screen = self._app.require_module_screen("scanner", ScannerScreen)
                scanner_export = scanner_screen.get_scanner_export()
            except Exception:
                # Scanner findings did not make it into the file: the project is
                # saved "empty" in this part even though the screen shows them.
                logger.warning("_do_save_json: scanner findings not exported", exc_info=True)
                scanner_export = {"findings": []}
            # Target sitemap
            try:
                from pentool.tui.screens.target.screen import TargetScreen

                target_screen = self._app.require_module_screen("target", TargetScreen)
                target_api = target_screen._get_api()
                target_export = target_api.export_project_data()
            except Exception:
                # The site map did not make it into the project file — on load
                # Target will be empty.
                logger.warning("_do_save_json: target sitemap not exported", exc_info=True)
                target_export = {"sitemap": {}}
            # Intruder results
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen

                intruder_screen = self._app.require_module_screen("intruder", IntruderScreen)
                intruder_export = intruder_screen.get_intruder_export()
            except Exception:
                # Intruder results did not make it into the project file.
                logger.warning("_do_save_json: intruder results not exported", exc_info=True)
                intruder_export = {"results": []}
            # Spider sessions (from EventBus history)
            spider_export = self._collect_spider_sessions()

            data = {
                **proxy_export,
                "scanner": scanner_export,
                "intruder": intruder_export,
                "spider": spider_export,
                "target": target_export,
            }
            save_project(path, data)
            self.update_project_name(path)
            self._app.notify(f"Saved → {os.path.basename(path)}", timeout=3)
            logger.info("APP: project saved to JSON: %s", path)
        except Exception as exc:
            _err(exc, "Save failed")

    def _do_load_json(self, path: str) -> None:
        from pentool.core.project import load_project

        data, err = load_project(path)
        if err:
            _err(Exception(err), "Load failed")
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

                scanner_screen = self._app.require_module_screen("scanner", ScannerScreen)
                db_path = self._cfg.db_path
                scanner_api = scanner_screen._get_or_create_api(db_path)
                scanner_count = scanner_api.import_project_data(data.get("scanner", {}))
                scanner_screen._populate_from_db([])
                scanner_screen._load_findings_worker()
            except Exception:
                # Scanner findings were not imported: the project opens without them.
                logger.warning("import scanner: findings not imported", exc_info=True)
            # Target sitemap
            target_count = 0
            try:
                from pentool.tui.screens.target.screen import TargetScreen

                target_screen = self._app.require_module_screen("target", TargetScreen)
                target_api = target_screen._get_api()
                target_count = target_api.import_project_data(data.get("target", {}))
                target_screen._load_sitemap()
            except Exception:
                # Site map was not imported — Target will open empty.
                logger.warning("import target: sitemap not imported", exc_info=True)
            # Intruder results
            intruder_count = 0
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen

                intruder_screen = self._app.require_module_screen("intruder", IntruderScreen)
                intruder_api = getattr(intruder_screen, "_api", None)
                if intruder_api:
                    intruder_count = intruder_api.import_project_data(data.get("intruder", {}))
            except Exception:
                # Intruder results were not imported.
                logger.warning("import intruder: results not imported", exc_info=True)

            self._app.post_message(ProxyLoadProject())
            self.update_project_name(path)

            total = loaded_proxy + scanner_count + target_count + intruder_count
            self._app.notify(
                f"Loaded {os.path.basename(path)} — "
                f"proxy: {loaded_proxy}, scanner: {scanner_count}, "
                f"target: {target_count}, intruder: {intruder_count}",
                timeout=5,
            )
            logger.info("APP: project loaded from JSON: %s, total items: %d", path, total)
        except Exception as exc:
            _err(exc, "Load failed")

    # ── Project switch ────────────────────────────────────────────────────────

    def switch_project_db(self, path: str, is_new: bool = False) -> None:
        """Switch to a different .db file as the active project.

        If the proxy is running it is stopped first (with a notification),
        then the DB switch happens in a single exclusive worker so concurrent
        switch calls cannot race each other.

        Callers that must not continue until the storage is really switched
        (the `--url` seed starts capturing right away) use
        :meth:`switch_project_db_awaited` instead.
        """
        self._prepare_switch(path, is_new)
        self._app.run_worker(self._do_switch(path, is_new), exclusive=True, thread=False)

    async def switch_project_db_awaited(self, path: str, is_new: bool = False) -> None:
        """Switch projects and wait until the storage really points at the new DB.

        Why this exists: `--url/--smart` starts the proxy and fetches the target
        immediately after creating the project. With the fired-and-forget
        version the switch finished *after* the fetch, so every captured request
        was written into the previously open DB and the new project's history
        stayed empty — the bug the user saw as "no requests with --smart".
        """
        self._prepare_switch(path, is_new)
        await self._do_switch(path, is_new)

    def _prepare_switch(self, path: str, is_new: bool) -> None:
        """Synchronous part of a project switch: state, flags and user feedback.

        Kept apart from `_do_switch` so both the worker path and the awaited
        path do exactly the same bookkeeping before touching any storage.
        """
        if is_new:
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Stop proxy before switching DB — avoids writing to the wrong file
        # and simplifies the concurrency story (one connection at a time).
        # NOTE: do NOT call the synchronous _stop_proxy() here — it holds the
        # TUI thread for up to ~10s (future.result(6)+join(5)) while the old
        # proxy is wound down, freezing the UI on "New/Open Project". The actual
        # stop now happens asynchronously at the top of _do_switch (see "0."
        # there), which awaits _stop_proxy_async() without blocking the UI.
        if self._proxy and self._proxy.is_running:
            self._app.notify(
                "Proxy stopped to switch project",
                severity="warning",
                timeout=4,
            )

        # Gate Start Proxy (action_toggle_proxy) until _do_switch flips this
        # back to True once HttpStorage.switch_db() has actually completed —
        # otherwise a Start Proxy click during the switch could race the
        # storage connection being closed/reopened underneath it.
        self._app._project_loaded = False

        self._cfg.db_path = path
        self._app._project_path = path

        if self._proxy:
            self._proxy.db_path = path

        if is_new and self._proxy:
            try:
                self._proxy.clear_requests()
                self._proxy.scope = []
                self._proxy.match_replace_rules = []
                # New project's DB has no project_settings row yet — reset to
                # the documented default (OFF) rather than carrying over
                # whatever the previous project had in memory.
                self._proxy.set_enforce_scope(False)
            except Exception:
                # The new project kept the previous project's history, scope and
                # Match&Replace rules — i.e. another project is visible in it.
                # Everything is caught here: this is the proxy object, and its
                # state is cleared by five independent setters.
                logger.exception("project: new-project proxy state not reset")

        self.update_project_name(path)
        action = "Created" if is_new else "Opened"
        # Single-line toast: no separate title (Textual's toast would render
        # the title on its own row above the message, duplicating "Opened/"
        # "Created" and making the card two rows tall).
        self._app.notify(f"{action}: {os.path.basename(path)}", severity="success" if is_new else "information")

        try:
            from pentool.tui.screens.dashboard.screen import DashboardScreen

            dash = self._app.require_module_screen("dashboard", DashboardScreen)
            dash._populate_projects()
            verb = "created" if is_new else "opened"
            dash.log_activity(f'Project "{os.path.splitext(os.path.basename(path))[0]}" {verb} from {path}', "ok")
        except NoMatches as exc:
            # No dashboard screen in the tree (the project is opened not from the
            # start screen) — there will be no feed entry, and that is fine.
            logger.debug("project: dashboard not mounted for switch log: %s", exc)
        except Exception:
            # The project was switched, but the dashboard feed has no entry about
            # it — and the feed is exactly how the user knows what happened.
            logger.exception("project: switch not logged to dashboard feed")

    # ── Internal async helpers ────────────────────────────────────────────────

    async def _do_switch(self, path: str, is_new: bool) -> None:
        """Switch project DB: stop proxy → init schema → switch storage → reload screens."""
        # Remember what the app is switching to: `reload_screen` (which is also
        # called later, when a lazily mounted screen comes up) reads it from here.
        self._current_path = path
        self._current_is_new = is_new
        # 0. Stop the proxy (async) and wait for its thread to die before
        # touching the DB. Runs in this async worker, so the TUI thread is
        # NOT blocked — this is what previously froze the UI for ~10s on
        # "New/Open Project" (switch_project_db called the synchronous
        # _stop_proxy() = future.result(6)+join(5)). _stop_proxy_async both
        # initiates proxy.stop() (so the 8080 listener is released) and waits
        # for the thread to exit so we don't open a new SQLite connection
        # while the old proxy loop might still be writing to it.
        await self._app._stop_proxy_async()

        # 1. Ensure schema exists (safe for both new and existing DBs)
        await self._init_new_db(path)

        # 2. Switch HttpStorage to the new DB — sequential, no races
        if self._proxy_service is not None:
            await self._proxy_service.switch_db(path)
            logger.info("_do_switch: storage switched to %s", path)

        # 3. Clear in-memory proxy requests for a new project
        if is_new:
            screen = self._app.module_screen("proxy")
            if screen is None:
                # Not mounted: there is nothing to clear on screen, and the rows
                # live in the old storage. `reload_screen` on its next mount
                # starts it empty, so the new project cannot inherit anything.
                logger.debug("_do_switch: proxy not mounted, table clear skipped")
            else:
                try:
                    # Await directly — do NOT use action_clear_list() here because it
                    # spawns a run_worker that races with _reload_from_storage below.
                    proxy = self._proxy
                    if proxy:
                        proxy.clear_requests()
                    await screen._do_clear_table()  # type: ignore[attr-defined]
                    try:
                        screen.query_one("#req-editor").clear()  # type: ignore[attr-defined]
                        screen.query_one("#resp-viewer").clear()  # type: ignore[attr-defined]
                    except NoMatches as exc:
                        # The table is cleared but the panels still show the previous
                        # project's request — the new project's data looks loaded.
                        logger.debug("_do_switch: detail panels not cleared: %s", exc)
                    screen._selected_req_id = None  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.debug("_do_switch: clear for new project: %s", exc)

        # 4. Set flag as soon as the DB itself is ready — Start Proxy only
        # needs HttpStorage (step 2) done, not the other screens below.
        self._app._project_loaded = True
        logger.info("_do_switch: project loaded flag set (DB ready)")

        # 5. Reload the remaining screens concurrently — independent of
        # each other and of the flag above.
        await self._reload_project_screens(path, is_new=is_new)
        logger.info("_do_switch: all screens reloaded")

    async def _reload_project_screens(self, path: str, is_new: bool = False) -> None:
        """Bring every module screen up to date with the project that is now open.

        Only *mounted* screens can be reloaded — with lazy mounting the rest live
        nowhere. Those are marked stale instead and reloaded by
        :meth:`LazyScreenManager.activate` the next time the module is opened, so
        a screen can never show the previous project's data.

        Each screen's reload is independent (different tables/state), so the
        mounted ones run concurrently via `asyncio.gather`: total time is bounded
        by the slowest single reload, not the sum.
        """

        async def _safe_reload(module_id: str, screen: object) -> None:
            try:
                await self.reload_screen(module_id, screen)
            except Exception:
                # The screen is mounted, so this is not deferrable: it stays on
                # the previous project's data. Loud on purpose.
                logger.error("_reload_project_screens: %s not switched", module_id, exc_info=True)

        tasks = []
        for module_id in _RELOADABLE_MODULES:
            screen = self._app.module_screen(module_id)
            if screen is None:
                self._app.mark_screen_stale(module_id)
                logger.debug("_reload_project_screens: %s not mounted — reload deferred", module_id)
                continue
            tasks.append(_safe_reload(module_id, screen))
        if tasks:
            await asyncio.gather(*tasks)

    async def reload_screen(self, module_id: str, screen: object) -> None:
        """Reload one screen from the project that is currently open.

        Raises when the reload fails: the caller decides whether that is fatal
        (a mounted screen showing another project's rows) or retryable (the
        deferred reload after a lazy mount, which keeps the screen stale).

        One method instead of six nested closures because it is now called from
        two places — the project switch and the lazy-mount replay.
        """
        path = self._current_path
        is_new = self._current_is_new
        match module_id:
            case "proxy":
                # is_new lets the proxy screen start a brand-new project with an
                # EMPTY scope (not inherited from the previous project).
                await screen._reload_from_storage(is_new=is_new)  # type: ignore[attr-defined]
                logger.info("reload_screen: proxy reloaded from %s", path)
            case "repeater":
                if is_new:
                    await screen.reset_for_new_project()  # type: ignore[attr-defined]
                else:
                    await screen.reload_from_project(path)  # type: ignore[attr-defined]
                logger.info("reload_screen: repeater %s", "reset" if is_new else "reloaded")
            case "scanner":
                # SCANNER_SCREEN_AVAILABLE from screens/__init__.py already wraps
                # the import in a try/except and falls back to
                # ScannerUnavailableScreen when the PRO package is absent —
                # importing scanner.screen directly raised ImportError there.
                from pentool.tui.screens import SCANNER_SCREEN_AVAILABLE

                if not SCANNER_SCREEN_AVAILABLE:
                    logger.debug("reload_screen: scanner unavailable (PRO not installed)")
                    return
                screen._scanner_api = None  # type: ignore[attr-defined]
                screen._scanner_api = screen._get_or_create_api(path)  # type: ignore[attr-defined]
                screen._populate_from_db([])  # type: ignore[attr-defined]
                screen._load_findings_worker()  # type: ignore[attr-defined]
                screen._clear_scan_logs()  # type: ignore[attr-defined]
                logger.info("reload_screen: scanner reloaded")
            case "target":
                await self._reload_target_screen(screen, is_new=is_new)
                logger.info("reload_screen: target reloaded from %s", path)
            case "dashboard":
                screen.refresh_stats()  # type: ignore[attr-defined]
            case "intruder":
                await screen.reload_from_project(path)  # type: ignore[attr-defined]
                logger.info("reload_screen: intruder reloaded from %s", path)
            case _:
                logger.debug("reload_screen: %s has nothing to reload", module_id)

    async def _reload_target_screen(self, target_screen: object, *, is_new: bool) -> None:
        """Target owns a SiteMap with its own SQLite connection — close it first."""
        if target_screen._target_api is not None:  # type: ignore[attr-defined]
            try:
                await target_screen._target_api.save()  # type: ignore[attr-defined]
            except Exception:
                # Unsaved site map changes of the previous project are lost on a
                # switch — silently. This is user data loss, which is why it is a
                # warning with a traceback.
                logger.warning("project: old site map not saved before switch", exc_info=True)
            # SiteMap holds one persistent SQLite connection: close it before
            # dropping the instance, otherwise a connection to the old project's
            # DB file lingers until quit and accumulates FDs/locks.
            try:
                await target_screen._target_api.close()  # type: ignore[attr-defined]
            except Exception:
                # The connection stays open until quit: file descriptors and locks
                # pile up with every project switch.
                logger.warning("project: old site map connection not closed", exc_info=True)
        target_screen._target_api = None  # type: ignore[attr-defined]
        target_screen._get_api()  # type: ignore[attr-defined]
        # For a brand-new project the DB is empty, but clear the new SiteMap
        # explicitly so no node from a previous project can appear in the tree
        # (defence in depth — the new TargetAPI already points at the new DB).
        if is_new:
            try:
                target_screen._target_api.clear()  # type: ignore[attr-defined]
                target_screen._target_api.sitemap._scope_hosts.clear()  # type: ignore[attr-defined]
            except Exception:
                # Nodes from the previous project may show up in the new one — this
                # is exactly the "artifact leaking between projects" that this block
                # was written for. error.
                logger.error("project: new project's site map not cleared", exc_info=True)
        target_screen._load_sitemap()  # type: ignore[attr-defined]

    async def _init_new_db(self, path: str) -> None:
        try:
            await init_db(path)
        except Exception as exc:
            logger.warning("_init_new_db: %s", exc)

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
                sessions.append(
                    {
                        "base_url": getattr(ev, "base_url", ""),
                        "pages_count": getattr(ev, "pages_count", 0),
                        "forms_count": getattr(ev, "forms_count", 0),
                        "endpoints_count": getattr(ev, "endpoints_count", 0),
                        "timestamp": getattr(ev, "timestamp", 0),
                    }
                )
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
        except Exception as exc:
            # The status bar will keep showing the previous project — i.e. naming
            # a file the application no longer works with.
            logger.debug("project: status bar not updated with %r: %s", name, exc)
        try:
            self._app.sub_title = f"project: {name}"
        except Exception as exc:
            logger.debug("project: window title not updated: %s", exc)
        if path and path != "new project":
            try:
                self._cfg.add_recent_project(path)
            except Exception as exc:
                # The project is open, but it will not be in the dashboard's
                # "recent" list — next time it has to be found by hand.
                logger.debug("project: %s not added to recent projects: %s", path, exc)
