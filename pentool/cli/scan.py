"""CLI scan commands: pentool scan active / passive / report."""

from __future__ import annotations

import asyncio

import click

from pentool.cli.scan_runner import ScanRunner, _import_scanner_api


@click.group("scan")
def scan() -> None:
    """Scanner module: vulnerability scanning."""


@scan.command("active")
@click.option("--url", "urls", required=True, multiple=True, help="Target URL (can be specified multiple times).")
@click.option(
    "--checks", "check_names", default=None,
    help="Comma-separated checks: missing_security_headers,info_leak",
)
@click.option("--output", "output", default=None, help="Save findings to file (json/csv/html).")
@click.option("--concurrency", default=5, show_default=True, help="Number of parallel threads.")
@click.option("--delay", default=0.0, show_default=True, help="Delay between requests (seconds).")
def scan_active(
    urls: tuple[str, ...],
    check_names: str | None,
    output: str | None,
    concurrency: int,
    delay: float,
) -> None:
    """Run an active scan on one or more target URLs."""
    names = [c.strip() for c in check_names.split(",")] if check_names else None

    runner = ScanRunner(
        list(urls),
        check_names=names,
        output=output,
        concurrency=concurrency,
        delay=delay,
    )
    sys_exit = runner.run()
    raise SystemExit(sys_exit)


@scan.command("passive")
@click.option("--scope", default=None, help="Host filter (e.g. *.example.com).")
def scan_passive(scope: str | None) -> None:
    click.echo(
        "Passive scanning runs automatically while the proxy intercepts traffic.\n"
        "Use the TUI (Scanner tab) to enable Passive mode and view findings."
    )
    if scope:
        click.echo(f"Scope filter: {scope}")


@scan.command("report")
@click.option("--output", required=True, help="Path to the report file.")
@click.option(
    "--format", "fmt", default="html",
    type=click.Choice(["html", "json", "csv"], case_sensitive=False),
    show_default=True,
    help="Report format.",
)
def scan_report(output: str, fmt: str) -> None:
    """Generate a report from existing findings in the database."""
    ScannerAPI = _import_scanner_api()
    from pentool.core.config import get_config

    cfg = get_config()
    api = ScannerAPI(db_path=cfg.db_path)

    async def _run() -> None:
        findings = await api.get_findings(limit=10000)
        if not findings:
            click.echo("No findings in database.")
            return
        await api.generate_report(output, fmt)
        click.echo(f"Report saved: {output} ({len(findings)} findings)")

    asyncio.run(_run())