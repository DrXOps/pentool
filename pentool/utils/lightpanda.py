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
and callers fall back to the plain no-JS path. The binary is a third-party
artifact, not a pip dependency — see docs (install via the official installer
or a release asset under `lightpanda/browser` on GitHub).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
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


# ── Auto-install ──────────────────────────────────────────────────────────

_LIGHTPANDA_VERSION = "0.3.7"
_LIGHTPANDA_URL_TEMPLATE = (
    "https://github.com/lightpanda-io/browser/releases/download/"
    f"{_LIGHTPANDA_VERSION}/"
    "lightpanda-{arch}-linux"
)


def _detect_arch() -> str:
    """Return the architecture part of the Lightpanda release asset name."""
    arch = "x86_64"  # default
    machine = os.uname().machine.lower()
    if machine in ("aarch64", "arm64"):
        arch = "aarch64"
    return arch


def ensure_lightpanda_installed_sync() -> bool:
    """Synchronous wrapper — call before event loop starts (from __main__).

    Downloads Lightpanda if missing. Prints progress to stderr.
    Returns True if the binary is available after the call.
    """
    if find_lightpanda_binary() is not None:
        return True
    # Run the async installer in a fresh event loop (we are pre-asyncio here).
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(ensure_lightpanda_installed())
        loop.close()
        return result
    except Exception as exc:
        logger.error("Lightpanda auto-install failed: %s", exc)
        return False


async def ensure_lightpanda_installed(force: bool = False) -> bool:
    """Download Lightpanda binary if not already installed.

    Args:
        force: If True, re-download even if the binary exists.

    Returns:
        True if the binary is available after the call.
    """
    if not force and find_lightpanda_binary() is not None:
        return True

    dest_dir = Path.home() / ".local" / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "lightpanda"

    arch = _detect_arch()
    url = _LIGHTPANDA_URL_TEMPLATE.format(arch=arch)

    logger.info("Lightpanda not found — downloading %s …", url)
    print(f"  ↻ Downloading Lightpanda {_LIGHTPANDA_VERSION} ({arch})…",
          file=sys.stderr, flush=True)

    import urllib.request

    tmp = dest.with_suffix(".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            chunk_size = 1 << 20  # 1 MiB
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"  ↻ {pct}% ({downloaded >> 20} MiB / {total >> 20} MiB)",
                              file=sys.stderr, flush=True)
        # Проверка размера — минимум 5 MiB
        if not tmp.exists() or tmp.stat().st_size < 5_000_000:
            logger.error("Lightpanda download too small — aborting")
            tmp.unlink(missing_ok=True)
            return False
        tmp.chmod(0o755)
        tmp.replace(dest)
        logger.info("Lightpanda installed → %s (%s bytes)", dest, dest.stat().st_size)
        print(f"  ✓ Lightpanda {_LIGHTPANDA_VERSION} installed → {dest}",
              file=sys.stderr, flush=True)
        return True
    except Exception as exc:
        logger.error("Lightpanda download failed: %s", exc)
        tmp.unlink(missing_ok=True)
        return False


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
