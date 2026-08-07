"""Main CLI command group."""

from __future__ import annotations

import click

from pentool.core.config import get_config
from pentool.core.logging import setup_logging


@click.group()
@click.version_option(package_name="pentool")
@click.option("--config", "config_path", default=None, help="Path to the configuration file.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output (DEBUG).")
@click.pass_context
def cli(ctx: click.Context, config_path: str | None, verbose: bool) -> None:
    """Pentool — a command-line tool for web application penetration testing.

    Run without arguments to open the TUI:

        pentool

    Or use the commands below for command-line usage.
    """
    ctx.ensure_object(dict)

    cfg = get_config()
    if config_path:
        from pentool.core.config import Config
        cfg = Config.load(config_path)

    log_level = "DEBUG" if verbose else cfg.log_level
    setup_logging(cfg.log_file, log_level)

    ctx.obj["config"] = cfg


# Import and register command groups
from pentool.cli.project import project  # noqa: E402

cli.add_command(project)


from pentool.cli.proxy import proxy  # noqa: E402

cli.add_command(proxy)


@cli.group()
def repeater() -> None:
    """Repeater module: manual request sending."""


@repeater.command("send")
@click.option("--request-file", required=True, type=click.Path(exists=True), help="File containing the HTTP request.")
def repeater_send(request_file: str) -> None:
    click.echo(f"Repeater send {request_file} — not implemented yet.")


@cli.group()
def intruder() -> None:
    """Intruder module: automated attacks."""


@intruder.command("run")
@click.option("--request", "request_file", required=True, type=click.Path(exists=True))
@click.option("--payloads", required=True, type=click.Path(exists=True))
@click.option("--attack", default="sniper", show_default=True,
              type=click.Choice(["sniper", "battering_ram", "pitchfork", "cluster_bomb"]))
def intruder_run(request_file: str, payloads: str, attack: str) -> None:
    click.echo(f"Intruder run [{attack}] — not implemented yet.")


from pentool.cli.scan import scan  # noqa: E402

cli.add_command(scan)


@cli.command("decode")
@click.argument("operation", type=click.Choice([
    "url_encode", "url_decode",
    "base64_encode", "base64_decode",
    "base64url_encode", "base64url_decode",
    "html_encode", "html_decode",
    "hex_encode", "hex_decode",
    "unicode_escape", "unicode_unescape",
    "md5", "sha1", "sha256",
]))
@click.argument("text")
def decode_cmd(operation: str, text: str) -> None:
    """Encode/decode/hash text."""
    from pentool.utils.coder import apply_operation
    try:
        result = apply_operation(operation, text)
        click.echo(result)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@cli.command("update")
@click.option("--check", "check_only", is_flag=True, default=False,
              help="Only check for updates without installing.")
def update_cmd(check_only: bool) -> None:
    """Check for and install Pentool updates."""
    from pentool.core.updater import check_update_sync, do_pip_upgrade

    click.echo("Checking for updates...")
    info = check_update_sync()

    if info.error:
        click.echo(f"Could not check for updates: {info.error}", err=True)
        raise SystemExit(1)

    if not info.has_update:
        click.echo(f"Already up to date (version {info.latest_version}).")
        return

    click.echo(f"New version available: {info.latest_version}")
    click.echo(f"Release notes: {info.url}")

    if check_only:
        return

    if click.confirm(f"Install {info.latest_version} now?", default=True):
        click.echo("Upgrading via pip...")
        if do_pip_upgrade():
            click.echo("Upgrade successful. Restart Pentool to use the new version.")
            _sync_pro_package_after_upgrade()
        else:
            click.echo(
                "pip upgrade failed. You can update manually:\n"
                "  pip install --upgrade pentool",
                err=True,
            )
            raise SystemExit(1)


def _sync_pro_package_after_upgrade() -> None:
    """Re-download the PRO package too, if one is active on this machine.

    `pip install --upgrade pentool` only touches the FREE package — the PRO
    package lives separately in ~/.pentool/pro/ and is otherwise only ever
    (re)downloaded by check_and_update_pro_package(), which normally runs in
    the background on TUI startup. Doing it here too means a CLI-driven
    upgrade doesn't leave a stale PRO build around until the next TUI launch.
    Best-effort — never fails the overall upgrade if this part doesn't work.
    """
    import asyncio

    from pentool.core.license import PRO_PACKAGE_DIR, check_and_update_pro_package

    if not PRO_PACKAGE_DIR.exists():
        return  # PRO was never activated on this machine — nothing to sync

    try:
        click.echo("Checking for a newer PRO build...")
        updated = asyncio.run(check_and_update_pro_package())
        if updated:
            click.echo("PRO package updated to the latest build.")
    except Exception as exc:
        click.echo(f"Could not check for a PRO update: {exc}", err=True)


@cli.group()
def license() -> None:
    """License management: trial, activation, status."""


@license.command("trial")
def license_trial() -> None:
    """Start a 14-day PRO trial (one per machine)."""
    import asyncio

    from pentool.core.license import start_trial

    click.echo("Requesting a 14-day PRO trial...")
    info = asyncio.run(start_trial())

    if not info.valid:
        click.echo(f"Could not start trial: {info.error}", err=True)
        raise SystemExit(1)

    click.echo(f"Trial started — key: {info.license_key}")
    click.echo(f"Plan: {info.plan.upper()} | Expires: {info.expires_text}")
    click.echo(f"Features: {', '.join(info.features) or 'none'}")


@license.command("activate")
@click.argument("key")
def license_activate(key: str) -> None:
    """Activate a license key (PROD-XXXX-XXXX-XXXX)."""
    import asyncio

    from pentool.core.license import activate_license, invalidate_session_license

    click.echo(f"Activating license key {key}...")
    info = asyncio.run(activate_license(key))
    invalidate_session_license()

    if not info.valid:
        click.echo(f"Activation failed: {info.error}", err=True)
        raise SystemExit(1)

    click.echo(f"License activated — plan: {info.plan.upper()}")
    click.echo(f"Expires: {info.expires_text}")
    click.echo(f"Features: {', '.join(info.features) or 'none'}")


@license.command("status")
def license_status() -> None:
    """Show the current license status."""
    from pentool.core.license import get_license

    info = get_license()
    click.echo(f"Status:  {info.status_text}")
    click.echo(f"Plan:    {info.plan}")
    click.echo(f"Expires: {info.expires_text}")
    click.echo(f"Machine: {info.machine_id}")
    if info.features:
        click.echo(f"Features: {', '.join(info.features)}")
    if info.error:
        click.echo(f"Note: {info.error}")


@license.command("deactivate")
def license_deactivate() -> None:
    """Deactivate the current license (delete local cache)."""
    from pentool.core.license import deactivate_license, invalidate_session_license

    deactivate_license()
    invalidate_session_license()
    click.echo("License deactivated.")
