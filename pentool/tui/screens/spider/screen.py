"""SpiderScreen — full site crawler."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")
from textual.widgets import (
    Button,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)

from pentool.core.logging import get_logger
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox

logger = get_logger(__name__)


class SpiderScreen(Widget):
    """Recursive site crawler — Spider."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("f5", "start_spider", "Start Spider", show=False),
        Binding("f6", "stop_spider", "Stop", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._spider = None
        # NOT named `_running` — that name collides with
        # textual.message_pump.MessagePump._running, an internal attribute
        # every Widget already has (True while its own message loop is
        # active, which is essentially always once mounted — nothing to do
        # with whether a crawl is in progress). Shadowing it here used to
        # make ActivityIndicator's Spider glyph read "active" almost
        # immediately after startup, before Start was ever pressed.
        self._crawl_running = False
        self._result = None
        self._pages_count = 0
        self._max_pages = 100

    def compose(self) -> ComposeResult:
        with Horizontal(id="spider-toolbar"):
            yield Button("🕷 Start", id="btn-spider-start", variant="success")
            yield Static(" │ ", classes="toolbar-sep")
            yield Button("■ Stop", id="btn-spider-stop", variant="error")
            yield Static(" │ ", classes="toolbar-sep")
            yield Button("⚡ Scan Found", id="btn-scan-found", variant="warning")
            yield Static(" │ ", classes="toolbar-sep")
            yield Button("🗑 Clear", id="btn-spider-clear", variant="default")

        with Horizontal(id="config-panel"):
            with Vertical(id="url-group"):
                yield Label("Target URL:")
                yield Input(placeholder="https://example.com", id="target-url", compact=True)

            with Vertical(id="settings-group"):
                yield Label("Settings:")
                with Horizontal(classes="config-row"):
                    yield Label("Max depth:")
                    yield Input(value="3", id="cfg-depth", type="integer", compact=True)
                with Horizontal(classes="config-row"):
                    yield Label("Max pages:")
                    yield Input(value="100", id="cfg-pages", type="integer", compact=True)
                with Horizontal(classes="config-row"):
                    yield Label("Concurrency:")
                    yield Input(value="5", id="cfg-concurrency", type="integer", compact=True)
                yield Checkbox("Stay in scope", value=True, id="cfg-scope")
                yield Checkbox("Follow JS files", value=True, id="cfg-js")

        with Horizontal(id="progress-area"):
            yield ProgressBar(total=100, id="spider-progress", show_eta=False)
            yield Static("0 / 0", id="progress-label")
            yield Static("● IDLE", id="spider-hint")

        with TabbedContent(id="spider-tabs"):
            with TabPane("🗺 Site Map", id="tab-sitemap"):
                yield Static("Discovered pages:", classes="section-label")
                yield Tree("Site", id="site-tree")

            with TabPane("🔗 Endpoints", id="tab-endpoints"):
                yield Static("API endpoints & URL parameters:", classes="section-label")
                yield RichLog(id="endpoints-log", highlight=True, markup=True)

            with TabPane("📋 Forms", id="tab-forms"):
                yield Static("Discovered forms & parameters:", classes="section-label")
                yield RichLog(id="forms-log", highlight=True, markup=True)

            with TabPane("⚡ JS Files", id="tab-js"):
                yield Static("JavaScript files & API references:", classes="section-label")
                yield RichLog(id="js-log", highlight=True, markup=True)

        yield Static(
            "Start: Start Spider  │  Stop: Stop Spider  │  Scan Found: Send URLs to Scanner",
            id="status-bar",
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#btn-spider-stop", Button).disabled = True
        except Exception:
            pass


    @on(Button.Pressed, "#btn-spider-start")
    def _on_start(self) -> None:
        self.action_start_spider()

    @on(Button.Pressed, "#btn-spider-stop")
    def _on_stop(self) -> None:
        self.action_stop_spider()

    @on(Button.Pressed, "#btn-scan-found")
    def _on_scan_found(self) -> None:
        self._send_to_scanner()

    @on(Button.Pressed, "#btn-spider-clear")
    def _on_clear(self) -> None:
        self.action_clear_spider()


    def action_start_spider(self) -> None:
        url_input = self.query_one("#target-url", Input)
        url = url_input.value.strip()
        if not url:
            self.app.notify("Enter target URL", severity="warning")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            url_input.value = url

        try:
            max_depth = int(self.query_one("#cfg-depth", Input).value or "3")
        except ValueError:
            max_depth = 3
        try:
            max_pages = int(self.query_one("#cfg-pages", Input).value or "100")
        except ValueError:
            max_pages = 100
        try:
            concurrency = int(self.query_one("#cfg-concurrency", Input).value or "5")
        except ValueError:
            concurrency = 5
        scope = self.query_one("#cfg-scope", Checkbox).value

        self._max_pages = max_pages
        self._pages_count = 0
        self._crawl_running = True
        try:
            self.app.spider_crawl_started()  # type: ignore[attr-defined]
        except Exception:
            pass

        self.query_one("#btn-spider-start", Button).disabled = True
        self.query_one("#btn-spider-stop", Button).disabled = False
        self.query_one("#spider-hint", Static).update("[bold yellow]● RUNNING[/bold yellow]")
        self.query_one("#spider-progress", ProgressBar).update(total=max_pages, progress=0)
        self.query_one("#progress-label", Static).update("0 / 0")

        self._clear_results()

        self._run_spider_worker(url, max_depth, max_pages, concurrency, scope)

    def action_stop_spider(self) -> None:
        if self._spider is not None:
            self._spider.stop()
        self._set_idle_ui()

    def action_clear_spider(self) -> None:
        self._result = None
        self._pages_count = 0
        self._clear_results()
        self.query_one("#spider-hint", Static).update("● IDLE")
        self.query_one("#spider-progress", ProgressBar).update(total=100, progress=0)
        self.query_one("#progress-label", Static).update("0 / 0")

    def _clear_results(self) -> None:
        try:
            tree = self.query_one("#site-tree", Tree)
            tree.clear()
            tree.root.label = "Site"
        except Exception:
            pass
        for log_id in ("#endpoints-log", "#forms-log", "#js-log"):
            try:
                self.query_one(log_id, RichLog).clear()
            except Exception:
                pass


    @work
    async def _run_spider_worker(
        self, url: str, max_depth: int, max_pages: int, concurrency: int, scope: bool
    ) -> None:
        from pentool.api.spider_api import SpiderAPI, SpiderConfig

        def on_page(page_url: str) -> None:
            self._on_page_found(page_url)

        def on_progress(done: int, total: int) -> None:
            self._on_progress(done, total)

        cfg = SpiderConfig(
            max_depth=max_depth,
            max_pages=max_pages,
            concurrency=concurrency,
            respect_scope=scope,
        )
        self._spider = SpiderAPI(config=cfg)
        db_path = getattr(self.app, "db_path", "") or getattr(self.app, "_db_path", "")

        try:
            result = await self._spider.crawl(
                url, on_page=on_page, on_progress=on_progress, db_path=db_path,
            )
            self._result = result
            self._on_spider_done(result)
        except Exception as exc:
            logger.error("Spider error: %s", exc)
            self.app.notify(f"Spider error: {exc}", severity="error")
            self._set_idle_ui()


    def _on_page_found(self, url: str) -> None:
        self._pages_count += 1
        try:
            tree = self.query_one("#site-tree", Tree)
            root = tree.root
            root.label = f"Site ({self._pages_count} pages)"
            parsed = urlparse(url)
            path = parsed.path or "/"
            root.add_leaf(f"[dim]{parsed.netloc}[/dim]{path}", data=url)
        except Exception:
            pass

    def _on_progress(self, done: int, total: int) -> None:
        try:
            self.query_one("#spider-progress", ProgressBar).update(
                total=max(total, 1), progress=done
            )
            self.query_one("#progress-label", Static).update(f"{done} / {total}")
        except Exception:
            pass

    def _on_spider_done(self, result) -> None:
        """Crawler finished — display complete results."""
        self._set_idle_ui()
        self._populate_results(result)
        pages = len(result.pages)
        forms = len(result.forms)
        endpoints = len(result.endpoints)
        js_files = len(result.js_files)
        errors = len(result.errors)
        # Emit SpiderFinished → EventBus history → project save can collect sessions
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import SpiderFinished
            get_event_bus().emit(SpiderFinished(
                source="spider",
                base_url=getattr(result, "base_url", ""),
                pages_count=pages,
                forms_count=forms,
                endpoints_count=endpoints,
            ))
        except Exception:
            pass
        self.app.notify(
            f"Spider done: {pages} pages, {endpoints} endpoints, {forms} forms, {js_files} JS files"
            + (f", {errors} errors" if errors else ""),
            severity="information",
        )

    def _populate_results(self, result) -> None:
        """Populate all result tabs."""
        try:
            tree = self.query_one("#site-tree", Tree)
            tree.clear()
            root = tree.root
            root.label = f"[bold]{result.base_url}[/bold] ({len(result.pages)} pages)"

            pages_by_dir: dict[str, list[str]] = {}
            for page in result.pages:
                parsed = urlparse(page)
                parts = parsed.path.rsplit("/", 1)
                dirname = parts[0] or "/"
                pages_by_dir.setdefault(dirname, []).append(page)

            for dirname, pages in sorted(pages_by_dir.items()):
                if len(pages) == 1:
                    p = urlparse(pages[0])
                    root.add_leaf(f"[cyan]{p.path or '/'}[/cyan]", data=pages[0])
                else:
                    dir_node = root.add(f"[blue]{dirname}/[/blue] ({len(pages)})")
                    for page in pages:
                        p = urlparse(page)
                        dir_node.add_leaf(f"[cyan]{p.path or '/'}[/cyan]", data=page)

            root.expand()
        except Exception as exc:
            logger.debug("_populate_results tree: %s", exc)

        try:
            log = self.query_one("#endpoints-log", RichLog)
            log.clear()
            if result.endpoints:
                log.write(f"[bold]Found {len(result.endpoints)} endpoints:[/bold]")
                for ep in result.endpoints:
                    src_color = {"js": "yellow", "param": "green", "html": "blue"}.get(ep.source, "white")
                    params_str = f" [params: {', '.join(ep.params)}]" if ep.params else ""
                    log.write(
                        f"[{src_color}][{ep.source.upper()}][/{src_color}] "
                        f"[{ep.method}] {ep.url}{params_str}"
                    )
            else:
                log.write("[dim]No endpoints found[/dim]")
        except Exception:
            pass

        try:
            log = self.query_one("#forms-log", RichLog)
            log.clear()
            if result.forms:
                log.write(f"[bold]Found {len(result.forms)} forms:[/bold]")
                for form in result.forms:
                    method_color = "red" if form.method == "POST" else "green"
                    log.write(
                        f"[{method_color}][{form.method}][/{method_color}] "
                        f"[link]{form.action}[/link]"
                    )
                    for field in form.fields:
                        log.write(f"  [dim]  └─ {field.name} ({field.type})[/dim]")
            else:
                log.write("[dim]No forms found[/dim]")
        except Exception:
            pass

        try:
            log = self.query_one("#js-log", RichLog)
            log.clear()
            if result.js_files:
                log.write(f"[bold]Found {len(result.js_files)} JS files:[/bold]")
                for js in result.js_files:
                    log.write(f"[yellow]⚡[/yellow] {js}")
            else:
                log.write("[dim]No JS files found[/dim]")
        except Exception:
            pass

    def _set_idle_ui(self) -> None:
        """Reset UI to idle state.

        Guards the app-level counter decrement with the current
        _crawl_running value so repeated calls (Stop button, then the
        worker's own completion/error path also calling this) don't
        decrement spider_crawl_started()'s counter more than once per
        actual start.
        """
        if self._crawl_running:
            self._crawl_running = False
            try:
                self.app.spider_crawl_finished()  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            self.query_one("#btn-spider-start", Button).disabled = False
            self.query_one("#btn-spider-stop", Button).disabled = True
            self.query_one("#spider-hint", Static).update("● IDLE")
        except Exception:
            pass

    def _send_to_scanner(self) -> None:
        if self._result is None:
            self.app.notify("Run spider first to discover pages", severity="warning")
            return

        urls = list(self._result.pages)
        for ep in self._result.endpoints:
            if ep.url not in urls:
                urls.append(ep.url)

        if not urls:
            self.app.notify("No URLs to scan", severity="warning")
            return

        try:
            from pentool.tui.messages import SendToScanner
            self.app.post_message(SendToScanner("\n".join(urls[:50])))
        except Exception as exc:
            logger.error("_send_to_scanner: %s", exc)
            self.app.notify(f"Could not send to scanner: {exc}", severity="error")
