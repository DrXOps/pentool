"""Headless mode: run a scan without the TUI — for CI/CD automation.

Used by ``pentool --url <url> --headless [options]``.

Reuses the same ScannerAPI active-scan pipeline as ``pentool scan active``, but
accepts the URL(s) from the top-level CLI flags so automation is a single,
simple command. Emits machine-readable reports (JSON/HTML/CSV) for later audit.

Supports the full CI/CD feature set:

  --use-ai         Enable AI-assisted scanning (endpoint discovery, WAF bypass)
  --check CHECKS   Comma-separated checks (default: all)
  --threads N      Parallel threads (default: 10)
  --delay SEC      Delay between requests (default: 0.0)
  --format FORMAT  Output format: json, html, csv (default: auto from --output ext)
  --output PATH    Save report to file
  --crawl          Crawl the target first (JS via Lightpanda), then scan
  --depth N        Crawl depth (default: 3, requires --crawl)
  --max-pages N    Max pages to crawl (default: 100, requires --crawl)
"""

from __future__ import annotations

import asyncio

import click


def _import_scanner_api():
    try:
        from pentool.api.scanner_api import ScannerAPI
        return ScannerAPI
    except ImportError:
        click.echo(
            "Scanner is a PRO feature and isn't installed.\n"
            "Start a 14-day free trial (full PRO access):  pentool license trial\n"
            "Already have a key?  pentool license activate KEY",
            err=True,
        )
        raise SystemExit(1)


def run_headless_scan(
    urls: list[str],
    output: str | None = None,
    check_names: list[str] | None = None,
    concurrency: int = 10,
    delay: float = 0.0,
    use_ai: bool = False,
    crawl: bool = False,
    crawl_depth: int = 3,
    max_pages: int = 100,
    report_format: str = "auto",
) -> int:
    """Run an active scan against ``urls`` and exit with a process status.

    When ``crawl=True``, uses SpiderAPI to crawl the target first, then scans
    all discovered pages — matching what the TUI ScanService does.

    Args:
        urls: target URL(s).
        output: optional report path (.json / .html / .csv). None = print only.
        check_names: optional list of checks; None = defaults.
        concurrency: number of parallel scan threads (default 10).
        delay: delay between requests in seconds (default 0.0).
        use_ai: enable AI-assisted scanning (endpoint discovery, WAF bypass).
        crawl: crawl the target first before scanning.
        crawl_depth: max crawl depth (default 3).
        max_pages: max pages to crawl (default 100).
        report_format: force output format ("json", "html", "csv", "auto").

    Returns:
        Exit code (0 on success, 1 on error).
    """
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
        sev = f.severity.upper()
        click.echo(f"  [{sev}] {f.name} — {f.url}")

    def on_progress(done: int, total: int) -> None:
        click.echo(f"\r  Progress: {done}/{total}", nl=False)

    def on_request_sent(req_sent: int, threads_active: int,
                        check_name: str, param_name: str, url: str) -> None:
        pass  # keep the engine's progress-reporting proxy working

    async def _run() -> None:
        nonlocal findings
        all_targets: list[str] = list(urls)

        # 1. Crawl (optional)
        if crawl:
            use_js = is_lightpanda_available()
            from pentool.api.spider_api import SpiderAPI
            spider = SpiderAPI.from_params(
                max_depth=crawl_depth, max_pages=max_pages,
                js_render=use_js,
            )
            click.echo(
                f"[headless] Crawling {len(urls)} target(s) "
                f"js_render={use_js} depth={crawl_depth} max_pages={max_pages}..."
            )
            for url in urls:
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
            concurrency=concurrency,
            request_delay=delay,
        )

        # 3. Build ParsedRequest list
        reqs = [
            ParsedRequest(method="GET", url=u, headers={}, body="")
            for u in all_targets
        ]

        click.echo(
            f"[headless] Active scan on {len(reqs)} request(s) "
            f"checks={check_names or 'all'} "
            f"threads={concurrency} delay={delay}s use_ai={use_ai}..."
        )

        # 4. Run active scan (use_ai passed through)
        active_findings = await api.run_active_on_requests(
            seed_requests=reqs,
            check_names=check_names,
            on_finding=on_finding,
            on_progress=on_progress,
            on_request_sent=on_request_sent,
            use_ai=use_ai,
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
            pass

    try:
        click.echo(f"[headless] Starting scan on {len(urls)} target(s)...")
        asyncio.run(_run())
        click.echo(f"\nDone. Found {len(findings)} finding(s).")
    except Exception as exc:
        click.echo(f"[headless] Scan failed: {exc}", err=True)
        return 1

    if output:
        if report_format != "auto":
            fmt = report_format
        elif output.endswith(".json"):
            fmt = "json"
        elif output.endswith(".csv"):
            fmt = "csv"
        elif output.endswith(".html"):
            fmt = "html"
        else:
            fmt = "json"
        asyncio.run(api.generate_report(output, fmt))
        click.echo(f"[headless] Report saved: {output}")

    return 0