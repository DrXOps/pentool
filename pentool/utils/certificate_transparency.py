"""Certificate Transparency (crt.sh) client.

Fetches certificate transparency logs from crt.sh API and extracts
subdomains for a given domain.

Usage::

    from pentool.utils.certificate_transparency import CertTransparencyClient

    client = CertTransparencyClient()
    subdomains = await client.get_subdomains("example.com")
    # → ["admin.example.com", "api.example.com", ...]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

CRT_SH_URL = "https://crt.sh/?q=%25.{domain}&output=json"
# Rate-limit: crt.sh has no documented limit but will throttle heavy usage.
# 10 req/min is a safe default for casual use.
MAX_REQUESTS_PER_MINUTE = 10


@dataclass
class CertResult:
    """Result from a crt.sh lookup."""

    domain: str
    subdomains: set[str] = field(default_factory=set)
    error: str | None = None
    cert_count: int = 0


class CertTransparencyClient:
    """Async crt.sh client with rate-limiting and retries.

    Args:
        session: optional shared aiohttp.ClientSession.
        rate_limit: max requests per minute (0 = unlimited).
        retries: number of retries on non-fatal failure.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        rate_limit: int = MAX_REQUESTS_PER_MINUTE,
        retries: int = 3,
    ) -> None:
        self._session = session
        self._own_session = session is None
        self._rate_limit = rate_limit
        self._retries = retries
        self._last_request_time: float = 0.0
        self._min_interval = 60.0 / rate_limit if rate_limit > 0 else 0.0

    # ── public API ───────────────────────────────────────────────────

    async def get_subdomains(self, domain: str) -> list[str]:
        """Fetch subdomains from crt.sh.

        Returns a sorted deduplicated list of subdomain hostnames.
        Returns an empty list on failure (error is logged).
        """
        result = await self.get_subdomains_detailed(domain)
        return sorted(result.subdomains)

    async def get_subdomains_detailed(self, domain: str) -> CertResult:
        """Fetch subdomains with metadata."""
        result = CertResult(domain=domain)

        for attempt in range(1, self._retries + 1):
            self._throttle()
            try:
                data = await self._fetch(domain)
                if data is None:
                    result.error = "empty response"
                    return result

                subdomains: set[str] = set()
                for entry in data:
                    result.cert_count += 1
                    name_value = entry.get("name_value", "")
                    if not name_value:
                        continue
                    for name in name_value.split("\n"):
                        cleaned = name.strip().lower()
                        if cleaned and not cleaned.startswith("*."):
                            subdomains.add(cleaned)
                        elif cleaned.startswith("*."):
                            # Wildcard: add the base (e.g. *.example.com → example.com is already the domain)
                            # We still add the bare wildcard target as an implicit host
                            subdomains.add(cleaned[2:])  # "*.admin.example.com" → "admin.example.com"

                # Filter: keep only subdomains that actually belong to the domain
                result.subdomains = {
                    s for s in subdomains
                    if s.endswith(f".{domain}") or s == domain
                }
                return result

            except aiohttp.ClientError as exc:
                logger.warning(
                    "crt.sh attempt %d/%d for %s: %s",
                    attempt, self._retries, domain, exc,
                )
                if attempt < self._retries:
                    delay = 2.0 * attempt  # 2, 4, 6 seconds
                    logger.debug("retrying crt.sh in %.0fs", delay)
                    await asyncio.sleep(delay)
                else:
                    result.error = str(exc)
            except json.JSONDecodeError as exc:
                logger.warning("crt.sh JSON decode error for %s: %s", domain, exc)
                result.error = f"JSON decode: {exc}"
                return result  # no retry for bad JSON
            except Exception as exc:
                logger.error("crt.sh unexpected error for %s: %s", domain, exc)
                result.error = str(exc)
                return result

        return result

    async def close(self) -> None:
        """Close the session if we own it."""
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    # ── internal ─────────────────────────────────────────────────────

    def _throttle(self) -> None:
        """Rate-limit: wait if we're hitting too fast."""
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            wait = self._min_interval - elapsed
            time.sleep(wait)
        self._last_request_time = time.monotonic()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "pentool-recon/1.0"},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            self._own_session = True
        return self._session

    async def _fetch(self, domain: str) -> list[dict[str, Any]] | None:
        """Fetch raw JSON from crt.sh."""
        url = CRT_SH_URL.replace("{domain}", domain)
        session = await self._ensure_session()

        async with session.get(url) as resp:
            if resp.status != 200:
                logger.warning(
                    "crt.sh HTTP %d for %s",
                    resp.status, domain,
                )
                return None
            text = await resp.text()
            if not text or text.strip() == "[]":
                return []
            # crt.sh returns either a JSON array or (rarely) an error page
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.warning("crt.sh returned non-JSON for %s (head: %s…)", domain, text[:200])
                return None