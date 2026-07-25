"""CLI-команды сканирования: pentool scan active / passive / report."""

from __future__ import annotations

import asyncio
import sys

import click


@click.group("scan")
def scan() -> None:
    """Модуль Scanner: сканирование уязвимостей."""


@scan.command("active")
@click.option("--url", "urls", required=True, multiple=True, help="Целевой URL (можно несколько).")
@click.option(
    "--checks", "check_names", default=None,
    help="Проверки через запятую: missing_security_headers,info_leak",
)
@click.option("--output", "output", default=None, help="Сохранить findings в файл (json/csv/html).")
@click.option("--concurrency", default=5, show_default=True, help="Параллельных потоков.")
@click.option("--delay", default=0.0, show_default=True, help="Задержка между запросами (сек).")
@click.pass_context
def scan_active(
    ctx: click.Context,
    urls: tuple[str, ...],
    check_names: str | None,
    output: str | None,
    concurrency: int,
    delay: float,
) -> None:
    from pentool.api.scanner_api import ScannerAPI
    from pentool.core.config import get_config

    cfg = (ctx.obj or {}).get("config") or get_config()
    names = [c.strip() for c in check_names.split(",")] if check_names else None

    api = ScannerAPI(db_path=cfg.db_path)

    findings = []

    def on_finding(f) -> None:
        findings.append(f)
        sev = f.severity.upper()
        click.echo(f"  [{sev}] {f.name} — {f.url}")

    def on_progress(done: int, total: int) -> None:
        click.echo(f"\r  Progress: {done}/{total}", nl=False)

    async def _run() -> None:
        await api.start_active_scan(
            list(urls),
            check_names=names,
            on_finding=on_finding,
            on_progress=on_progress,
            concurrency=concurrency,
            request_delay=delay,
        )
        # Ждём завершения задачи
        if api._active_task:
            await api._active_task

    click.echo(f"Starting active scan on {len(urls)} target(s)...")
    asyncio.run(_run())
    click.echo(f"\nDone. Found {len(findings)} finding(s).")

    if output:
        fmt = "html"
        if output.endswith(".json"):
            fmt = "json"
        elif output.endswith(".csv"):
            fmt = "csv"
        asyncio.run(api.generate_report(output, fmt))
        click.echo(f"Report saved: {output}")


@scan.command("passive")
@click.option("--scope", default=None, help="Фильтр хоста (например *.example.com).")
@click.pass_context
def scan_passive(ctx: click.Context, scope: str | None) -> None:
    click.echo(
        "Passive scanning runs automatically while the proxy intercepts traffic.\n"
        "Use the TUI (Scanner tab) to enable Passive mode and view findings."
    )
    if scope:
        click.echo(f"Scope filter: {scope}")


@scan.command("report")
@click.option("--output", required=True, help="Путь к файлу отчёта.")
@click.option(
    "--format", "fmt", default="html",
    type=click.Choice(["html", "json", "csv"], case_sensitive=False),
    show_default=True,
    help="Формат отчёта.",
)
@click.pass_context
def scan_report(ctx: click.Context, output: str, fmt: str) -> None:
    from pentool.api.scanner_api import ScannerAPI
    from pentool.core.config import get_config

    cfg = (ctx.obj or {}).get("config") or get_config()
    api = ScannerAPI(db_path=cfg.db_path)

    async def _run() -> None:
        findings = await api.get_findings(limit=10000)
        if not findings:
            click.echo("No findings in database.")
            return
        await api.generate_report(output, fmt)
        click.echo(f"Report saved: {output} ({len(findings)} findings)")

    asyncio.run(_run())
