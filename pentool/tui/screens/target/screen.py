"""Target / Site Map screen — target tree view."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import RichLog, Static, Tree

from pentool.core.logging import get_logger
from pentool.tui.messages import SendHostToScanner, SyncScopeToProxy
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)


class TargetScreen(Widget):
    """Tree view of discovered hosts and URLs."""

    DEFAULT_CSS = _CSS

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._target_api = None
        self._selected_host: str | None = None
        self._selected_node_data = None
        self._scope_config = None  # ScopeConfig for regex include/exclude rules

    def compose(self) -> ComposeResult:
        with Horizontal(id="toolbar"):
            yield ToolbarButton("★ Add to Scope",      "btn-add-scope")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("✖ Remove from Scope", "btn-remove-scope")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("⚙ Scope Rules",       "btn-scope-rules")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton(
                "🕷 Crawl Scope", "btn-crawl-scope",
                tooltip="Crawl every in-scope host with the Spider"
            )
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton(
                "🕷 Crawl Host", "btn-crawl-host",
                tooltip="Crawl the selected host in the tree with the Spider"
            )
            yield Static(" │ ", classes="toolbar-sep")
            yield Checkbox(
                "🤖 Use AI", id="cfg-ai-use", value=False,
                tooltip="When set, Spider adds AI-suggested endpoints after crawling"
            )
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("🗑 Clear",             "btn-clear")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("📄 Export JSON",       "btn-export")

        with Horizontal(id="main-split"):
            yield Tree("Site Map", id="site-tree")
            yield ResizeHandle("site-tree", "detail-panel", id="target-resize-h")
            with Vertical(id="detail-panel"):
                yield Static("Details", classes="detail-label")
                yield RichLog(id="detail-log", markup=True, highlight=False)

        yield Static(
            "Scope: Add/Remove Scope  │  M: Context menu",
            id="status-bar",
        )

    def on_mount(self) -> None:
        pass  # data is only loaded explicitly via a project or the Refresh button

    def _get_api(self):
        if self._target_api is None:
            from pentool.api.target_api import TargetAPI
            db_path = getattr(self.app, "db_path", "") or getattr(self.app, "_db_path", "")
            self._target_api = TargetAPI(db_path=db_path)
        return self._target_api

    def _load_sitemap(self) -> None:
        # Reset selection/details BEFORE the async reload — otherwise a stale
        # node from the previous project stays shown in the Details panel
        # until the user clicks something in the new tree (looks like an
        # artifact "leaking" between projects).
        self._selected_host = None
        self._selected_node_data = None
        try:
            self.query_one("#detail-log", RichLog).clear()
        except Exception:
            pass

        # Save current scope hosts before reload
        scope_hosts: set[str] = set()
        try:
            api = self._target_api
            if api is not None:
                # Defense in depth: SiteMap now tracks scope in its own
                # _scope_hosts set (independent of whether a node exists
                # yet) and load() re-seeds it from the DB's in_scope
                # column — so this manual save/restore is no longer the
                # only thing keeping scope alive across a reload. Kept
                # anyway in case _target_api is swapped for a fresh
                # instance (whose _scope_hosts would start empty) between
                # scope changes and the reload.
                for host in api.sitemap.get_hosts():
                    if api.sitemap.is_in_scope(host):
                        scope_hosts.add(host)
        except Exception:
            pass
        self._load_worker(scope_hosts)

    @work
    async def _load_worker(self, scope_hosts: set[str] | None = None) -> None:
        try:
            api = self._get_api()
            await api.load()
            # Restore scope for hosts that were marked before reload
            if scope_hosts:
                for host in scope_hosts:
                    try:
                        api.set_in_scope(host, True)
                    except Exception:
                        pass
            tree_data = api.get_tree()
            self._build_tree(tree_data)
        except Exception as exc:
            logger.warning("TargetScreen._load_worker: %s", exc)

    def _build_tree(self, tree_data: dict) -> None:
        tree = self.query_one("#site-tree", Tree)
        tree.clear()
        root = tree.root
        total_hosts = len(tree_data)
        root.label = f"Site Map ({total_hosts} hosts)"

        api = self._get_api()
        for host, nodes in tree_data.items():
            total_reqs = sum(n.request_count for n in nodes)
            in_scope = api.sitemap.is_in_scope(host)
            if in_scope:
                host_label = f"[bold green]★ {host}[/bold green] [dim green](in scope)[/dim green] ({total_reqs})"
            else:
                host_label = f"{host} ({total_reqs})"
            host_node = root.add(host_label, data={"type": "host", "host": host, "in_scope": in_scope})

            for node in nodes:
                methods_str = " ".join(sorted(node.methods))
                path_label = f"{node.path}  [{methods_str}] ({node.request_count})"
                host_node.add_leaf(
                    path_label,
                    data={"type": "path", "host": host, "node": node},
                )

        root.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if data is None:
            return
        log = self.query_one("#detail-log", RichLog)
        log.clear()

        if data.get("type") == "host":
            host = data["host"]
            self._selected_host = host
            self._selected_node_data = None
            api = self._get_api()
            nodes = api.get_paths(host)
            in_scope = api.sitemap.is_in_scope(host)
            scope_str = "[green]YES[/green]" if in_scope else "[red]NO[/red]"
            log.write(f"[bold]{host}[/bold]")
            log.write(f"In scope: {scope_str}")
            log.write(f"Endpoints: {len(nodes)}")
            total = sum(n.request_count for n in nodes)
            log.write(f"Total requests: {total}")
            if nodes:
                log.write("")
                log.write("[dim]Paths:[/dim]")
                for n in nodes[:20]:
                    log.write(f"  {n.path}  {' '.join(sorted(n.methods))}")

        elif data.get("type") == "path":
            node = data["node"]
            self._selected_host = data["host"]
            self._selected_node_data = node
            log.write(f"[bold]{node.host}{node.path}[/bold]")
            log.write(f"Methods: {', '.join(sorted(node.methods))}")
            log.write(f"Requests: {node.request_count}")
            log.write(f"Last seen: {node.last_seen.strftime('%Y-%m-%d %H:%M')}")
            log.write(f"In scope: {'[green]YES[/green]' if node.in_scope else '[red]NO[/red]'}")


    def on_key(self, event) -> None:
        if event.key == "m":
            self._show_context_menu_for_selected()
            event.prevent_default()

    def on_mouse_down(self, event) -> None:
        if (event.button == 1 and event.ctrl) or event.button == 3:
            self._show_context_menu_at(event.screen_x, event.screen_y)
            event.prevent_default()

    def _show_context_menu_at(self, x: int, y: int) -> None:
        if self._selected_host is None:
            return
        items = [
            ("add_to_scanner", f"🔍 Send to Scanner: {self._selected_host}"),
            ("add_scope",      "★ Add to Scope"),
            ("remove_scope",   "✖ Remove from Scope"),
        ]
        self.app.show_context_menu(items, x, y, callback=self._on_context_action)

    def _show_context_menu_for_selected(self) -> None:
        try:
            tree = self.query_one("#site-tree", Tree)
            r = tree.region
            x, y = r.x + 2, r.y + 3
        except Exception:
            x, y = 5, 5
        self._show_context_menu_at(x, y)

    def _on_context_action(self, action: str) -> None:
        if action == "add_to_scanner":
            self._add_host_to_scanner(self._selected_host)
        elif action == "add_scope":
            self.action_add_to_scope()
        elif action == "remove_scope":
            self.action_remove_from_scope()

    def _add_host_to_scanner(self, host: str | None) -> None:
        if not host:
            return
        self.app.post_message(SendHostToScanner(host))  # type: ignore[attr-defined]


    @on(ToolbarButton.Pressed, "#btn-add-scope")
    def on_btn_add_scope(self, _: ToolbarButton.Pressed) -> None:
        self.action_add_to_scope()

    @on(ToolbarButton.Pressed, "#btn-remove-scope")
    def on_btn_remove_scope(self, _: ToolbarButton.Pressed) -> None:
        self.action_remove_from_scope()

    @on(ToolbarButton.Pressed, "#btn-scope-rules")
    def on_btn_scope_rules(self, _: ToolbarButton.Pressed) -> None:
        self.action_open_scope_rules()

    @on(ToolbarButton.Pressed, "#btn-crawl-scope")
    def on_btn_crawl_scope(self, _: ToolbarButton.Pressed) -> None:
        self.action_crawl_scope()

    @on(ToolbarButton.Pressed, "#btn-crawl-host")
    def on_btn_crawl_host(self, _: ToolbarButton.Pressed) -> None:
        self.action_crawl_selected_host()

    @on(ToolbarButton.Pressed, "#btn-clear")
    def on_btn_clear(self, _: ToolbarButton.Pressed) -> None:
        self.action_clear()

    @on(ToolbarButton.Pressed, "#btn-export")
    def on_btn_export(self, _: ToolbarButton.Pressed) -> None:
        self.action_export_json()

    def action_add_to_scope(self) -> None:
        if self._selected_host:
            self._set_scope_worker(self._selected_host, True)

    def action_remove_from_scope(self) -> None:
        if self._selected_host:
            self._set_scope_worker(self._selected_host, False)

    def action_open_scope_rules(self) -> None:
        from pentool.tui.dialogs.scope_dialog import ScopeConfig, ScopeDialog

        current = self._scope_config if self._scope_config is not None else ScopeConfig()

        def _on_result(result: ScopeConfig | None) -> None:
            if result is None:
                return
            self._scope_config = result
            inc = len(result.regex_include)
            exc = len(result.regex_exclude)
            hosts = len(result.hosts)
            parts = []
            if hosts:
                parts.append(f"{hosts} host{'s' if hosts != 1 else ''}")
            if inc:
                parts.append(f"{inc} include pattern{'s' if inc != 1 else ''}")
            if exc:
                parts.append(f"{exc} exclude pattern{'s' if exc != 1 else ''}")
            summary = ", ".join(parts) if parts else "no filters"
            self.app.notify(f"Scope rules saved: {summary}", timeout=3)

        self.app.push_screen(
            ScopeDialog(current_scope=current, extended=True),
            _on_result,
        )

    @work
    async def _set_scope_worker(self, host: str, in_scope: bool) -> None:
        try:
            api = self._get_api()
            api.set_in_scope(host, in_scope)
            await api.save()
            tree_data = api.get_tree()
            self._build_tree(tree_data)
            msg = f"{'Added' if in_scope else 'Removed'} {host} {'to' if in_scope else 'from'} scope"
            self.app.notify(msg, severity="information")
            # Mirror the change into ProxyServer.scope — keep both modules in sync
            self.app.post_message(SyncScopeToProxy(host, in_scope))  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("_set_scope_worker: %s", exc)

    def action_clear(self) -> None:
        self._clear_worker()

    @work
    async def _clear_worker(self) -> None:
        try:
            api = self._get_api()
            api.clear()
            self._build_tree({})
            self._selected_host = None
            self._selected_node_data = None
            try:
                self.query_one("#detail-log", RichLog).clear()
            except Exception:
                pass
            self.app.notify("Site map cleared", severity="information")
        except Exception as exc:
            logger.warning("_clear_worker: %s", exc)

    # ── Crawler (uses SpiderAPI / AsyncSpider) ───────────────────────────────
    #
    # The Spider has no dedicated module/tab in the TUI (see docs) — crawling
    # runs from here, in Target. These two toolbar triggers call SpiderAPI
    # directly and feed discovered pages back into the SiteMap, matching what
    # Send to Scanner/context menu users would expect from "crawl this scope".
    # The "🤖 Use AI" toolbar checkbox adds AI-suggested endpoints (see
    # _ai_suggest_endpoints) after each host's crawl.

    def action_crawl_scope(self) -> None:
        """Crawl every in-scope host (falls back to all known hosts if scope
        is empty, mirroring ProxyServer.is_in_scope's "empty scope = all in
        scope" convention)."""
        api = self._get_api()
        hosts = [h for h in api.get_hosts() if api.sitemap.is_in_scope(h)]
        if not hosts:
            hosts = api.get_hosts()
        if not hosts:
            self.app.notify("No hosts to crawl — Site Map is empty", severity="warning")
            return
        self._crawl_hosts_worker(hosts)

    def action_crawl_selected_host(self) -> None:
        """Crawl only the host currently selected in the tree."""
        if not self._selected_host:
            self.app.notify("Select a host in the tree first", severity="warning")
            return
        self._crawl_hosts_worker([self._selected_host])

    @work
    async def _crawl_hosts_worker(self, hosts: list[str]) -> None:
        from pentool.api.spider_api import SpiderAPI, SpiderConfig

        self.app.notify(
            f"Crawling {len(hosts)} host{'s' if len(hosts) != 1 else ''}…",
            timeout=3,
        )
        # Keeps ActivityIndicator's Spider glyph lit for the duration of this
        # crawl (no dedicated SpiderScreen anymore; this Target path builds its
        # own SpiderAPI and drives the counter directly).
        try:
            self.app.spider_crawl_started()  # type: ignore[attr-defined]
        except Exception:
            pass
        # "🤖 Use AI" toolbar checkbox — when set, add AI-suggested endpoints
        # after each host's crawl.
        use_ai = False
        try:
            use_ai = self.query_one("#cfg-ai-use", Checkbox).value
        except Exception:
            pass
        total_pages = 0
        total_errors = 0
        api = self._get_api()
        db_path = getattr(self.app, "db_path", "") or getattr(self.app, "_db_path", "")

        def _on_page_async(url: str) -> None:
            """Lazy feed: each discovered URL lands in the Site Map tree
            immediately (not once the whole crawl finishes). Runs in the async
            worker's loop alongside the crawl."""
            try:
                from pentool.utils.parser import ParsedRequest
                api.add_request(ParsedRequest(method="GET", url=url))
            except Exception as exc:
                logger.debug("lazy add %s: %s", url, exc)
            try:
                self.call_after_refresh(self._refresh_tree)
            except Exception:
                pass

        try:
            for host in hosts:
                url = host if "://" in host else f"https://{host}"
                # respect_scope defaults True — stay on the target host/subdomains,
                # never crawl external links.
                spider = SpiderAPI(config=SpiderConfig())
                try:
                    result = await spider.crawl(url, db_path=db_path, on_page=_on_page_async)
                except Exception as exc:
                    logger.warning("action_crawl_scope: crawl failed for %s: %s", host, exc)
                    total_errors += 1
                    continue
                total_pages += len(result.pages)
                total_errors += len(result.errors)
                if use_ai:
                    ai_added = await self._ai_suggest_endpoints(api, url)
                    if ai_added:
                        self.app.notify(f"AI endpoints added: {ai_added}", timeout=3)
        finally:
            try:
                self.app.spider_crawl_finished()  # type: ignore[attr-defined]
            except Exception:
                pass

        self.call_after_refresh(self._refresh_tree)
        try:
            await api.save()
        except Exception as exc:
            logger.debug("action_crawl_scope: save failed: %s", exc)

        msg = f"Crawl done: {total_pages} page(s) found across {len(hosts)} host(s)"
        if total_errors:
            msg += f", {total_errors} error(s)"
        self.app.notify(msg, severity="information")

    async def _ai_suggest_endpoints(self, api, url: str) -> int:
        """Ask the AI for non-obvious endpoints and register them in the SiteMap.

        Returns how many endpoints were added (0 if AI is off or returned nothing).
        Called from _crawl_hosts_worker when the "🤖 Use AI" checkbox is set.
        """
        try:
            from pentool.services.ai import get_ai
            from pentool.core.config import get_config
            from pentool.utils.parser import ParsedRequest

            cfg = get_config()
            backend = get_ai(cfg)
            if backend is None:
                return 0

            # Already-discovered context: all hosts + their paths from the SiteMap.
            known: list[str] = []
            for h in api.get_hosts():
                try:
                    for node in api.get_paths(h):
                        if node.path and node.path != "/":
                            known.append(f"https://{h}{node.path}")
                except Exception:
                    continue

            result = await backend.generate("crawl_endpoints", {
                "url": url,
                "links": known,
            })
            if not result:
                return 0
            items = result if isinstance(result, list) else result.get("items", [])
            if not items:
                return 0

            added = 0
            for item in items:
                method = str(item.get("method", "GET")).upper()
                path = str(item.get("path", "")).strip()
                if not path.startswith("/"):
                    path = "/" + path
                # Skip certainty-empty or already-known. Simple dedupe vs known.
                try:
                    api.add_request(ParsedRequest(method=method, url=f"{url}{path}"))
                    added += 1
                except Exception:
                    continue
            return added
        except Exception as exc:
            logger.debug("_ai_suggest_endpoints failed: %s", exc)
            return 0

    def action_export_json(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if path:
                self._export_worker(path)

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.SAVE, title="Export Site Map"),
            _on_path,
        )

    @work
    async def _export_worker(self, path: str) -> None:
        try:
            api = self._get_api()
            api.export_json(path)
            self.app.notify(f"Exported: {path}", severity="information")
        except Exception as exc:
            self.app.notify(f"Export failed: {exc}", severity="error")

    def add_request_from_proxy(self, req) -> None:
        """Called from proxy on a new request — updates the map in real time."""
        try:
            from pentool.utils.parser import ParsedRequest
            if isinstance(req, ParsedRequest):
                parsed_req = req
            else:
                # InterceptedRequest → ParsedRequest
                parsed_req = ParsedRequest(
                    method=req.method,
                    url=req.url,
                    headers=req.headers,
                    body=req.body,
                )
            api = self._get_api()
            api.add_request(parsed_req)
            logger.debug(
                "add_request_from_proxy: added %s %s (hosts now: %d)",
                parsed_req.method, parsed_req.url, len(api.get_hosts()),
            )
            self.call_after_refresh(self._refresh_tree)
            # Persist to DB (batches of ~20 requests)
            self._save_counter = getattr(self, "_save_counter", 0) + 1
            if self._save_counter % 20 == 0:
                self.run_worker(self._do_save_sitemap())
        except Exception as exc:
            logger.warning("add_request_from_proxy: %s", exc)

    async def _do_save_sitemap(self) -> None:
        try:
            api = self._get_api()
            await api.save()
        except Exception as exc:
            logger.debug("_do_save_sitemap: %s", exc)

    def _refresh_tree(self) -> None:
        try:
            api = self._get_api()
            tree_data = api.sitemap.get_tree()
            logger.debug("_refresh_tree: rebuilding tree with %d host(s)", len(tree_data))
            self._build_tree(tree_data)
        except Exception as exc:
            logger.warning("_refresh_tree: %s", exc)
