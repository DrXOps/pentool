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

from pentool.core.logging import get_logger

# Same Worker as pentool.core.license — kept as a separate literal here
# (rather than importing _LICENSE_API_BASE) so crash reporting has no
# import-time dependency on the licensing module.
_API_BASE = "https://pentool-license.akashtanov2020.workers.dev"

logger = get_logger(__name__)


def _get_metadata() -> dict[str, Any]:
    """Collect anonymous metadata for crash report."""
    try:
        from pentool import __version__ as version
    except ImportError:
        version = "unknown"
    return {
        "version": version,
        "python": sys.version.split()[0],
        "os": platform.system(),
        "os_version": platform.release(),
        "arch": platform.machine(),
    }


def _save_local_crash(exc: BaseException, tb_text: str | None = None) -> None:
    """Write crash traceback to a local file as fallback.

    Used when the network send fails or aiohttp is unavailable — ensures
    the crash information is never silently lost.
    """
    try:
        from datetime import datetime

        from pentool.core.config import DEFAULT_CONFIG_DIR

        crash_log = DEFAULT_CONFIG_DIR / "crash_last.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n=== CRASH {ts} ===\n")
            f.write(f"Exception: {type(exc).__name__}: {exc}\n")
            if tb_text:
                f.write(tb_text)
            else:
                import traceback as _tb

                _tb.print_exc(file=f)
            f.write(f"=== END CRASH {ts} ===\n")
    except (
        Exception
    ):  # logging-ok: the dump cannot be written any more, and recursing into the logger is worse than silence
        pass  # last resort — nothing we can do


def _anonymize(text: str) -> str:
    """Remove paths and potential tokens from traceback text."""
    import re

    # Remove absolute paths — keep only filename
    text = re.sub(r'  File "([^"]+)"', lambda m: f'  File "{os.path.basename(m.group(1))}"', text)
    # Remove anything that looks like a token/key (long hex strings)
    text = re.sub(r"\b[A-Fa-f0-9]{32,}\b", "<TOKEN>", text)
    return text


async def send_crash_async(exc: BaseException, endpoint: str = f"{_API_BASE}/api/crash", source: str = "cli") -> None:
    """Send crash report asynchronously. Silently ignores any errors.

    ``source`` tells the admin panel where the app died: ``cli`` for the
    command-line entry point, ``tui`` for a fatal exception inside Textual (a
    different fix path — the TUI crash also loses the screen state).

    Falls back to a local crash log if the HTTP request fails — never loses
    the traceback entirely.
    """
    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        _save_local_crash(exc)
        return  # aiohttp not available — save locally

    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_text = _anonymize("".join(tb_lines))
    payload = {
        "traceback": tb_text,
        "exception": type(exc).__name__,
        "source": source,
        **_get_metadata(),
    }

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await session.post(endpoint, json=payload, ssl=False)
    except Exception:
        # The network failed — keep the report locally so the traceback is not lost.
        # Caught broadly on purpose: fire-and-forget telemetry must not
        # crash the app on any server response (this is pinned by
        # test_send_crash_async_post_error_swallowed), so the cause
        # is logged instead of being narrowed.
        logger.warning("crash report not sent — saved locally", exc_info=True)
        _save_local_crash(exc, tb_text)


def send_crash(exc: BaseException, source: str = "cli") -> None:
    """Fire-and-forget crash report from sync context.

    ``source`` is forwarded to the server (``cli`` / ``tui``) — see
    `send_crash_async`.
    """
    try:
        from pentool.core.config import get_config

        cfg = get_config()
        if not getattr(cfg, "send_crash_reports", True):
            return
    except Exception:
        # Fail-open on purpose, pinned by tests
        # (test_send_crash_config_exception_still_attempts): a broken config must not
        # silently disable crash reports — they are needed exactly when
        # something is broken.
        logger.debug("crash-telemetry: opt-out setting not read — sending anyway", exc_info=True)

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_crash_async(exc, source=source))
        loop.close()
    except (RuntimeError, OSError):
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
        logger.warning("first-run ping: machine id not read — not sending", exc_info=True)
        return

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await session.post(endpoint, json={"machine_id": machine_id}, ssl=False)
    except Exception:
        # The install ping is fire-and-forget too: a network error must not
        # break anything, but there is no reason to stay silent about it either.
        logger.warning("first-run ping not sent", exc_info=True)


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
        # Fail-open on purpose, pinned by tests
        # (test_send_crash_config_exception_still_attempts): a broken config must not
        # silently disable crash reports — they are needed exactly when
        # something is broken.
        logger.debug("crash-telemetry: opt-out setting not read — sending anyway", exc_info=True)

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_first_run_ping_async())
        loop.close()
    except (RuntimeError, OSError):
        pass
