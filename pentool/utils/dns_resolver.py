"""Async DNS resolver — A, AAAA, CNAME, MX lookups.

Architecture
------------
Two tiers, zero mandatory deps beyond stdlib:

- **Tier 1 (FREE):** ``socket.getaddrinfo()`` for A/AAAA records.
  No CNAME support, no MX — the Python stdlib DNS client doesn't expose them.
  Available on every Python >= 3.10, no install needed.

- **Tier 2 (PRO):** ``aiodns`` resolver which supports CNAME + MX out of the box.
  Added as a PRO dependency (not in pyproject.toml — pip-installed on demand).

Both tiers share the same ``DnsResolver`` interface so callers don't care
which backend is active.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

logger = logging.getLogger(__name__)


# ── data classes ──────────────────────────────────────────────────────


@dataclass
class DnsRecord:
    """A single DNS record result."""

    host: str          # queried hostname
    type_: str         # "A" | "AAAA" | "CNAME" | "MX"
    value: str         # resolved IP / CNAME target / MX exchange
    ttl: int = 0       # time-to-live from DNS (0 = unknown)


@dataclass
class DnsResult:
    """Complete DNS resolution for one hostname."""

    host: str
    a_records: list[DnsRecord] = field(default_factory=list)
    aaaa_records: list[DnsRecord] = field(default_factory=list)
    cname: str | None = None   # resolved CNAME (first one, if any)
    mx_records: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def first_ip(self) -> str | None:
        """First A-record IP, or None."""
        if self.a_records:
            return self.a_records[0].value
        return None

    @property
    def all_ips(self) -> list[str]:
        """All A and AAAA IPs."""
        return [r.value for r in self.a_records + self.aaaa_records]


# ── resolver ──────────────────────────────────────────────────────────


class DnsResolver:
    """Async DNS resolver with automatic Tier-2 fallback.

    Usage::

        resolver = DnsResolver()
        result = await resolver.resolve("example.com")
        print(result.first_ip, result.cname, result.mx_records)
        batch = await resolver.resolve_batch(["a.com", "b.com"])
        for host, ips in batch.items():
            print(host, ips)
    """

    def __init__(self, cache_ttl: float = 60.0, timeout: float = 5.0) -> None:
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self._cache: dict[str, tuple[float, DnsResult]] = {}  # host → (expires_at, result)
        # Lazy-imported aiodns resolver (None = not available)
        self._aiodns_resolver: Any | None = None

    # ── public API ───────────────────────────────────────────────────

    async def resolve(self, host: str) -> DnsResult:
        """Resolve one hostname — returns cached result if fresh."""
        host = host.strip().lower()
        # 1. Cache hit
        now = monotonic()
        if host in self._cache:
            expires_at, cached = self._cache[host]
            if now < expires_at:
                return cached

        # 2. Resolve — try Tier-2 first (aiodns), fall back to stdlib
        result = await self._resolve(host)
        self._cache[host] = (now + self.cache_ttl, result)
        return result

    async def resolve_batch(
        self,
        hosts: list[str],
        concurrency: int = 20,
    ) -> dict[str, DnsResult]:
        """Resolve multiple hostnames concurrently.

        Args:
            hosts: hostnames to resolve.
            concurrency: max parallel lookups.

        Returns:
            dict mapping host → DnsResult.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _one(host: str) -> tuple[str, DnsResult]:
            async with sem:
                return host, await self.resolve(host)

        tasks = [asyncio.create_task(_one(h)) for h in hosts]
        results: dict[str, DnsResult] = {}
        for task in asyncio.as_completed(tasks):
            host, result = await task
            results[host] = result
        return results

    def invalidate(self, host: str) -> None:
        """Remove host from cache (force re-resolve next call)."""
        self._cache.pop(host.lower().strip(), None)

    def clear_cache(self) -> None:
        """Clear entire DNS cache."""
        self._cache.clear()

    # ── internal ─────────────────────────────────────────────────────

    async def _resolve(self, host: str) -> DnsResult:
        """Try aiodns first, fall back to socket.getaddrinfo."""
        result = await self._resolve_aiodns(host)
        if result is not None:
            return result
        return self._resolve_stdlib(host)

    async def _resolve_aiodns(self, host: str) -> DnsResult | None:
        """Resolve via aiodns (PRO). Returns None if aiodns unavailable."""
        try:
            import aiodns  # type: ignore[import-untyped]
        except ImportError:
            return None

        if self._aiodns_resolver is None:
            self._aiodns_resolver = aiodns.DNSResolver(timeout=self.timeout)

        result = DnsResult(host=host)
        try:
            # A records
            raw = await asyncio.wait_for(
                self._aiodns_resolver.query(host, "A"),
                timeout=self.timeout,
            )
            for r in raw:
                result.a_records.append(
                    DnsRecord(host=host, type_="A", value=r.host, ttl=getattr(r, "ttl", 0))
                )
        except (ImportError, asyncio.TimeoutError, Exception) as exc:
            logger.debug("aiodns A resolve for %s: %s", host, exc)

        try:
            # AAAA
            raw = await asyncio.wait_for(
                self._aiodns_resolver.query(host, "AAAA"),
                timeout=self.timeout,
            )
            for r in raw:
                result.aaaa_records.append(
                    DnsRecord(host=host, type_="AAAA", value=r.host, ttl=getattr(r, "ttl", 0))
                )
        except (ImportError, asyncio.TimeoutError, Exception) as exc:
            logger.debug("aiodns AAAA resolve for %s: %s", host, exc)

        try:
            # CNAME
            raw = await asyncio.wait_for(
                self._aiodns_resolver.query(host, "CNAME"),
                timeout=self.timeout,
            )
            if raw:
                result.cname = raw[0].host
        except (ImportError, asyncio.TimeoutError, Exception) as exc:
            logger.debug("aiodns CNAME resolve for %s: %s", host, exc)

        try:
            # MX
            raw = await asyncio.wait_for(
                self._aiodns_resolver.query(host, "MX"),
                timeout=self.timeout,
            )
            for r in raw:
                if r.host:
                    result.mx_records.append(r.host)
        except (ImportError, asyncio.TimeoutError, Exception) as exc:
            logger.debug("aiodns MX resolve for %s: %s", host, exc)

        # Success or partial — if we got at least something, return
        if result.a_records or result.aaaa_records or result.cname or result.mx_records:
            return result
        # aiodns returned nothing — try stdlib
        return None

    def _resolve_stdlib(self, host: str) -> DnsResult:
        """Fallback via stdlib socket.getaddrinfo — A/AAAA only, no CNAME/MX."""
        result = DnsResult(host=host)
        try:
            raw = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            seen: set[str] = set()
            for family, _, _, _, sockaddr in raw:
                ip = sockaddr[0]
                if ip in seen:
                    continue
                seen.add(ip)
                type_ = "A" if family == socket.AF_INET else "AAAA"
                result.a_records.append(
                    DnsRecord(host=host, type_=type_, value=ip)
                ) if type_ == "A" else result.aaaa_records.append(
                    DnsRecord(host=host, type_=type_, value=ip)
                )
        except socket.gaierror as exc:
            result.error = str(exc)
            logger.debug("stdlib resolve for %s: %s", host, exc)
        return result


# ── convenience ──────────────────────────────────────────────────────

_shared_resolver: DnsResolver | None = None


def get_shared_resolver(
    cache_ttl: float = 60.0,
    timeout: float = 5.0,
) -> DnsResolver:
    """Return module-level shared DnsResolver (lazy init)."""
    global _shared_resolver
    if _shared_resolver is None:
        _shared_resolver = DnsResolver(cache_ttl=cache_ttl, timeout=timeout)
    return _shared_resolver