"""Headless mode: run a scan without the TUI — for CI/CD automation.

Used by `pentool --url <url> --headless --output result.json`.

Reuses the same ScannerAPI active-scan pipeline as `pentool scan active`, but
accepts the URL(s) from the top-level CLI flags so automation is a single,
simple command. Emits machine-readable reports (JSON/HTML/CSV) for later audit.
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


def run_headless_scan(urls: list[str], output: str | None, check_names: list[str] | None = None,
                      concurrency: int = 5, delay: float = 0.0) -> int:
    """Run an active scan against ``urls`` and exit with a process status.

    Args:
        urls: target URL(s).
        output: optional report path (.json / .html / .csv). None = print only.
        check_names: optional list of checks; None = defaults.
        concurrency / delay: scan tuning.

    Returns:
        Exit code (0 on success).
    """
    ScannerAPI = _import_scanner_api()

    from pentool.core.config import get_config

    cfg = get_config()
    api = ScannerAPI(db_path=cfg.db_path)

    findings: list = []

    def on_finding(f) -> None:
        findings.append(f)
        sev = f.severity.upper()
        click.echo(f"  [{sev}] {f.name} — {f.url}")

    def on_progress(done: int, total: int) -> None:
        click.echo(f"\r  Progress: {done}/{total}", nl=False)

    async def _run() -> None:
        await api.start_active_scan(
            urls,
            check_names=check_names,
            on_finding=on_finding,
            on_progress=on_progress,
            concurrency=concurrency,
            request_delay=delay,
        )
        if api._active_task:
            await api._active_task

    click.echo(f"[headless] Active scan on {len(urls)} target(s)...")
    asyncio.run(_run())
    click.echo(f"\nDone. Found {len(findings)} finding(s).")

    if output:
        fmt = "json" if output.endswith(".json") else ("csv" if output.endswith(".csv") else "html")
        asyncio.run(api.generate_report(output, fmt))
        click.echo(f"[headless] Report saved: {output}")

    return 0
