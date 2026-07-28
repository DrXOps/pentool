"""Target / Site Map screen — target tree view."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import RichLog, Static, Tree

from pentool.core.logging import get_logger
from pentool.tui.messages import SendHostToScanner, SyncScopeToProxy
from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.tui.widgets.resize_handle import ResizeHandle
from pathlib import Path

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
            yield ToolbarButton("↺ Reload from DB",     "btn-refresh")
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
            "Refresh: Reload site map  │  Scope: Add/Remove Scope  │  M: Context menu",
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
        # Save current scope hosts before reload
        scope_hosts: set[str] = set()
        try:
            api = self._target_api
            if api is not None:
                for host in api.sitemap.hosts():
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
                        await api.set_in_scope(host, True)
                    except Exception:
                        pass
            tree_data = await api.get_tree()
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

    @on(ToolbarButton.Pressed, "#btn-refresh")
    def on_btn_refresh(self, _: ToolbarButton.Pressed) -> None:
        self._load_sitemap()

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
        from pentool.tui.dialogs.scope_dialog import ScopeDialog, ScopeConfig

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
            await api.set_in_scope(host, in_scope)
            await api.save()
            tree_data = await api.get_tree()
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
            await api.clear()
            self._build_tree({})
            self.app.notify("Site map cleared", severity="information")
        except Exception as exc:
            logger.warning("_clear_worker: %s", exc)

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
            await api.export_json(path)
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
            self.call_after_refresh(self._refresh_tree)
            # Persist to DB (batches of ~20 requests)
            self._save_counter = getattr(self, "_save_counter", 0) + 1
            if self._save_counter % 20 == 0:
                self.run_worker(self._do_save_sitemap())
        except Exception as exc:
            logger.warning("add_request_from_proxy: %s", exc)

    @work
    async def _save_sitemap_worker(self) -> None:
        try:
            api = self._get_api()
            await api.save()
        except Exception as exc:
            logger.debug("_save_sitemap_worker: %s", exc)

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
            self._build_tree(tree_data)
        except Exception as exc:
            logger.warning("_refresh_tree: %s", exc)
