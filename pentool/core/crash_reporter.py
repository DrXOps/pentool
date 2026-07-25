"""Crash reporter — collects and sends anonymous crash reports."""

from __future__ import annotations

import asyncio
import os
import platform
import sys
import traceback
from typing import Any


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


async def send_crash_async(exc: BaseException, endpoint: str = "https://pentool.pro/api/crash") -> None:
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
