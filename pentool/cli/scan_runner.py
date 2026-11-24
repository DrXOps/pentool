"""ScanRunner — a single engine for CLI and headless scanning.

Eliminates duplication between ``cli/scan.py`` (scan active) and ``cli/headless.py``
(run_headless_scan). Both entry points use the same class.

Uses ``ScanService`` (instead of calling ScannerAPI directly), which provides:
- Fingerprint → tech_profile → AIWorker via _on_fingerprint
- Correct payload/WAF queues
- Crawling via SpiderAPI
- A single lifecycle (stop, error handling)
"""

from __future__ import annotations

import asyncio
from typing import Callable

import click

_SCANNER_UNAVAILABLE_MSG = (
    "Scanner is a PRO feature and isn't installed.\n"
    "Have a key? Open Pentool → Settings → License, paste it and press Activate.\n"
    "No key yet? Start the 14-day trial on the same screen (it activates PRO)."
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
        """Execute the scan and return exit code (0 = success).

        Uses ``ScanService`` for the full lifecycle:
        crawl → fingerprint → AIWorker → active scan → save.
        """
        scanner_api = _import_scanner_api()
        from pentool.api.spider_api import SpiderAPI
        from pentool.core.config import get_config
        from pentool.core.event_bus import EventBus
        from pentool.services.scan_service import ScanConfig, ScanService
        from pentool.utils.lightpanda import is_lightpanda_available

        cfg = get_config()
        api = scanner_api(db_path=cfg.db_path)

        # Callback for CLI logging
        _findings: list = []

        def on_finding(f) -> None:
            _findings.append(f)
            if self._on_finding:
                self._on_finding(f)
            else:
                sev = f.severity.upper()
                click.echo(f"  [{sev}] {f.name} — {f.url}")

        def on_log(msg: str) -> None:
            # Rich tags are not needed in the CLI, but they can be shown
            click.echo(f"  {msg}")

        async def _run() -> int:
            nonlocal _findings

            # 1. Spider (crawl) — if requested
            spider_api: SpiderAPI | None = None
            if self.crawl:
                use_js = is_lightpanda_available()
                spider_api = SpiderAPI.from_params(
                    max_depth=self.crawl_depth,
                    max_pages=self.max_pages,
                    js_render=use_js,
                )
                click.echo(
                    f"[scan] Crawling {len(self.urls)} target(s) "
                    f"js_render={use_js} depth={self.crawl_depth} "
                    f"max_pages={self.max_pages}..."
                )
            else:
                click.echo("[scan] Skipping crawl — using provided URLs directly")

            # 2. EventBus (for ScanService internal events)
            from pentool.core.events import FindingDiscovered, ScanProgressEvent

            bus = EventBus()
            # Subscribe to events for CLI output
            findings_from_events: list = []

            def on_finding_event(event: FindingDiscovered) -> None:
                f = getattr(event, "finding", None)
                if f:
                    findings_from_events.append(f)
                    on_finding(f)

            bus.subscribe(FindingDiscovered, on_finding_event)

            def on_progress_event(event: ScanProgressEvent) -> None:
                done = getattr(event, "done", 0)
                total = getattr(event, "total", 0)
                if total > 0:
                    click.echo(f"\r  Progress: {done}/{total}", nl=False)

            bus.subscribe(ScanProgressEvent, on_progress_event)

            # 3. ScanService — the single orchestrator
            service = ScanService(
                scanner_api=api,
                spider_api=spider_api,
                event_bus=bus,
                tui_loop=None,
                on_log=on_log,
            )

            config = ScanConfig(
                targets=self.urls,
                check_names=self.check_names,
                threads=self.concurrency,
                delay_sec=self.delay,
                max_depth=self.crawl_depth,
                max_pages=self.max_pages,
                db_path=cfg.db_path,
                resume=not self.crawl,  # if crawl is off — use the URLs as is
                use_ai=self.use_ai,
            )

            click.echo(
                f"[scan] Active scan on {len(self.urls)} target(s) "
                f"checks={self.check_names or 'all'} "
                f"threads={self.concurrency} delay={self.delay}s "
                f"use_ai={self.use_ai}..."
            )

            try:
                findings = await service.run(config)
            except Exception as exc:
                click.echo(f"\n[scan] Scan failed: {exc}", err=True)
                return 1

            # findings already holds all results (ScanService adds them itself)
            _findings = findings

            click.echo(f"\nDone. Found {len(findings)} finding(s).")

            # Save the findings (ScanService already saved them, but a duplicate is safe)
            if findings:
                await api.save_findings(findings)

            # Generate the report
            if self.output:
                fmt = self._resolve_format()
                await api.generate_report(self.output, fmt)
                click.echo(f"[scan] Report saved: {self.output}")

            return 0

        try:
            click.echo(f"[scan] Starting scan on {len(self.urls)} target(s)...")
            exit_code = asyncio.run(_run())
            return exit_code
        except Exception as exc:
            click.echo(f"[scan] Scan failed: {exc}", err=True)
            return 1

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
