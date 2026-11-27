"""Target / Site Map screen — target tree view."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.widgets import Tree

from pentool.core.logging import get_logger
from pentool.tui.header import HeaderAction, HeaderSpec
from pentool.tui.hotkeys.defaults import TARGET_BINDINGS
from pentool.tui.markup import esc
from pentool.tui.messages import SendHostToScanner, SendToRepeater, SyncScopeToProxy
from pentool.tui.mixins.ai_sync import AiModeSyncMixin
from pentool.tui.mixins.autosave import AutoSaveMixin
from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.mixins.safe_query import safe_query_one
from pentool.tui.screens.module_screen import ModuleScreen
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.resize_handle import ResizeHandle

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)


def _format_tech_profile(profile: dict) -> str:
    """Format TechProfile dict (new and legacy format) to short string."""
    parts = []

    # WAF (both formats)
    waf = profile.get("waf", {})
    waf_name = profile.get("waf_name")
    if isinstance(waf, dict) and waf.get("detected"):
        parts.append(f"WAF: {waf.get('name', '?')}")
    elif waf is True and waf_name:
        parts.append(f"WAF: {waf_name}")
    elif waf is True:
        parts.append("WAF")

    # Language (new format)
    lang = profile.get("language")
    if lang and lang != "Unknown":
        parts.append(lang)

    # Legacy language flags
    for key, label in [
        ("is_php", "PHP"),
        ("is_java", "Java"),
        ("is_dotnet", ".NET"),
        ("is_nodejs", "Node.js"),
        ("is_python", "Python"),
        ("is_golang", "Go"),
        ("is_ruby", "Ruby"),
    ]:
        if profile.get(key):
            if label not in parts:
                parts.append(label)

    # Framework (new format)
    fw = profile.get("framework")
    if fw:
        parts.append(fw)

    # Legacy framework flags
    for key, label in [
        ("is_django", "Django"),
        ("is_flask", "Flask"),
        ("is_laravel", "Laravel"),
        ("is_rails", "Rails"),
        ("is_spring", "Spring"),
        ("is_express", "Express"),
    ]:
        if profile.get(key):
            if label not in parts:
                parts.append(label)

    # CMS (new format)
    cms = profile.get("cms")
    if cms:
        parts.append(cms)

    # CDN (new format)
    cdn = profile.get("cdn")
    if cdn:
        parts.append(f"CDN:{cdn}")

    # SPA (new format)
    spa = profile.get("spa")
    if spa:
        parts.append(spa)

    # Frontend JS (may be a list ['jQuery', 'HTMX'] or a string 'jQuery, HTMX')
    frontend_js = profile.get("frontend_js", [])
    if isinstance(frontend_js, list):
        parts.extend(frontend_js)
    elif isinstance(frontend_js, str) and frontend_js.strip():
        parts.append(frontend_js)

    # CSS framework
    css_fw = profile.get("css_framework", [])
    if isinstance(css_fw, list):
        parts.extend(css_fw)
    elif isinstance(css_fw, str) and css_fw.strip():
        parts.append(css_fw)

    # OS
    os_type = profile.get("os") or profile.get("os_type")
    if os_type:
        parts.append(os_type)

    # Auth methods (may be a list ['Session', 'CSRF'] or a string 'Session, CSRF Token')
    auth = profile.get("auth_methods", [])
    if isinstance(auth, list) and auth:
        parts.append(f"Auth:{','.join(auth[:3])}")
    elif isinstance(auth, str) and auth.strip():
        parts.append(f"Auth:{auth}")

    # Server (both formats)
    server = profile.get("server_header", "") or profile.get("powered_by", "") or profile.get("server", "")
    if server and server not in parts:
        parts.append(server)

    return " | ".join(parts) if parts else ""


class TargetScreen(ContentClipboardMixin, AiModeSyncMixin, AutoSaveMixin, ModuleScreen):
    """Tree view of discovered hosts and URLs."""

    DEFAULT_CSS = _CSS

    BINDINGS = TARGET_BINDINGS

    #: Crawl worker group (ADR-11). The name is needed in two places — in the
    #: decorator and in on_unmount — so it is a constant, not a literal.
    CRAWL_GROUP = "target-crawl"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._target_api = None
        self._selected_host: str | None = None
        self._selected_node_data = None
        self._scope_config = None  # ScopeConfig for regex include/exclude rules
        self._running_save_tasks: list[str] = []  # tracked auto-save workers
        #: Site map changed since the last write. The flush happens on a short
        #: debounce (live traffic) and on unmount (lazy screens tear the node down
        #: without notice), so a single seeded host is never lost.
        self._sitemap_dirty: bool = False
        self._sitemap_save_timer = None

    #: Header buttons (see `header_spec`) → methods that run them.
    ACTIONS = {
        "add_scope": "action_add_to_scope",
        "remove_scope": "action_remove_from_scope",
        "scope_rules": "action_open_scope_rules",
        "crawl_scope": "action_crawl_scope",
        "crawl_host": "action_crawl_selected_host",
        "clear": "action_clear",
        "export": "action_export_json",
        "recon": "_header_open_recon",
    }

    def header_spec(self) -> HeaderSpec:
        """Scope and crawl actions; the "Use AI" setting stays in the config row."""
        return HeaderSpec(
            actions=(
                HeaderAction("add_scope", "★ Add to Scope"),
                HeaderAction("remove_scope", "✖ Remove from Scope"),
                HeaderAction("scope_rules", "⚙ Scope"),
                HeaderAction("crawl_scope", "🕷 Crawl Scope"),
                HeaderAction("crawl_host", "🕷 Crawl Host"),
                HeaderAction("export", "📄 Export JSON"),
                HeaderAction("recon", "🧭 Recon"),
                HeaderAction("clear", "🗑 Clear"),
            ),
        )

    def compose(self) -> ComposeResult:
        # A setting, not an action: it lives in its own row under the module header.
        with Horizontal(id="tgt-config-row"):
            # The wrapper keeps its id: `_sync_ai_visibility` toggles `#ai-crawl-box`.
            with Horizontal(id="ai-crawl-box"):
                yield Checkbox(
                    "🤖 Use AI",
                    id="cfg-ai-use",
                    value=False,
                    tooltip="When set, Spider adds AI-suggested endpoints after crawling",
                )

        # Hide the AI section on startup when ai_enabled is off
        from pentool.core.config import get_config

        if not getattr(get_config(), "ai_enabled", False):
            self._ai_hidden_on_compose = True

        with Horizontal(id="main-split"):
            yield Tree("Site Map", id="site-tree")
            yield ResizeHandle("site-tree", "detail-panel", id="target-resize-h")
            # #detail-panel is the ContentPanel itself: other places look it up
            # exactly that way (clear_content/write_to_log). This used to be a
            # Vertical with the panel inside, so `query_one("#detail-panel",
            # ContentPanel)` found nothing and `on_tree_node_selected` crashed
            # in `Vertical.clear`.
            yield ContentPanel("Details", id="detail-panel", widget_type="richlog", wrap=True, role="text-readonly")

    def on_mount(self) -> None:
        """Hide the AI section on startup when ai_enabled is off."""
        if getattr(self, "_ai_hidden_on_compose", False):
            try:
                self.query_one("#ai-crawl-box").display = False
            except NoMatches as exc:
                # The AI block stays visible while AI is off — exactly the
                # mismatch this code was written to prevent.
                logger.debug("target: AI crawl box not hidden on mount: %s", exc)
        self._init_ai_sync()

    def on_show(self) -> None:
        """Sync the AI UI whenever the screen is shown."""
        self._sync_ai_ui()

    def on_unmount(self) -> None:
        """Cancel the crawl and flush whatever the site map still owes the DB.

        A crawl runs for minutes and holds the network and the process pool:
        off-screen nobody can show its result, while the ActivityIndicator would
        keep burning. The screen's other workers are short-lived — Textual
        cancels them together with the node.

        The active-crawl counter is decremented right here: a worker torn down by
        cancellation may never reach its ``finally``, and the counter would stay
        inflated forever.

        The pending site map is written before the node disappears: with lazy
        screens this hook is the last moment the tree can be persisted, and a
        host seeded by ``--url`` used to be lost exactly here.
        """
        try:
            if getattr(self, "_sitemap_dirty", False):
                self._sitemap_dirty = False
                coro = self._do_save_sitemap()
                try:
                    self.run_worker(  # type: ignore[attr-defined]
                        coro,
                        group=self.SAVE_WORKER_GROUP,
                        exit_on_error=False,
                    )
                except Exception:
                    # The worker was not accepted (the node is already gone): close
                    # the coroutine so it does not surface as "never awaited".
                    coro.close()
                    raise
        except Exception:
            logger.error("target: site map not flushed on unmount", exc_info=True)
        try:
            cancelled = self.workers.cancel_group(self, self.CRAWL_GROUP)
        except Exception:
            # Cancelling the crawl on screen exit failed — the workers keep
            # writing to the DB of a project that is already being closed. The
            # whole cause must be visible: it decides whether their tasks hang.
            logger.exception("on_unmount: cancel_group failed")
            return
        if cancelled:
            try:
                self.app.spider_crawl_finished()  # type: ignore[attr-defined]
            except Exception:
                # The active-crawl counter stays inflated: the progress
                # indicator shows a crawl that no longer exists.
                logger.exception("on_unmount: spider_crawl_finished failed")

    def _sync_ai_ui(self) -> None:
        """Check ai_enabled and hide/show the AI widgets."""
        try:
            from pentool.core.config import get_config

            ai_on = bool(get_config().ai_enabled)
            self.query_one("#ai-crawl-box").display = ai_on
        except Exception as exc:
            # The only place where the AI block is shown/hidden from the
            # global setting; its failure is a visible mismatch.
            logger.debug("target: AI UI not synced: %s", exc)

    def project_export(self) -> dict:
        """Site map data for the JSON project file."""
        return self._get_api().export_project_data()

    def project_import(self, data: dict) -> int:
        """Put site map data from a JSON project into the open database."""
        count = self._get_api().import_project_data(data)
        self._load_sitemap()
        return count

    async def reload_from_project(self, db_path: str) -> None:
        """Re-create the SiteMap against the newly opened project."""
        await self._switch_project(is_new=False)

    async def reset_for_new_project(self) -> None:
        """Same as a reload, plus an explicit clear: the new DB is empty."""
        await self._switch_project(is_new=True)

    async def close_storage(self) -> None:
        """Save and close the SiteMap connection (called on project close)."""
        await self._close_target_api()

    async def _switch_project(self, *, is_new: bool) -> None:
        """Persist and drop the old SiteMap, then open the new one."""
        await self._close_target_api()
        self._get_api()
        if is_new:
            try:
                self._target_api.clear()
                self._target_api.sitemap._scope_hosts.clear()
            except Exception:
                # Nodes from the previous project may show up in the new one.
                logger.error("target: new project's site map not cleared", exc_info=True)
        self._load_sitemap()

    async def _close_target_api(self) -> None:
        """Save, then close: SiteMap holds one persistent SQLite connection."""
        if self._target_api is None:
            return
        try:
            await self._target_api.save()
        except Exception:
            # Unsaved changes of the previous project are lost on a switch.
            logger.warning("target: old site map not saved before switch", exc_info=True)
        try:
            await self._target_api.close()
        except Exception:
            # The connection stays open until quit: FDs and locks pile up.
            logger.warning("target: old site map connection not closed", exc_info=True)
        self._target_api = None

    def _get_api(self):
        if self._target_api is None:
            from pentool.api.target_api import TargetAPI

            db_path = str(getattr(self.app, "db_path", "") or "")
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
            self.query_one("#detail-panel", ContentPanel).clear_content()
        except NoMatches as exc:
            # Stale data from the previous project stays in Details — exactly
            # the "artifact leaking between projects" the comment above mentions.
            logger.debug("target: detail panel not cleared on reload: %s", exc)

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
            # An empty set means "scope lost across the reload" — exactly what
            # the save above prevents. Hence a traceback instead of a plain
            # line: without one the journal would only say "empty".
            logger.exception("target: scope hosts not collected before reload")
        self._load_worker(scope_hosts)

    @work(group="target-load")
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
                        # One host was not restored into scope after the reload —
                        # the tree shows it as "out of scope", which looks like a
                        # setting randomly lost. A traceback is needed: the cause
                        # may be in the DB rather than in the host itself.
                        logger.exception("target: scope not restored for %s", host)
            tree_data = api.get_tree()
            self._build_tree(tree_data)
        except Exception:
            # The tree is left over from the previous project or empty: the
            # Target screen shows something other than the open database holds.
            logger.exception("TargetScreen._load_worker failed")

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
                host_label = f"[bold green]★ {esc(host)}[/bold green] [dim green](in scope)[/dim green] ({total_reqs})"
            else:
                host_label = f"{esc(host)} ({total_reqs})"
            host_node = root.add(host_label, data={"type": "host", "host": host, "in_scope": in_scope})

            # TechDetect node — show technologies when a cached profile exists
            if in_scope:
                try:
                    from pentool.services.tech_detector import get_tech_cache

                    cached = get_tech_cache(host)
                    if cached:
                        tech_str = _format_tech_profile(cached)
                        if tech_str:
                            host_node.add_leaf(
                                f"[dim cyan]{esc(tech_str)}[/dim cyan]",
                                data={"type": "tech", "host": host},
                            )
                except Exception as exc:
                    # The tech line disappears from the tree for one host —
                    # the tree still works, but that profile stays incomplete.
                    logger.debug("target: tech leaf not added for %s: %s", host, exc)

            # Multi-level tree: split each path into segments so endpoints like
            # /api/users/123 become api → users → 123 rather than a flat list.
            for node in nodes:
                self._add_path_node_tree(host_node, host, node)

        root.expand()

    def _add_path_node_tree(self, host_node, host: str, node) -> None:
        """Insert a SiteNode into host_node, nesting by path segments (multi-level).

        /api/users/123  →  api / users / 123  (dirs auto-created, leaves are paths)
        """
        raw = node.path or "/"
        segments = [seg for seg in raw.split("/") if seg != ""] or ["/"]

        # Walk the segment tree, creating/reusing dir nodes, then add the leaf.
        parent = host_node
        for i, seg in enumerate(segments):
            if not seg:  # skip empty segments between slashes
                continue
            is_last = i == len(segments) - 1
            if is_last:
                methods_str = " ".join(sorted(node.methods)) if node.methods else "GET"
                parent.add_leaf(
                    f"{esc(seg)}  [{methods_str}] ({node.request_count})",
                    data={"type": "path", "host": host, "node": node},
                )
            else:
                parent = self._ensure_dir_child(parent, host, seg)

    @staticmethod
    def _ensure_dir_child(node, host: str, seg: str):
        """Return an existing dir child named ``seg`` under ``node`` or create one."""
        for child in node.children:
            d = child.data or {}
            if d.get("type") == "dir" and d.get("dir") == seg:
                return child
        return node.add(esc(seg), data={"type": "dir", "host": host, "dir": seg})

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if data is None:
            return
        # The details panel is rebuilt when the screen is remounted; a click that
        # arrives during that gap must be ignored, not crash the app.
        log = safe_query_one(self, "#detail-panel", ContentPanel, context="target: details panel")
        if log is None:
            return
        log.clear_content()

        if data.get("type") == "host":
            host = data["host"]
            self._selected_host = host
            self._selected_node_data = None
            api = self._get_api()
            nodes = api.get_paths(host)
            in_scope = api.sitemap.is_in_scope(host)
            scope_str = "[green]YES[/green]" if in_scope else "[red]NO[/red]"
            log.write_to_log(f"[bold]{esc(host)}[/bold]")
            log.write_to_log(f"In scope: {scope_str}")

            # TechDetect — read from the cache
            try:
                from pentool.services.tech_detector import get_tech_cache

                cached = get_tech_cache(host)
                if cached:
                    tech_str = _format_tech_profile(cached)
                    if tech_str:
                        log.write_to_log(f"[dim cyan]Tech: {esc(tech_str)}[/dim cyan]")
            except Exception:
                # The tech profile simply does not appear in Details. Expected
                # with an empty cache, yet indistinguishable from a failure
                # without a record, so a traceback: `get_tech_cache` has two
                # branches — "missing" and "broken".
                logger.exception("target: tech cache not read for %s", host)

            log.write_to_log(f"Endpoints: {len(nodes)}")
            total = sum(n.request_count for n in nodes)
            log.write_to_log(f"Total requests: {total}")
            if nodes:
                log.write_to_log("")
                log.write_to_log("[dim]Paths:[/dim]")
                for n in nodes[:20]:
                    log.write_to_log(f"  {esc(n.path)}  {' '.join(sorted(n.methods))}")

        elif data.get("type") == "path":
            node = data["node"]
            self._selected_host = data["host"]
            self._selected_node_data = node
            log.write_to_log(f"[bold]{esc(node.host)}{esc(node.path)}[/bold]")
            log.write_to_log(f"Methods: {', '.join(sorted(node.methods))}")
            log.write_to_log(f"Requests: {node.request_count}")
            log.write_to_log(f"Last seen: {node.last_seen.strftime('%Y-%m-%d %H:%M')}")
            log.write_to_log(f"In scope: {'[green]YES[/green]' if node.in_scope else '[red]NO[/red]'}")

    def on_key(self, event) -> None:
        if event.key == "m":
            # Don't intercept when a TextArea/Input is focused (typing "m").
            focused = self.focused
            if focused and hasattr(focused, "text"):
                event.prevent_default()
                return
            self.action_context_menu()
            event.prevent_default()

    def action_context_menu(self) -> None:
        """Show context menu for selected host/node (BINDINGS: m)."""
        self._show_context_menu_for_selected()

    def on_mouse_down(self, event) -> None:
        if (event.button == 1 and event.ctrl) or event.button == 3:
            self._show_context_menu_at(event.screen_x, event.screen_y)
            event.prevent_default()

    def _show_context_menu_at(self, x: int, y: int) -> None:
        if self._selected_host is None:
            return
        items = [
            ("add_to_scanner", f"🔍 Send to Scanner: {self._selected_host}"),
        ]
        # "Send to Repeater" is only meaningful for a specific path endpoint.
        if self._selected_node_data is not None:
            node = self._selected_node_data
            items.append(("send_repeater", f"↗️ Send to Repeater: {node.path}"))
        items += [
            ("add_scope", "★ Add to Scope"),
            ("remove_scope", "✖ Remove from Scope"),
        ]
        self.app.show_context_menu(items, x, y, callback=self._on_context_action)

    def _show_context_menu_for_selected(self) -> None:
        try:
            tree = self.query_one("#site-tree", Tree)
            r = tree.region
            x, y = r.x + 2, r.y + 3
        except NoMatches:
            x, y = 5, 5
        self._show_context_menu_at(x, y)

    def _on_context_action(self, action: str) -> None:
        if action == "add_to_scanner":
            self._add_host_to_scanner(self._selected_host)
        elif action == "send_repeater":
            self._send_selected_to_repeater()
        elif action == "add_scope":
            self.action_add_to_scope()
        elif action == "remove_scope":
            self.action_remove_from_scope()

    def _send_selected_to_repeater(self) -> None:
        """Send the selected path endpoint to the Repeater as a request template.

        Site nodes only store aggregated method/path, not body/headers, so this
        builds a clean GET (or the node's first method) to edit in Repeater.
        """
        node = self._selected_node_data
        if not node:
            return
        try:
            from pentool.utils.parser import ParsedRequest, build_http_request

            method = sorted(node.methods)[0] if node.methods else "GET"
            url = f"https://{node.host}{node.path}"
            raw = build_http_request(ParsedRequest(method=method, url=url, headers={}, body=""))
            self.app.post_message(SendToRepeater(raw))  # type: ignore[attr-defined]
            self.notify_user(f"Sent {method} {node.path} to Repeater", timeout=3)
        except Exception as exc:
            logger.debug("send_selected_to_repeater: %s", exc)

    def _add_host_to_scanner(self, host: str | None) -> None:
        if not host:
            return
        self.app.post_message(SendHostToScanner(host))  # type: ignore[attr-defined]

    def _header_open_recon(self) -> None:
        """Open Recon screen and pre-fill domain from selected host."""
        from urllib.parse import urlparse

        domain = ""
        try:
            node = self.query_one("#site-tree", Tree).cursor_node
            if node and hasattr(node, "label"):
                node_label = str(node.label)
                if "://" in node_label:
                    domain = urlparse(node_label).hostname or ""
                elif "." in node_label:
                    domain = node_label.split(":")[0].strip()
        except NoMatches as exc:
            # A fallback via _selected_host exists below; without a log record
            # it is impossible to tell the primary path broke. This catches
            # exactly "no tree among the widgets" — i.e. the screen is not built.
            logger.debug("target: domain from tree cursor not read: %s", exc)
        if not domain:
            domain = self._selected_host

        # Get-or-mount: Recon is lazy, so `action_switch_module` alone only
        # *starts* mounting it — pre-filling afterwards needs the widget.
        if domain:
            self.run_worker(self._prefill_recon_domain(domain))
        self.app.action_switch_module("recon")

    async def _prefill_recon_domain(self, domain: str) -> None:
        """Pre-fill ReconScreen domain input."""
        from urllib.parse import urlparse

        # Normalise: strip protocol, path, port
        domain = domain.strip().lower()
        if "://" in domain:
            domain = urlparse(domain).hostname or domain
        domain = domain.split(":")[0].split("/")[0]
        try:
            from pentool.tui.screens.recon.screen import ReconScreen

            recon = await self.app.ensure_module_screen("recon", ReconScreen)
            if recon is None:
                return
            domain_input = recon.query_one("#recon-domain")
            if hasattr(domain_input, "value"):
                domain_input.value = domain
        except Exception as exc:
            # Recon opened with an empty domain field — the user has to type it
            # in by hand even though it is selected in the tree.
            logger.debug("target: recon domain not prefilled: %s", exc)

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
            # Sync hosts/wildcards with SiteMap — fire-and-forget
            self._sync_scope_rules(result.hosts)
            self.notify_user(f"Scope saved: {summary}", timeout=3)

        self.app.push_screen(
            ScopeDialog(current_scope=current, extended=True),
            _on_result,
        )

    @work(group="target-scope", exclusive=True)
    async def _sync_scope_rules(self, hosts: list[str]) -> None:
        """Sync ScopeDialog hosts into SiteMap scope (exact + wildcard)."""
        try:
            api = self._get_api()
            # Reset all scope first
            old_hosts = list(api.sitemap._scope_hosts)
            old_wildcards = list(api.sitemap._scope_wildcards)
            for h in old_hosts:
                api.set_in_scope(h, False)
            for w in old_wildcards:
                api.set_in_scope(f"*{w}", False)
            # Set new rules
            for h in hosts:
                api.set_in_scope(h, True)
            await api.save()
            tree_data = api.get_tree()
            self._build_tree(tree_data)

            # Sync with ProxyServer.scope so its toggle reflects real state
            effective_hosts = [h for h in hosts if not h.startswith("*")]
            try:
                proxy = getattr(self.app, "_proxy", None)
                if proxy is not None:
                    proxy.set_scope(list(effective_hosts))
                from pentool.core.config import get_config

                cfg = get_config()
                cfg.scope = list(effective_hosts)
                cfg.save()
            except Exception:
                # Scope was applied in SiteMap, but Proxy never learned about it
                # and config.yaml was not updated: after a restart the old scope
                # returns while Proxy treats the new hosts as out-of-scope.
                logger.exception("_sync_scope_rules: proxy sync failed")
        except Exception:
            # Not a single host from the dialog was applied — the dialog closed
            # as a success while the tree kept the previous scope.
            logger.exception("_sync_scope_rules failed")

    @work(group="target-scope", exclusive=True)
    async def _set_scope_worker(self, host: str, in_scope: bool) -> None:
        try:
            api = self._get_api()
            api.set_in_scope(host, in_scope)
            await api.save()
            tree_data = api.get_tree()
            self._build_tree(tree_data)
            display = host if not host.startswith("*") else f"*{host}"
            msg = f"{'Added' if in_scope else 'Removed'} {display} {'to' if in_scope else 'from'} scope"
            self.notify_user(msg, severity="information")
            # Mirror the change into ProxyServer.scope — keep both modules in sync
            # Skip for wildcards (Proxy handles its own scope rules)
            if not host.startswith("*"):
                self.app.post_message(SyncScopeToProxy(host, in_scope))  # type: ignore[attr-defined]
            # Auto-detect tech stack for new in-scope hosts (fire-and-forget)
            if in_scope and not host.startswith("*"):
                asyncio.ensure_future(self._auto_detect_tech(host))
        except Exception:
            # The "in scope" checkbox was clicked but the host did not switch:
            # the user sees the click did nothing and gets no second attempt.
            logger.exception("_set_scope_worker failed for %s", host)

    async def _auto_detect_tech(self, host: str) -> None:
        """Fire-and-forget tech detection when a host is added to scope."""
        logger.info("TECHDETECT: starting for host=%s", host)
        try:
            from pentool.services.tech_detector import detect_tech

            url = host if "://" in host else f"https://{host}"
            logger.info("TECHDETECT: fetching %s", url)
            profile = await detect_tech(url)
            logger.info("TECHDETECT: profile=%s for host=%s", profile, host)
            if not profile:
                self.notify_user(f"⚠️ TechDetect for {host}: no profile returned", timeout=5)
                return
            # Check that the profile holds at least something meaningful
            has_data = any(profile.get(k) for k in ("language", "framework", "cms", "server", "waf"))
            logger.info("TECHDETECT: has_data=%s profile_keys=%s", has_data, list(profile.keys()))
            if not has_data:
                self.notify_user(f"⚠️ TechDetect for {host}: empty profile (no headers matched)", timeout=5)
                return
            tech_str = (
                _format_tech_profile(profile) or f"{profile.get('language') or '?'} / {profile.get('framework') or '?'}"
            )
            if profile.get("cms"):
                tech_str += f" / {profile['cms']}"
            self.notify_user(f"🔍 {host}: {tech_str}", timeout=6)
            logger.info("TECHDETECT: updating tree node for %s with tech=%s", host, tech_str)
            # Update the tree — add a tech node under the host
            self._update_tech_node(host, profile)
        except Exception as exc:
            logger.error("TECHDETECT: error for %s: %s", host, exc, exc_info=True)
            self.notify_user(f"⚠️ TechDetect error for {host}: {exc}", timeout=5)

    def action_clear(self) -> None:
        self._clear_worker()

    @work(group="target-scope", exclusive=True)
    async def _clear_worker(self) -> None:
        try:
            api = self._get_api()
            api.clear()
            self._build_tree({})
            self._selected_host = None
            self._selected_node_data = None
            try:
                self.query_one("#detail-panel", ContentPanel).clear_content()
            except NoMatches as exc:
                # The map is cleared but Details still holds the previous node —
                # a reference to data that no longer exists.
                logger.debug("target: details not cleared with site map: %s", exc)
            self.notify_user("Site map cleared", severity="information")
        except Exception:
            # "Clear" did not work: the map stayed on screen and no success
            # notification appeared — the only thing that will say what exactly
            # broke is the traceback.
            logger.exception("_clear_worker failed")

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
            self.notify_user("No hosts to crawl — Site Map is empty", severity="warning")
            return
        self._maybe_crawl_hosts(hosts)

    def action_crawl_selected_host(self) -> None:
        """Crawl only the host currently selected in the tree."""
        if not self._selected_host:
            self.notify_user("Select a host in the tree first", severity="warning")
            return
        self._maybe_crawl_hosts([self._selected_host])

    def _maybe_crawl_hosts(self, hosts: list[str]) -> None:
        """Ask for confirmation when this crawl has already run."""
        from pentool.api.spider_api import SpiderAPI

        # Check whether these hosts have already been crawled
        # Normalise the URL: add the scheme when it is missing
        normalized = [h if "://" in h else f"https://{h}" for h in hosts]
        all_cached = all(SpiderAPI.has_cached_result(h) for h in normalized)
        if all_cached:
            self._ask_recrawl(hosts)
        else:
            self._crawl_hosts_worker(hosts)

    def _ask_recrawl(self, hosts: list[str]) -> None:
        """Show the dialog: re-crawl or skip."""
        from pentool.tui.dialogs.recrawl_dialog import RecrawlDialog

        host = hosts[0] if hosts else "unknown"

        def on_dialog(result: str | None) -> None:
            if result == "recrawl":
                self._crawl_hosts_worker(hosts)

        self.app.push_screen(RecrawlDialog(host), on_dialog)

    @work(group=CRAWL_GROUP, exclusive=True)
    async def _crawl_hosts_worker(self, hosts: list[str]) -> None:
        from pentool.api.spider_api import SpiderAPI, SpiderConfig

        self.notify_user(
            f"Crawling {len(hosts)} host{'s' if len(hosts) != 1 else ''}…",
            timeout=3,
        )
        # Keeps ActivityIndicator's Spider glyph lit for the duration of this
        # crawl (no dedicated SpiderScreen anymore; this Target path builds its
        # own SpiderAPI and drives the counter directly).
        try:
            self.app.spider_crawl_started()  # type: ignore[attr-defined]
        except Exception:
            # The crawl indicator will not light up while the crawl runs on: the
            # user sees a minute of silence with no sign of work. A traceback
            # because the on-screen counter now diverges from reality for good.
            logger.exception("target: spider indicator not started")
        # "🤖 Use AI" toolbar checkbox — when set, add AI-suggested endpoints
        # after each host's crawl.
        use_ai = False
        try:
            use_ai = self.query_one("#cfg-ai-use", Checkbox).value
        except NoMatches as exc:
            # Assume "off" — that is safe, but with the checkbox actually on
            # the AI suggestions simply will not appear.
            logger.debug("target: AI checkbox not read, assuming off: %s", exc)
        logger.info("action_crawl_scope: use_ai=%s (AI-enabled checkbox)", use_ai)
        total_pages = 0
        total_endpoints = 0
        total_js = 0
        total_errors = 0
        api = self._get_api()
        db_path = str(getattr(self.app, "db_path", "") or "")

        def _on_page_async(url: str) -> None:
            """Lazy feed: each discovered URL lands in the Site Map tree
            immediately (not once the whole crawl finishes). Runs in the async
            worker's loop alongside the crawl."""
            try:
                from pentool.utils.parser import ParsedRequest

                # count=False: this is a discovery event, not a real HTTP request.
                # Re-crawling the same page must not inflate the node counter.
                api.add_request(ParsedRequest(method="GET", url=url), count=False)
            except Exception:
                # The discovered URL never reached the SiteMap: the page was
                # crawled but is not in the tree — and this happens per page.
                logger.exception("lazy add failed for %s", url)
            try:
                self.call_after_refresh(self._refresh_tree)
            except Exception:
                # Lazy feed only works together with a redraw: without one the
                # found URLs pile up in the model but not in the tree.
                logger.exception("target: tree refresh not scheduled after page")

        # Create one SpiderAPI for the whole crawl, not one per host
        # (prevents a process-pool leak).
        try:
            spider = SpiderAPI(config=SpiderConfig(js_render=True))
            for host in hosts:
                url = host if "://" in host else f"https://{host}"
                try:
                    result = await spider.crawl(url, db_path=db_path, on_page=_on_page_async)
                except Exception:
                    # One host failed while the rest keep crawling — but the end
                    # result is "errors: N" with no reason; the traceback shows
                    # whether it was the network, a timeout or the parser.
                    logger.exception("action_crawl_scope: crawl failed for %s", host)
                    total_errors += 1
                    continue
                total_pages += len(result.pages)
                total_endpoints += len(result.endpoints)
                total_js += len(result.js_files)
                total_errors += len(result.errors)
                if use_ai:
                    ai_added = await self._ai_suggest_endpoints(api, url)
                    if ai_added:
                        self.notify_user(f"AI endpoints added: {ai_added}", timeout=3)
        except asyncio.CancelledError:
            raise  # re-raise after cleanup
        finally:
            try:
                self.app.spider_crawl_finished()  # type: ignore[attr-defined]
            except Exception:
                # The active-crawl counter was not decremented — the Spider
                # indicator stays lit forever after this crawl. This is the only
                # trace of the counter leak, hence the traceback.
                logger.exception("target: spider indicator not finished")

        self.call_after_refresh(self._refresh_tree)
        try:
            await api.save()
        except Exception:
            # What this crawl found lives only in memory: the next app start
            # will not see it.
            logger.exception("action_crawl_scope: save failed")

        msg = (
            f"Crawl done: {total_pages} page(s), {total_endpoints} endpoint(s), "
            f"{total_js} file(s) across {len(hosts)} host(s)"
        )
        if total_errors:
            msg += f", {total_errors} error(s)"
        self.notify_user(msg, severity="information")

    async def _ai_suggest_endpoints(self, api, url: str) -> int:
        """Ask the AI for non-obvious endpoints and register them in the SiteMap.

        Returns how many endpoints were added (0 if AI is off or returned nothing).
        Called from _crawl_hosts_worker when the "🤖 Use AI" checkbox is set.
        """
        try:
            from pentool.core.config import get_config
            from pentool.services.ai import get_active_backend, get_ai, start_ai
            from pentool.utils.parser import ParsedRequest

            cfg = get_config()
            # Reuse the already-started MCP server (started on ai_enabled or at
            # app mount) instead of creating a fresh, never-started backend —
            # a fresh get_ai() has no live subprocess, so its generate() fails
            # with "the server is not running".
            # i18n-ok: the message is quoted from the backend, not our prose
            backend = get_active_backend()
            if backend is None:
                backend = get_ai(cfg)
                if backend is None:
                    return 0
                ok = await start_ai(cfg)
                if not ok:
                    return 0
                backend = get_active_backend()
            if backend is None:
                return 0

            # Already-discovered context: all hosts + their paths from the SiteMap.
            known: list[str] = []
            for h in api.get_hosts():
                try:
                    for node in api.get_paths(h):
                        if node.path and node.path != "/":
                            known.append(f"https://{h}{node.path}")
                except Exception as exc:
                    # One host returned no paths — the AI suggestion gets poorer,
                    # but the crawl continues. The record names the host.
                    logger.debug("target: paths for %s not read for AI context: %s", h, exc)
                    continue

            # Use js_render for SPA to get full rendered HTML
            from pentool.services.tech_detector import detect_tech, get_cached_tech

            cached = get_cached_tech(url)
            use_js = bool(cached and cached.get("spa"))
            tech_profile_raw = await detect_tech(url, js_render=use_js)
            tech_profile = (
                tech_profile_raw
                if tech_profile_raw is None
                else getattr(tech_profile_raw, "to_context_dict", lambda: str(tech_profile_raw))()
            )
            prompt_data = {
                "url": url,
                "tech_stack": tech_profile,
                "links": known,
            }
            result = await backend.generate("crawl_endpoints", prompt_data)
            if isinstance(result, dict):
                _nitems = len(result.get("items") or [])
                logger.info(
                    "_ai_suggest_endpoints: %s gen result items=%d %s",
                    url,
                    _nitems,
                    "RAW:" + str(result.get("raw", ""))[:120] if _nitems == 0 else "",
                )
            if not result:
                return 0
            items = result if isinstance(result, list) else result.get("items", [])
            if not items:
                return 0

            added = 0
            import aiohttp as _aiohttp

            _timeout = _aiohttp.ClientTimeout(total=5)
            async with _aiohttp.ClientSession(timeout=_timeout) as session:
                for item in items:
                    method = str(item.get("method", "GET")).upper()
                    path = str(item.get("path", "")).strip()
                    if not path.startswith("/"):
                        path = "/" + path
                    full_url = f"{url}{path}"
                    # Validate endpoint with a quick HEAD (fallback to GET)
                    valid = False
                    try:
                        async with session.head(full_url, ssl=False) as resp:
                            if resp.status < 500:
                                valid = True
                    except Exception as exc:
                        # HEAD is unsupported by the server or the network dropped:
                        # GET is tried below. Expected, yet the reason matters.
                        logger.debug("target: HEAD probe failed for %s: %s", full_url, exc)
                    if not valid:
                        try:
                            async with session.get(full_url, ssl=False) as resp:
                                if resp.status < 500:
                                    valid = True
                        except Exception as exc:
                            # Both probes failed — the endpoint is discarded as
                            # nonexistent even though it could be alive.
                            logger.debug("target: GET probe failed for %s: %s", full_url, exc)
                    if not valid:
                        continue
                    # count=False: AI-suggested paths are discoveries, not real HTTP —
                    # a repeated suggestion must not inflate the node counter.
                    try:
                        api.add_request(ParsedRequest(method=method, url=full_url), count=False)
                        added += 1
                    except Exception as exc:
                        # The AI-suggested endpoint did not reach the map — the
                        # "added" counter below will under-report.
                        logger.debug("target: AI endpoint %s not added: %s", full_url, exc)
                        continue
            return added
        except Exception as exc:
            logger.warning("_ai_suggest_endpoints failed: %s", exc, exc_info=True)
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

    @work(group="target-export", exclusive=True)
    async def _export_worker(self, path: str) -> None:
        try:
            api = self._get_api()
            api.export_json(path)
            self.notify_user(f"Exported: {path}", severity="information")
        except Exception as exc:
            self.err(exc, "Export failed")

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
                parsed_req.method,
                parsed_req.url,
                len(api.get_hosts()),
            )
            self.call_after_refresh(self._refresh_tree)
            # Persist soon, not "every 20 requests": with `--url/--smart` the seed
            # adds exactly ONE host, so the counter never reached 20 and the host
            # was missing from the project after a restart ("the host does not
            # land in Target"). A short debounce keeps batched writes for live
            # traffic and guarantees a flush for the single-host case.
            self._mark_sitemap_dirty()
        except Exception as exc:
            logger.warning("add_request_from_proxy: %s", exc)

    def _mark_sitemap_dirty(self, delay: float = 2.0) -> None:
        """Schedule a site-map flush shortly after the last change."""
        try:
            self._sitemap_dirty = True
            timer = getattr(self, "_sitemap_save_timer", None)
            if timer is not None:
                timer.stop()
            self._sitemap_save_timer = self.set_timer(delay, self._flush_sitemap_sync)
        except Exception:
            # No timer means no delayed flush; the unmount hook still tries once.
            logger.debug("target: sitemap flush not scheduled", exc_info=True)

    def _flush_sitemap_sync(self) -> None:
        """Flush from a timer/manual call: start a tracked save worker."""
        if not getattr(self, "_sitemap_dirty", False):
            return
        if not self.is_mounted:
            # The node is being torn down: unmount's own flush handles the write,
            # and a worker started here would never run (its coroutine would be
            # reported as "never awaited").
            return
        self._sitemap_dirty = False
        try:
            self._start_save_worker(self._do_save_sitemap(), f"target-save-{time.monotonic_ns()}")
        except Exception:
            self._sitemap_dirty = True
            logger.error("target: site map flush not started", exc_info=True)

    async def flush_sitemap(self) -> None:
        """Awaitable flush — used after the `--url` seed so the host is in the DB."""
        if not getattr(self, "_sitemap_dirty", False):
            return
        self._sitemap_dirty = False
        await self._do_save_sitemap()

    async def _do_save_sitemap(self) -> None:
        try:
            api = self._get_api()
            await api.save()
        except Exception:
            # The site map was not saved: the next launch opens the project
            # without it. That is data loss — an error with a traceback.
            logger.error("_do_save_sitemap: site map not saved", exc_info=True)

    def _update_tech_node(self, host: str, profile: dict) -> None:
        """Update or add a tech-info leaf under the host node in the tree.

        Called from auto_scope.py after TechDetect completes.
        """
        try:
            tree = self.query_one("#site-tree", Tree)
            # Find the host node by scanning root children
            for child in tree.root.children:
                data = child.data
                if isinstance(data, dict) and data.get("host") == host:
                    # Remove old tech node if exists
                    to_remove = [c for c in child.children if isinstance(c.data, dict) and c.data.get("type") == "tech"]
                    for c in to_remove:
                        child.remove(c)
                    # Add new tech node
                    tech_str = _format_tech_profile(profile)
                    if tech_str:
                        child.add_leaf(
                            f"[dim cyan]{esc(tech_str)}[/dim cyan]",
                            data={"type": "tech", "host": host},
                        )
                    break
        except Exception as exc:
            logger.debug("_update_tech_node: %s", exc)

    def _refresh_tree(self) -> None:
        try:
            api = self._get_api()
            tree_data = api.sitemap.get_tree()
            logger.debug("_refresh_tree: rebuilding tree with %d host(s)", len(tree_data))
            self._build_tree(tree_data)
        except Exception as exc:
            logger.warning("_refresh_tree: %s", exc)
