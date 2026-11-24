"""``pentool license`` — activation, status and the trial, from the terminal.

Why this command exists: the interface, the site and the docs told users to run
`pentool license activate|trial|status` for a long time, while the CLI had no such
group at all (`python -m pentool license trial` → "No such command"). Activation used
to be possible only inside the TUI, which is useless on a server or in CI. The core
functions already existed; this module is the missing front door, and the texts
elsewhere now have something real to point at.
"""

from __future__ import annotations

import asyncio
import json

import click

from pentool.core.license import (
    LicenseInfo,
    activate_license,
    deactivate_license,
    get_machine_id,
    get_session_license,
    reassign_license,
    start_trial,
)

#: Exit code for "the licence server said no" / "could not reach it".
EXIT_FAILED = 1


def _mask(key: str) -> str:
    """Show enough of a key to recognise it, never the whole thing."""
    if len(key) <= 8:
        return key or "—"
    return f"{key[:5]}…{key[-4:]}"


def _describe(info: LicenseInfo) -> list[str]:
    """Human-readable lines for a licence state (status and post-activation output)."""
    if info.valid and info.plan != "free":
        lines = [
            f"Plan:      {info.plan.upper()}",
            f"Expires:   {info.expires_text}",
            f"Machine:   {get_machine_id()}",
            f"Key:       {_mask(info.license_key)}",
        ]
        if info.features:
            lines.append("Features:  " + ", ".join(info.features))
        return lines
    return [
        "Plan:      FREE",
        "PRO is not active on this machine.",
        "Activate a key:  pentool license activate <KEY>",
        "Or start the trial:  pentool license trial",
    ]


def _as_json(info: LicenseInfo) -> str:
    return json.dumps(
        {
            "valid": info.valid,
            "plan": info.plan,
            "expires_at": info.expires,
            "features": list(info.features),
            "machine_id": get_machine_id(),
            "key": _mask(info.license_key),
            "error": info.error,
        },
        ensure_ascii=False,
        indent=2,
    )


def _run(coroutine):
    """One event loop per command: the CLI is synchronous."""
    return asyncio.run(coroutine)


def _fail(message: str) -> None:
    click.echo(f"✗ {message}", err=True)


@click.group()
def license() -> None:
    """Licence of this Pentool installation."""


@license.command("status")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def status_cmd(as_json: bool) -> None:
    """Show the licence cached on this machine."""
    info = get_session_license()
    if as_json:
        click.echo(_as_json(info))
        return
    for line in _describe(info):
        click.echo(line)
    if info.error:
        click.echo(f"Note: {info.error}", err=True)


@license.command("activate")
@click.argument("key")
@click.option(
    "--reassign",
    is_flag=True,
    help="Take the key off the machine that holds it and bind it here instead.",
)
def activate_cmd(key: str, reassign: bool) -> None:
    """Activate KEY on this machine."""
    info = _run(reassign_license(key) if reassign else activate_license(key))
    if info.valid:
        click.echo(f"✓ Licence activated: {info.plan.upper()}")
        for line in _describe(info):
            click.echo(line)
        click.echo("Restart Pentool to load PRO modules (Scanner, Recon).")
        return
    _fail(info.error or "the licence server rejected the key")
    if "slots in use" in info.error or "bound to another machine" in info.error:
        click.echo("The key is bound to another machine. Move it with:  pentool license activate --reassign <KEY>")
    raise SystemExit(EXIT_FAILED)


@license.command("deactivate")
def deactivate_cmd() -> None:
    """Release this machine's slot so the key can be used elsewhere."""
    try:
        _run(deactivate_license())
    except Exception as exc:  # noqa: BLE001 - the CLI must report, not traceback
        _fail(f"could not deactivate: {exc}")
        raise SystemExit(EXIT_FAILED) from exc
    click.echo("✓ Licence deactivated: the slot is free again.")
    click.echo("Restart Pentool to unload PRO modules.")


@license.command("trial")
def trial_cmd() -> None:
    """Start the 14-day PRO trial (one per machine, no key needed)."""
    info = _run(start_trial())
    if not info.valid:
        _fail(info.error or "the trial was not issued")
        raise SystemExit(EXIT_FAILED)
    click.echo("✓ Trial started: PRO for 14 days")
    for line in _describe(info):
        click.echo(line)
    click.echo("Restart Pentool to load PRO modules (Scanner, Recon).")
