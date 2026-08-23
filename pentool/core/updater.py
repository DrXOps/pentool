"""Update checker — checks GitHub releases for a newer version."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class UpdateInfo:
    has_update: bool
    latest_version: str
    url: str
    error: str = ""


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse 'v1.2.3' or '1.2.3' into (1, 2, 3)."""
    v = v.strip().lstrip("v").strip()
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except Exception:
        return (0,)


async def check_update_async(
    owner: str = "sudores",
    repo: str = "pentool",
    timeout: float = 6.0,
) -> UpdateInfo:
    """Query GitHub releases API and compare with installed version."""
    try:
        from pentool import __version__ as current_version
    except Exception:
        current_version = "0.0.0"

    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        return UpdateInfo(has_update=False, latest_version=current_version, url="",
                          error="aiohttp not installed")

    try:
        aio_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=aio_timeout) as session:
            async with session.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return UpdateInfo(has_update=False, latest_version=current_version,
                                      url="", error=f"HTTP {resp.status}")
                data = await resp.json()
    except asyncio.TimeoutError:
        return UpdateInfo(has_update=False, latest_version=current_version,
                          url="", error="timeout")
    except Exception as exc:
        return UpdateInfo(has_update=False, latest_version=current_version,
                          url="", error=str(exc))

    latest_tag = data.get("tag_name", "")
    html_url   = data.get("html_url", "")
    if not latest_tag:
        return UpdateInfo(has_update=False, latest_version=current_version,
                          url="", error="no tag_name in response")

    has_update = _parse_version(latest_tag) > _parse_version(current_version)
    return UpdateInfo(has_update=has_update, latest_version=latest_tag, url=html_url)


def check_update_sync() -> UpdateInfo:
    """Synchronous wrapper for use outside an async context."""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(check_update_async())
        loop.close()
        return result
    except Exception as exc:
        return UpdateInfo(has_update=False, latest_version="", url="", error=str(exc))


def do_pip_upgrade() -> bool:
    """Attempt to upgrade via pip. Returns True on success."""
    import subprocess
    import sys
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pentool"],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False
