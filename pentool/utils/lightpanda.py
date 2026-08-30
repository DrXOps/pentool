"""Lightpanda integration for headless JS rendering (spider crawl / tech detect).

Lightpanda (https://lightpanda.io) is a lightweight browser built in Zig: it
executes JavaScript and renders the DOM without pulling in a full Chromium +
Node-driver stack. This is the "invisible-task" engine for pentool — cheap
(measured ~23 MB RSS/run vs ~456 MB for Playwright+Chromium) and fast.

We drive it through its stable CLI (`lightpanda fetch --dump html <url>`), which
executes JS and prints the serialized post-JS DOM. This gives the rendered HTML
that the crawler needs for SPA/level3-level4 discovery without a heavyweight
browser dependency.

Graceful-by-design: if the binary is not installed, availability returns False
and callers fall back to the old no-JS path (exactly like when Playwright was
missing). The binary is a third-party artifact, not a pip dependency — see
docs (install via the official installer or a release asset under
`lightpanda/browser` on GitHub).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

# stdlib logging (NOT pentool.core.logging) — utils/ must not import core/.
logger = logging.getLogger(__name__)

# Conventional install locations (env override read dynamically in the finder).
_INSTALL_HINTS = (
    "~/.local/bin/lightpanda",
    "~/bin/lightpanda",
    "/usr/local/bin/lightpanda",
    "/usr/bin/lightpanda",
)


def find_lightpanda_binary() -> str | None:
    """Locate a usable `lightpanda` executable, or None if not installed."""
    candidates: list[str] = []
    env_bin = os.environ.get("LIGHTPANDA_BIN")
    if env_bin:
        candidates.append(env_bin)
    on_path = shutil.which("lightpanda")
    if on_path:
        candidates.append(on_path)
    candidates.extend(str(Path(h).expanduser()) for h in _INSTALL_HINTS)
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        p = Path(c)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def is_lightpanda_available() -> bool:
    return find_lightpanda_binary() is not None


async def lightpanda_fetch_html(
    url: str,
    timeout: float = 20.0,
    user_agent: str | None = None,
) -> str | None:
    """Fetch *url*'s post-JS rendered HTML via `lightpanda fetch --dump html`.

    Returns the rendered HTML string, or None if the binary is missing or the
    fetch failed. Never raises.
    """
    binary = find_lightpanda_binary()
    if binary is None:
        return None
    cmd = [binary, "fetch", "--dump", "html", url]
    try:
        # Executes JS and prints the serialized DOM. Output may be large for
        # heavy pages — cap to a sane bound and run in an executor thread so
        # the asyncio loop isn't blocked.
        loop = asyncio.get_running_loop()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={**os.environ, "LIGHTPANDA_NO_COLOR": "1"},
            limit=10 * 1024 * 1024,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            logger.warning("lightpanda fetch timed out for %s", url)
            return None
        if proc.returncode != 0:
            logger.debug("lightpanda fetch exit=%s for %s", proc.returncode, url)
            return None
        html = out.decode("utf-8", errors="replace")
        return html or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("lightpanda fetch error %s: %s", url, exc)
        return None
