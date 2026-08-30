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
from pentool.modules.spider import is_playwright_available as _playwright_available
from pentool.utils.auth_headers import extract_auth_headers
from pentool.utils.lightpanda import is_lightpanda_available

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
    # Optional automatic session-login (Этап 2.3). When True and `login` is
    # set, ScanService tries to establish a cookie session against the first
    # target (CSRF-protected form, e.g. DVWA) before the active scan, and
    # reuses it via the shared _auth_headers. Off by default — the crawler
    # should never silently log into third-party sites without an explicit opt-in.
    auto_login: bool = False
    login: tuple[str, str] | None = None  # (username, password)
    # Hybrid JS crawl (Этап 2.4): when True and Playwright is installed, if the
    # static crawl only reaches the entry page, re-crawl with js_render to pull
    # client-side-built links (levels 3+). Off by default.
    hybrid_js: bool = False
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
        # Auth headers (Cookie/Authorization) shared across phases — the
        # crawler may establish/learn a session that the active scan must
        # reuse (DVWA would redirect to /login.php for unauthenticated probes).
        self._auth_headers: dict = {}

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

        # Session baseline: if seed requests carry auth headers (Cookie/
        # Authorization), seed them so the ACTIVE phase can reuse them even
        # before/without a crawl (e.g. resume). _crawl_target() may override
        # this with the headers the crawler actually established.
        from pentool.utils.auth_headers import extract_auth_headers as _extract_auth
        self._auth_headers = {}
        if config.seed_requests and config.seed_requests[0].headers:
            self._auth_headers = _extract_auth(dict(config.seed_requests[0].headers))

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
        if self._auth_headers:
            self._log(f"[dim]AUTH[/dim] Reusing {len(self._auth_headers)} auth header(s) in active scan")

        self._emit(ScanProgressEvent(done=0, total=len(all_scan_targets), scanning=True, source="scanner"))

        # Optional auto-login (Этап 2.3): if the caller opted in with creds and
        # the crawl never learned a session, try to establish one so the active
        # scan runs against a logged-in context (not redirected to /login.php).
        if config.auto_login and config.login and not self._auth_headers:
            await self._try_auto_login(config)

        all_findings = await self._run_active_scan(
            config, all_scan_targets, self._auth_headers, post_forms=all_forms,
        )

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

    # Cap how many distinct parameter-value variants we keep for one path
    # template. `/vulnerabilities/sqli/?id=1` and `?id=2` collapse to the SAME
    # template, but the different values may reflect differently in the
    # active scan — keeping a small bundle (not just one representative)
    # preserves that without an unbounded request explosion.
    _MAX_VARIANTS_PER_TEMPLATE = 5

    def _filter_targets(self, all_scan_targets: list[str]) -> list[str]:
        """Phase 2: remove static assets and deduplicate by URL template,
        keeping up to _MAX_VARIANTS_PER_TEMPLATE distinct URLs per template."""
        from pentool.modules.scanner.helpers import is_scannable_url, path_template
        seen_templates: dict[str, int] = {}
        seen_exact: set[str] = set()
        unique: list[str] = []
        skipped_static = 0
        skipped_dedup = 0

        for t in all_scan_targets:
            if not is_scannable_url(t):
                skipped_static += 1
                continue
            # Exact duplicates are always collapsed regardless of template.
            if t in seen_exact:
                skipped_dedup += 1
                continue
            tmpl = path_template(t)
            count = seen_templates.get(tmpl, 0)
            if count >= self._MAX_VARIANTS_PER_TEMPLATE:
                skipped_dedup += 1
                continue
            seen_exact.add(t)
            seen_templates[tmpl] = count + 1
            unique.append(t)

        if skipped_static or skipped_dedup:
            self._log(
                f"[dim]FILTER[/dim] Skipped [bold]{skipped_static}[/bold] static, "
                f"[bold]{skipped_dedup}[/bold] duplicate templates (cap "
                f"{self._MAX_VARIANTS_PER_TEMPLATE} variants/template)"
            )
        return unique

    async def _try_auto_login(self, config: ScanConfig) -> None:
        """Best-effort session login against the first target (Этап 2.3).

        Uses pentool.utils.auth_login.build_session_headers() to submit a
        CSRF-protected login form, then stores the resulting Cookie in
        self._auth_headers so the active phase reuses it. Off by default and
        only runs when the crawl didn't already learn a session.
        """
        if not config.targets or not config.login:
            return
        try:
            from pentool.utils.auth_login import build_session_headers

            username, password = config.login
            base = config.targets[0]
            headers = await build_session_headers(
                url=base, username=username, password=password, use_cache=True,
            )
            if headers:
                self._auth_headers = headers
                self._log(
                    f"[dim]AUTH[/dim] auto-login established session for {base} "
                    f"({len(headers)} header(s))"
                )
        except Exception as exc:
            self._log(f"[yellow]AUTH[/yellow] auto-login failed: {exc}")

    # Action-URL substrings that signal a state-mutating/security-relevant
    # endpoint. Auto-submitting these as POST could log the user out, delete
    # data, or hit admin panels — so ScanService skips them (Этап 2.6 safety).
    _RISKY_FORM_MARKERS = (
        "/logout", "/signout", "/delete", "/remove", "/drop", "/purge",
        "/reset", "/admin", "/truncate",
    )

    @staticmethod
    def _is_risky_form_action(action_url: str) -> bool:
        path = urlparse(action_url).path.lower()
        return any(marker in path for marker in ScanService._RISKY_FORM_MARKERS)

    async def _run_active_scan(
        self, config: ScanConfig, all_scan_targets: list[str], auth_headers: dict | None = None,
        post_forms: list | None = None,
    ) -> list[Finding]:
        """Phase 3: run active checks on collected targets, return findings."""
        from pentool.utils.parser import ParsedRequest

        # Reuse any auth/session headers the crawl established, so active
        # probes (and the TechFingerprinter baseline) target the SAME
        # authenticated context instead of being redirected to a login page.
        auth_headers = auth_headers or {}

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
            # Intentionally a no-op for the scan log: printing a line for every
            # HTTP request flooded the log with hundreds/thousands of lines
            # ("→ check [param] url"). The live request counter on the status
            # bar is driven separately via on_request_sent. The scan log only
            # shows stage summaries (crawl/scan/findings/stage-done).
            pass

        _on_request_sent = getattr(config, "on_request_sent", None)
        _on_total_estimate = getattr(config, "on_total_estimate", None)

        from pentool.core.config import get_config
        from pentool.utils.http_client import get_shared_http_client
        http_client = get_shared_http_client(
            follow_redirects=True, extra_headers=auth_headers, cfg=get_config()
        )
        self._scanner.configure_engine(
            http_client=http_client,
            concurrency=config.threads,
            request_delay=config.delay_sec,
        )

        try:
            if config.seed_requests:
                crawled_reqs = [
                    ParsedRequest(method="GET", url=url, headers=auth_headers, body="")
                    for url in all_scan_targets
                    if not any(sr.url == url for sr in config.seed_requests)
                ]
                all_reqs = list(config.seed_requests) + crawled_reqs
            else:
                all_reqs = [
                    ParsedRequest(method="GET", url=url, headers=auth_headers, body="")
                    for url in all_scan_targets
                ]

            # Auto-submit POST forms (Этап 2.6) with default field values so
            # POST-only endpoints (e.g. sqli_blind/exec/upload) are reached.
            # Skip dangerous actions (/logout, /delete, /admin, ...) to avoid
            # real side-effects.
            _form_reqs: list = []
            for form in post_forms or []:
                try:
                    action = getattr(form, "action", "")
                    fields = getattr(form, "fields", []) or []
                    if not action.startswith("http") or not fields:
                        continue
                    if self._is_risky_form_action(action):
                        self._log(f"[dim]FORM[/dim] skip POST {action} (destructive action)")
                        continue
                    body = urlencode([(f.name, f.value or "test") for f in fields])
                    _form_reqs.append(ParsedRequest(
                        method="POST", url=action, headers=auth_headers, body=body,
                    ))
                except Exception:
                    continue
            if _form_reqs:
                all_reqs = all_reqs + _form_reqs

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
            # Carry the headers the crawler actually used (Proxy-discovered
            # session + seed) into the active phase via _auth_headers.
            if getattr(result, "auth_headers", None):
                self._auth_headers = dict(result.auth_headers)

            # Hybrid JS crawl (Этап 2.4): when the caller opted in (hybrid_js)
            # and a JS engine (Lightpanda preferred, Playwright fallback) is
            # available, if the static crawl surfaced almost nothing (only
            # reached the entry page — typical for a JS/SPA app whose
            # level-2/3 links are built client-side), re-crawl with js_render
            # to catch them. Graceful: no-ops if no engine is installed.
            # Off by default so scans stay deterministic/fast unless the user
            # explicitly wants JS recovery.
            if (
                getattr(config, "hybrid_js", False)
                and (is_lightpanda_available() or _playwright_available())
                and not self._stop_requested
                and len(getattr(result, "pages", [])) < 2
            ):
                try:
                    from pentool.api.spider_api import SpiderAPI, SpiderConfig

                    js_spider = SpiderAPI(config=SpiderConfig(js_render=True))
                    js_result = await js_spider.crawl(
                        base_url, extra_headers=auth_headers, db_path=config.db_path,
                    )
                    if js_result and js_result.pages:
                        self._log(
                            f"[dim]JS[/dim] hybrid crawl recovered "
                            f"{len(js_result.pages)} extra page(s) from {base_url}"
                        )
                        result.pages = list(dict.fromkeys(
                            list(result.pages) + list(js_result.pages)
                        ))
                        result.endpoints = list(result.endpoints) + [
                            e for e in js_result.endpoints
                            if not any(x.url == e.url for x in result.endpoints)
                        ]
                        # JS crawl may have learned a session too.
                        if getattr(js_result, "auth_headers", None):
                            self._auth_headers = dict(js_result.auth_headers)
                except Exception as exc:
                    self._log(f"[dim]JS crawl warn:[/dim] {exc}")

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
