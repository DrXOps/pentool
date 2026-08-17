"""ScanService — orchestrates Spider → ScanEngine → EventBus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlencode, urlparse, urlunparse

from pentool.api.scanner_api import Finding, ScannerAPI
from pentool.api.spider_api import SpiderAPI
from pentool.core.event_bus import EventBus
from pentool.core.events import (
    FindingDiscovered,
    ScanFinished,
    ScanProgressEvent,
    ScanStarted,
    SpiderFinished,
    UrlCrawled,
)
from pentool.core.logging import get_logger
from pentool.modules.spider import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from pentool.services.base_service import BaseService
from pentool.utils.auth_headers import extract_auth_headers

logger = get_logger(__name__)


@dataclass
class ScanConfig:
    """Configuration for a single scan run."""
    targets: list[str]
    seed_requests: list = field(default_factory=list)  # list[ParsedRequest]
    check_names: list[str] | None = None
    threads: int = 10
    delay_sec: float = 0.0
    max_depth: int = DEFAULT_MAX_DEPTH
    max_pages: int = DEFAULT_MAX_PAGES
    db_path: str = ""
    resume: bool = False  # True — skip crawling, use seed_requests directly
    resume_targets: list[str] = field(default_factory=list)  # URLs to scan on resume
    # on_request_sent(requests_sent, threads_active, check_name, param_name, url)
    on_request_sent: Callable | None = None
    # Stable identity of the Scanner tab / scan run this scan belongs to —
    # persisted on each Finding so a tab only ever shows findings from its
    # own scans (see ScanEngine.get_findings(tab_uid=...)), instead of every
    # tab showing every finding ever saved to the project DB.
    scan_tab_uid: str = ""
    scan_session_id: str = ""
    # Called once, before active-scan work starts, with a rough estimate of
    # the total number of HTTP requests the scan will make — drives a
    # progress bar off request volume instead of (req, point, check) task
    # count, since one pipeline-check task (e.g. XSS) can be hundreds of
    # real requests.
    on_total_estimate: Callable[[int], None] | None = None


class ScanService(BaseService):
    """Orchestrates: Spider → URL collection → ScanEngine → EventBus.

    Has no knowledge of Textual. Launched via async @work in ScannerScreen.

    Usage:
        service = ScanService(scanner_api, spider_api, event_bus)
        findings = await service.run(config)
    """

    def __init__(
        self,
        scanner_api: ScannerAPI,
        spider_api: SpiderAPI,
        event_bus: EventBus | None = None,
        tui_loop: asyncio.AbstractEventLoop | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(event_bus=event_bus, tui_loop=tui_loop, on_log=on_log)
        self._scanner = scanner_api
        self._spider = spider_api
        self._stop_requested = False

    # ── public API ─────────────────────────────────────────────────────────────

    def request_stop(self) -> None:
        """Request stop (thread-safe)."""
        self._stop_requested = True
        self._spider.stop()
        try:
            self._scanner.request_active_stop()
        except Exception:
            pass

    async def run(self, config: ScanConfig) -> list[Finding]:
        self._stop_requested = False
        self._emit(ScanStarted(
            targets=config.targets,
            checks=config.check_names or [],
            source="scanner",
        ))

        all_scan_targets, all_forms = await self._collect_targets(config)
        if self._stop_requested:
            self._log("[yellow]STOP[/yellow] Scan stopped after crawl.")
            self._emit(ScanFinished(total_findings=0, stopped_early=True, source="scanner"))
            return []

        all_scan_targets = self._filter_targets(all_scan_targets)
        self._log(
            f"[cyan]CRAWL[/cyan] Total: [bold]{len(all_scan_targets)}[/bold] URLs + "
            f"[bold]{len(all_forms)}[/bold] POST forms to test"
        )

        self._emit(ScanProgressEvent(done=0, total=len(all_scan_targets), scanning=True, source="scanner"))

        all_findings = await self._run_active_scan(config, all_scan_targets)

        self._emit(ScanFinished(
            total_findings=len(all_findings),
            stopped_early=self._stop_requested,
            source="scanner",
        ))
        return all_findings

    async def _collect_targets(
        self, config: ScanConfig
    ) -> tuple[list[str], list]:
        """Phase 1: collect scan targets via crawl or resume."""
        all_scan_targets: list[str] = []
        all_forms: list = []

        if config.resume and config.resume_targets:
            all_scan_targets = list(config.resume_targets)
            self._log(
                f"[yellow]RESUME[/yellow] Skipping crawl — "
                f"using {len(all_scan_targets)} previously discovered URLs"
            )
        else:
            for base_url in config.targets:
                if self._stop_requested:
                    break
                await self._crawl_target(base_url, config, all_scan_targets, all_forms)

        return all_scan_targets, all_forms

    def _filter_targets(self, all_scan_targets: list[str]) -> list[str]:
        """Phase 2: remove static assets and deduplicate by URL template."""
        from pentool.modules.scanner.helpers import is_scannable_url, path_template
        seen_templates: set[str] = set()
        unique: list[str] = []
        skipped_static = 0
        skipped_dedup = 0

        for t in all_scan_targets:
            if not is_scannable_url(t):
                skipped_static += 1
                continue
            tmpl = path_template(t)
            if tmpl in seen_templates:
                skipped_dedup += 1
                continue
            seen_templates.add(tmpl)
            unique.append(t)

        if skipped_static or skipped_dedup:
            self._log(
                f"[dim]FILTER[/dim] Skipped [bold]{skipped_static}[/bold] static, "
                f"[bold]{skipped_dedup}[/bold] duplicate templates"
            )
        return unique

    async def _run_active_scan(
        self, config: ScanConfig, all_scan_targets: list[str]
    ) -> list[Finding]:
        """Phase 3: run active checks on collected targets, return findings."""
        from pentool.utils.http_client import HTTPClient
        from pentool.utils.parser import ParsedRequest

        findings: list[Finding] = []

        def on_finding(f: Finding) -> None:
            if not self._stop_requested:
                f.scan_tab_uid = config.scan_tab_uid
                f.scan_session_id = config.scan_session_id
                findings.append(f)
                self._emit(FindingDiscovered(finding=f, scan_source="active", source="scanner"))

        def on_progress(done: int, total: int) -> None:
            self._emit(ScanProgressEvent(done=done, total=total, scanning=True, source="scanner"))

        def on_request(url: str, check_name: str, point_name: str = "") -> None:
            pt = f" [{point_name}]" if point_name and point_name != "—" else ""
            self._log(f"[dim]→ {check_name}{pt}[/dim]  {url[:80]}")

        _on_request_sent = getattr(config, "on_request_sent", None)
        _on_total_estimate = getattr(config, "on_total_estimate", None)

        from pentool.core.config import get_config
        cfg = get_config()
        http_client = HTTPClient(
            timeout=cfg.request_timeout,
            follow_redirects=True,
            verify_ssl=cfg.verify_ssl,
        )
        self._scanner.configure_engine(
            http_client=http_client,
            concurrency=config.threads,
            request_delay=config.delay_sec,
        )

        try:
            if config.seed_requests:
                base_headers = dict(config.seed_requests[0].headers or {})
                crawled_reqs = [
                    ParsedRequest(method="GET", url=url, headers=base_headers, body="")
                    for url in all_scan_targets
                    if not any(sr.url == url for sr in config.seed_requests)
                ]
                all_reqs = list(config.seed_requests) + crawled_reqs
            else:
                all_reqs = [
                    ParsedRequest(method="GET", url=url, headers={}, body="")
                    for url in all_scan_targets
                ]

            self._log(
                f"[bold green]SCAN[/bold green] Running active checks on "
                f"[bold]{len(all_reqs)}[/bold] requests…"
            )

            active_findings = await self._scanner.run_active_on_requests(
                seed_requests=all_reqs,
                check_names=config.check_names,
                on_finding=on_finding,
                on_progress=on_progress,
                on_request=on_request,
                on_request_sent=_on_request_sent,
                resume=config.resume,
                on_total_estimate=_on_total_estimate,
            )
            for f in active_findings:
                f.scan_tab_uid = config.scan_tab_uid
                f.scan_session_id = config.scan_session_id
            all_findings = list({id(f): f for f in findings + active_findings}.values())
        finally:
            await http_client.close()

        if not self._stop_requested:
            await self._scanner.save_findings(all_findings)

        return all_findings

    # ── private methods ────────────────────────────────────────────────────────

    async def _crawl_target(
        self,
        base_url: str,
        config: ScanConfig,
        all_scan_targets: list[str],
        all_forms: list,
    ) -> None:
        """Crawl a single target, populate all_scan_targets and all_forms."""
        try:
            parsed = urlparse(base_url)
            # Strip standard ports from netloc
            if parsed.port == 443 and parsed.scheme == "https":
                base_url = urlunparse(parsed._replace(netloc=parsed.hostname))
            elif parsed.port == 80 and parsed.scheme == "http":
                base_url = urlunparse(parsed._replace(netloc=parsed.hostname))

            # Pass auth headers (Cookie, Authorization) from seed_requests —
            # explicit ones win; SpiderAPI.crawl() also auto-discovers a
            # session from Proxy History via db_path as a fallback when no
            # seed_requests were supplied (see utils/auth_headers.py).
            auth_headers: dict = {}
            if config.seed_requests:
                raw_hdrs = dict(config.seed_requests[0].headers or {})
                auth_headers = extract_auth_headers(raw_hdrs)
            result = await self._spider.crawl(
                base_url, extra_headers=auth_headers, db_path=config.db_path,
            )
            base_host = urlparse(base_url).netloc

            self._log(
                f"[cyan]CRAWL[/cyan] {base_url} → "
                f"{len(result.pages)} pages, "
                f"{len(result.forms)} forms, "
                f"{len(result.endpoints)} endpoints, "
                f"{len(result.js_files)} JS files"
            )

            # Emit SpiderFinished for subscribers
            self._emit(SpiderFinished(
                base_url=base_url,
                pages_count=len(result.pages),
                forms_count=len(result.forms),
                endpoints_count=len(result.endpoints),
                source="spider",
            ))

            # Always include base URL
            all_scan_targets.append(base_url)

            # Pages
            for page in result.pages:
                phost = urlparse(page).netloc
                if (phost == base_host or not phost) and page not in all_scan_targets:
                    all_scan_targets.append(page)
                    self._emit(UrlCrawled(url=page, base_target=base_url, source="spider"))

            # Forms
            for form in result.forms:
                form_url = form.action
                if not form_url.startswith("http"):
                    continue
                fhost = urlparse(form_url).netloc
                if fhost != base_host and fhost:
                    continue
                if form.method.upper() == "GET" and form.fields:
                    params = {f.name: f.value or "test" for f in form.fields}
                    query = urlencode(params)
                    p = urlparse(form_url)
                    form_target = urlunparse(p._replace(query=query))
                    if form_target not in all_scan_targets:
                        all_scan_targets.append(form_target)
                        self._emit(UrlCrawled(url=form_target, base_target=base_url, source="spider"))
                elif form.method.upper() == "POST":
                    all_forms.append(form)
                    if form_url not in all_scan_targets:
                        all_scan_targets.append(form_url)
                        self._emit(UrlCrawled(url=form_url, base_target=base_url, source="spider"))

            # Endpoints
            for ep in result.endpoints:
                ep_host = urlparse(ep.url).netloc
                if (
                    ep.url.startswith("http")
                    and (ep_host == base_host or not ep_host)
                    and ep.url not in all_scan_targets
                ):
                    all_scan_targets.append(ep.url)
                    self._emit(UrlCrawled(url=ep.url, base_target=base_url, source="spider"))

        except Exception as exc:
            logger.warning("ScanService._crawl_target error for %s: %s", base_url, exc)
            self._log(f"[yellow]CRAWL warn:[/yellow] {exc}")
            if base_url not in all_scan_targets:
                all_scan_targets.append(base_url)
