"""ScanRunner — единый движок для CLI и headless-сканирования.

Устраняет дублирование между ``cli/scan.py`` (scan active) и ``cli/headless.py``
(run_headless_scan). Обе точки входа используют один и тот же класс.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Callable

import click


_SCANNER_UNAVAILABLE_MSG = (
    "Scanner is a PRO feature and isn't installed.\n"
    "Start a 14-day free trial (full PRO access):\n"
    "  pentool license trial\n"
    "Already have a key?\n"
    "  pentool license activate KEY"
)


def _import_scanner_api():
    """Lazy-import ScannerAPI with user-friendly error on missing PRO."""
    try:
        from pentool.api.scanner_api import ScannerAPI
        return ScannerAPI
    except ImportError:
        click.echo(_SCANNER_UNAVAILABLE_MSG, err=True)
        raise SystemExit(1)


class ScanRunner:
    """Orchestrates an active scan from CLI or headless entry points.

    Usage::

        runner = ScanRunner(urls, concurrency=5, delay=0.0, ...)
        exit_code = runner.run()

    The same ``ScanRunner`` is used by both ``pentool scan active`` and
    ``pentool --url ... --headless``.
    """

    def __init__(
        self,
        urls: list[str],
        *,
        check_names: list[str] | None = None,
        output: str | None = None,
        report_format: str = "auto",
        concurrency: int = 5,
        delay: float = 0.0,
        use_ai: bool = False,
        crawl: bool = False,
        crawl_depth: int = 3,
        max_pages: int = 100,
        on_finding: Callable | None = None,
    ) -> None:
        self.urls = urls
        self.check_names = check_names
        self.output = output
        self.report_format = report_format
        self.concurrency = concurrency
        self.delay = delay
        self.use_ai = use_ai
        self.crawl = crawl
        self.crawl_depth = crawl_depth
        self.max_pages = max_pages
        self._on_finding = on_finding

    def run(self) -> int:
        """Execute the scan and return exit code (0 = success)."""
        ScannerAPI = _import_scanner_api()
        from pentool.core.config import get_config
        from pentool.utils.http_client import get_shared_http_client
        from pentool.utils.parser import ParsedRequest
        from pentool.utils.lightpanda import is_lightpanda_available

        cfg = get_config()
        api = ScannerAPI(db_path=cfg.db_path)

        findings: list = []

        def on_finding(f) -> None:
            findings.append(f)
            if self._on_finding:
                self._on_finding(f)
            else:
                sev = f.severity.upper()
                click.echo(f"  [{sev}] {f.name} — {f.url}")

        def on_progress(done: int, total: int) -> None:
            click.echo(f"\r  Progress: {done}/{total}", nl=False)

        def on_request_sent(req_sent: int, threads_active: int,
                            check_name: str, param_name: str, url: str) -> None:
            pass  # keep the engine's progress-reporting proxy working

        async def _run() -> None:
            nonlocal findings
            all_targets: list[str] = list(self.urls)

            # 1. Crawl (optional)
            if self.crawl:
                use_js = is_lightpanda_available()
                from pentool.api.spider_api import SpiderAPI
                spider = SpiderAPI.from_params(
                    max_depth=self.crawl_depth, max_pages=self.max_pages,
                    js_render=use_js,
                )
                click.echo(
                    f"[scan] Crawling {len(self.urls)} target(s) "
                    f"js_render={use_js} depth={self.crawl_depth} "
                    f"max_pages={self.max_pages}..."
                )
                for url in self.urls:
                    try:
                        result = await spider.crawl(url, db_path=cfg.db_path)
                        if hasattr(result, "pages") and result.pages:
                            for page in result.pages:
                                if page not in all_targets:
                                    all_targets.append(page)
                            click.echo(f"  → {url}: {len(result.pages)} pages")
                        else:
                            all_targets.append(url)
                    except Exception as exc:
                        click.echo(f"  ⚠ crawl failed for {url}: {exc}", err=True)
                        all_targets.append(url)
                click.echo(f"  Total unique targets: {len(all_targets)}")

            # 2. Configure engine
            http_client = get_shared_http_client(follow_redirects=True, cfg=cfg)
            api.configure_engine(
                http_client=http_client,
                concurrency=self.concurrency,
                request_delay=self.delay,
            )

            # 3. Build ParsedRequest list
            reqs = [
                ParsedRequest(method="GET", url=u, headers={}, body="")
                for u in all_targets
            ]

            click.echo(
                f"[scan] Active scan on {len(reqs)} request(s) "
                f"checks={self.check_names or 'all'} "
                f"threads={self.concurrency} delay={self.delay}s "
                f"use_ai={self.use_ai}..."
            )

            # 4. Run active scan — with optional AIWorker
            if self.use_ai:
                from pentool.modules.scanner.ai_worker import AIWorker
                from pentool.services.ai.factory import ensure_backend
                backend = await ensure_backend(_force=True)
                if backend is not None:
                    click.echo("[scan] Starting AIWorker (endpoint discovery, WAF bypass)...")
                    ai_payload_queue: asyncio.Queue = asyncio.Queue()
                    waf_bypass_queue: asyncio.Queue = asyncio.Queue()
                    worker = AIWorker(
                        target_urls=all_targets,
                        tech_profile=None,
                        payload_queue=ai_payload_queue,
                    )
                    worker._waf_bypass_queue = waf_bypass_queue
                    ai_task = asyncio.create_task(worker.run())
                else:
                    click.echo("[scan] AI backend unavailable — skipping AIWorker", err=True)
                    ai_task = None
                    ai_payload_queue = None
                    waf_bypass_queue = None
            else:
                ai_task = None
                ai_payload_queue = None
                waf_bypass_queue = None

            active_findings = await api.run_active_on_requests(
                seed_requests=reqs,
                check_names=self.check_names,
                on_finding=on_finding,
                on_progress=on_progress,
                on_request_sent=on_request_sent,
                use_ai=self.use_ai,
            )
            for f in active_findings:
                if not any(getattr(x, "id", None) == f.id for x in findings):
                    findings.append(f)

            # Save findings to DB so generate_report can read them
            if findings:
                await api.save_findings(findings)

            try:
                await http_client.close()
            except Exception:
                pass  # best-effort

        try:
            click.echo(f"[scan] Starting scan on {len(self.urls)} target(s)...")
            asyncio.run(_run())
            click.echo(f"\nDone. Found {len(findings)} finding(s).")
        except Exception as exc:
            click.echo(f"[scan] Scan failed: {exc}", err=True)
            return 1

        if self.output:
            fmt = self._resolve_format()
            asyncio.run(api.generate_report(self.output, fmt))
            click.echo(f"[scan] Report saved: {self.output}")

        return 0

    def _resolve_format(self) -> str:
        """Determine output format from --format flag or file extension."""
        if self.report_format != "auto":
            return self.report_format
        out = (self.output or "").lower()
        if out.endswith(".json"):
            return "json"
        if out.endswith(".csv"):
            return "csv"
        if out.endswith(".html"):
            return "html"
        return "json"