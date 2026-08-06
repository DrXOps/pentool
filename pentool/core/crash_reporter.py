"""Crash reporter — collects and sends anonymous crash reports.

Also sends a one-shot "first run" ping so the admin panel can show an
install counter — see send_first_run_ping(). Both go to the same
pentool-license Cloudflare Worker that already handles license
validation (pentool.core.license._LICENSE_API_BASE) — /api/crash and
/api/telemetry/first_run are public, unauthenticated ingestion
endpoints there, mirrored in pentool-backend's admin.html dashboard.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
import traceback
from typing import Any

# Same Worker as pentool.core.license — kept as a separate literal here
# (rather than importing _LICENSE_API_BASE) so crash reporting has no
# import-time dependency on the licensing module.
_API_BASE = "https://pentool-license.akashtanov2020.workers.dev"


def _get_metadata() -> dict[str, Any]:
    """Collect anonymous metadata for crash report."""
    try:
        from pentool import __version__ as version
    except Exception:
        version = "unknown"
    return {
        "version": version,
        "python": sys.version.split()[0],
        "os": platform.system(),
        "os_version": platform.release(),
        "arch": platform.machine(),
    }


def _anonymize(text: str) -> str:
    """Remove paths and potential tokens from traceback text."""
    import re
    # Remove absolute paths — keep only filename
    text = re.sub(r'  File "([^"]+)"', lambda m: f'  File "{os.path.basename(m.group(1))}"', text)
    # Remove anything that looks like a token/key (long hex strings)
    text = re.sub(r'\b[A-Fa-f0-9]{32,}\b', '<TOKEN>', text)
    return text


async def send_crash_async(exc: BaseException, endpoint: str = f"{_API_BASE}/api/crash") -> None:
    """Send crash report asynchronously. Silently ignores any errors."""
    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        return  # aiohttp not available — skip silently

    try:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb_text = _anonymize("".join(tb_lines))
        payload = {
            "traceback": tb_text,
            "exception": type(exc).__name__,
            **_get_metadata(),
        }
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await session.post(endpoint, json=payload, ssl=False)
    except Exception:
        pass  # never propagate errors from crash reporter


def send_crash(exc: BaseException) -> None:
    """Fire-and-forget crash report from sync context."""
    try:
        from pentool.core.config import get_config
        cfg = get_config()
        if not getattr(cfg, "send_crash_reports", True):
            return
    except Exception:
        pass

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_crash_async(exc))
        loop.close()
    except Exception:
        pass


async def send_first_run_ping_async(endpoint: str = f"{_API_BASE}/api/telemetry/first_run") -> None:
    """Ping the install counter once per machine. Silently ignores errors.

    Dedup happens server-side (keyed by machine_id) — safe to call on every
    startup; only the very first call from a given machine increments the
    counter, so no local "have I already sent this" state is needed here.
    """
    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        return

    try:
        from pentool.core.license import get_machine_id
        machine_id = get_machine_id()
    except Exception:
        return

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await session.post(endpoint, json={"machine_id": machine_id}, ssl=False)
    except Exception:
        pass


def send_first_run_ping() -> None:
    """Fire-and-forget install-counter ping from sync context.

    Respects the same send_crash_reports opt-out as send_crash() — both are
    "anonymous telemetry to Anthropic-free, self-hosted infra" in spirit,
    so one setting covers both rather than adding a second toggle.
    """
    try:
        from pentool.core.config import get_config
        cfg = get_config()
        if not getattr(cfg, "send_crash_reports", True):
            return
    except Exception:
        pass

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_first_run_ping_async())
        loop.close()
    except Exception:
        pass
