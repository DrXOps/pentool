"""Headless mode: run a scan without the TUI — for CI/CD automation.

Used by ``pentool --url <url> --headless [options]``.

Reuses the same ScanRunner as ``pentool scan active``, but accepts the URL(s)
from the top-level CLI flags so automation is a single, simple command.
"""

from __future__ import annotations

from pentool.cli.scan_runner import ScanRunner


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

    Delegates to ``ScanRunner`` — the same engine used by ``pentool scan active``.

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
    runner = ScanRunner(
        urls,
        check_names=check_names,
        output=output,
        report_format=report_format,
        concurrency=concurrency,
        delay=delay,
        use_ai=use_ai,
        crawl=crawl,
        crawl_depth=crawl_depth,
        max_pages=max_pages,
    )
    return runner.run()