"""CLI commands for proxy server management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from pentool.core.config import get_config
from pentool.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@click.group()
def proxy() -> None:
    """HTTP/HTTPS proxy server management."""


@proxy.command("start")
@click.option("--port", default=8080, show_default=True, help="Proxy port.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to listen on.")
@click.option("--cert-dir", default=None, help="Directory for CA certificates.")
@click.option("--db", "db_path", default=None, help="Path to the SQLite database for logging.")
@click.option("--intercept", is_flag=True, default=False, help="Enable interactive interception.")
@click.option("--scope", default="", help="Comma-separated list of hosts (empty = all).")
def proxy_start(
    port: int,
    host: str,
    cert_dir: str | None,
    db_path: str | None,
    intercept: bool,
    scope: str,
) -> None:
    cfg = get_config()
    setup_logging(cfg.log_file, cfg.log_level)

    _cert_dir = cert_dir or cfg.cert_dir
    _db_path = db_path or cfg.db_path

    from pentool.api.proxy_api import ProxyAPI

    api = ProxyAPI()
    server = api.create_proxy(
        host=host,
        port=port,
        cert_dir=_cert_dir,
        db_path=_db_path,
    )
    server.intercept_enabled = intercept

    if scope:
        server.set_scope([h.strip() for h in scope.split(",") if h.strip()])

    click.echo(f"Starting proxy on {host}:{port}")
    click.echo(f"  CA certs  : {_cert_dir}")
    click.echo(f"  Database  : {_db_path}")
    click.echo(f"  Intercept : {'ON' if intercept else 'OFF'}")
    if server.scope:
        click.echo(f"  Scope     : {', '.join(server.scope)}")
    else:
        click.echo("  Scope     : ALL hosts")
    click.echo("Press Ctrl+C to stop.\n")

    # Initialize database if needed
    from pentool.core.database import init_db_sync
    try:
        init_db_sync(_db_path)
    except Exception as exc:
        click.echo(f"Warning: could not init database: {exc}", err=True)

    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        click.echo("\nProxy stopped.")


@proxy.command("status")
@click.option("--port", default=8080, show_default=True, help="Port to check.")
def proxy_status(port: int) -> None:
    """Check whether the proxy is listening on the specified port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        result = s.connect_ex(("127.0.0.1", port))
    if result == 0:
        click.echo(f"Proxy is RUNNING on port {port}")
    else:
        click.echo(f"Proxy is NOT running on port {port}")


@proxy.command("history")
@click.option("--db", "db_path", default=None, help="Path to the SQLite database.")
@click.option("--limit", default=20, show_default=True, help="Number of records.")
@click.option("--method", default=None, help="Filter by method (GET, POST, ...).")
@click.option("--host", default=None, help="Filter by host (URL substring).")
def proxy_history(
    db_path: str | None,
    limit: int,
    method: str | None,
    host: str | None,
) -> None:
    cfg = get_config()
    _db_path = db_path or cfg.db_path

    if not Path(_db_path).exists():
        click.echo(f"Database not found: {_db_path}", err=True)
        raise SystemExit(1)

    async def _fetch() -> list:
        from pentool.storage.http_storage import HttpStorage
        storage = HttpStorage()
        await storage.init_db(_db_path)
        filters: dict = {}
        if method:
            filters["method"] = [method.upper()]
        if host:
            filters["host"] = host
        return await storage.get_metadata_batch(
            offset=0,
            limit=limit,
            filters=filters if filters else None,
            order_by="id",
            desc=True,
        )

    rows = asyncio.run(_fetch())

    if not rows:
        click.echo("No requests found.")
        return

    click.echo(f"{'ID':<6} {'METHOD':<8} {'STATUS':<8} {'URL'}")
    click.echo("-" * 80)
    for row in rows:
        rid = row["id"]
        meth = row.get("method", "-")
        url = row.get("url", "-")
        status = row.get("status_code")
        status_str = str(status) if status else "-"
        url_short = url[:60] + "..." if len(url) > 60 else url
        click.echo(f"{rid:<6} {meth:<8} {status_str:<8} {url_short}")


@proxy.command("ca-info")
@click.option("--cert-dir", default=None, help="CA certificate directory.")
def proxy_ca_info(cert_dir: str | None) -> None:
    cfg = get_config()
    _cert_dir = cert_dir or cfg.cert_dir
    ca_cert = Path(_cert_dir) / "ca.crt"

    if ca_cert.exists():
        click.echo(f"CA certificate: {ca_cert}")
    else:
        from pentool.utils.cert import generate_ca_cert
        cert_path, _ = generate_ca_cert(_cert_dir)
        click.echo(f"CA certificate generated: {cert_path}")

    click.echo("\nTo trust the CA certificate:")
    click.echo("")
    click.echo("  Linux (Ubuntu/Debian):")
    click.echo(f"    sudo cp {ca_cert} /usr/local/share/ca-certificates/pentool-ca.crt")
    click.echo("    sudo update-ca-certificates")
    click.echo("")
    click.echo("  macOS:")
    click.echo(f"    sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain {ca_cert}")
    click.echo("")
    click.echo("  Firefox / Chrome:")
    click.echo("    Settings → Certificates → Import → select ca.crt → Trust for websites")
