"""Main CLI command group."""

from __future__ import annotations

import click

from pentool.core.config import get_config
from pentool.core.logging import setup_logging


@click.group()
@click.version_option(package_name="pentool")
@click.option("--config", "config_path", default=None, help="Path to the configuration file.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output (DEBUG).")
@click.option("--url", "cli_urls", multiple=True, default=None,
              help="Target URL(s). With --headless runs a headless scan; without, launches the TUI.")
@click.option("--headless", is_flag=True, default=False,
              help="Run without the TUI (headless), for CI/CD automation.")
@click.option("--output", "cli_output", default=None,
              help="Save headless findings to file (.json / .html / .csv).")
@click.option("--check", "cli_checks", default=None,
              help="Comma-separated checks (e.g. xss,sqli,info_leak). Default: all.")
@click.option("--threads", "cli_threads", default=10, type=int, show_default=True,
              help="Number of parallel scan threads.")
@click.option("--delay", "cli_delay", default=0.0, type=float, show_default=True,
              help="Delay between requests (seconds).")
@click.option("--use-ai", "cli_use_ai", is_flag=True, default=False,
              help="Enable AI-assisted scanning (endpoint discovery, WAF bypass).")
@click.option("--crawl", "cli_crawl", is_flag=True, default=False,
              help="Crawl the target before scanning (requires Lightpanda for JS).")
@click.option("--depth", "cli_depth", default=3, type=int, show_default=True,
              help="Crawl depth (requires --crawl).")
@click.option("--max-pages", "cli_max_pages", default=100, type=int, show_default=True,
              help="Max pages to crawl (requires --crawl).")
@click.option("--format", "cli_format", default="auto",
              type=click.Choice(["auto", "json", "html", "csv"], case_sensitive=False),
              help="Report format (default: auto from --output extension).")
@click.pass_context
def cli(ctx: click.Context,
        config_path: str | None, verbose: bool,
        cli_urls: tuple[str, ...] | None, headless: bool,
        cli_output: str | None,
        cli_checks: str | None,
        cli_threads: int,
        cli_delay: float,
        cli_use_ai: bool,
        cli_crawl: bool,
        cli_depth: int,
        cli_max_pages: int,
        cli_format: str) -> None:
    """Pentool — web application security testing toolkit.

    Run without arguments to open the TUI:

        pentool

    One-shot / CI/CD:

        pentool --url https://example.com --headless --output result.json

    Full CI/CD options:

        pentool --url https://example.com --headless --check xss,sqli \\
                --threads 20 --delay 0.5 --use-ai --crawl --output report.json
    """
    ctx.ensure_object(dict)

    cfg = get_config()
    if config_path:
        from pentool.core.config import Config
        cfg = Config.load(config_path)

    log_level = "DEBUG" if verbose else cfg.log_level
    setup_logging(cfg.log_file, log_level)

    ctx.obj["config"] = cfg

    if cli_urls:
        urls = list(cli_urls)
        if headless:
            from pentool.cli.headless import run_headless_scan
            names = [c.strip() for c in cli_checks.split(",")] if cli_checks else None
            run_headless_scan(
                urls,
                output=cli_output,
                check_names=names,
                concurrency=cli_threads,
                delay=cli_delay,
                use_ai=cli_use_ai,
                crawl=cli_crawl,
                crawl_depth=cli_depth,
                max_pages=cli_max_pages,
                report_format=cli_format,
            )
        else:
            from pentool.tui.app import PentoolApp
            app = PentoolApp()
            app._pending_start_urls = urls
            app.run()