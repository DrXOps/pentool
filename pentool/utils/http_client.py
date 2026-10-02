"""Async HTTP client based on aiohttp."""

from __future__ import annotations

import logging
import socket
import time
from typing import Any, Callable

import aiohttp

from pentool.utils.parser import ParsedRequest, ParsedResponse

logger = logging.getLogger(__name__)

# Callback type: called after each request
RequestCallback = Callable[[ParsedRequest, ParsedResponse], None]

# ── DNS override ───────────────────────────────────────────────────
# Module-level mapping: host -> (real_ip, ttl_expires_at).
# Populated by DiscoveryRunner._discover_real_ip() via set_dns_override().
# Used by HTTPClient._get_session() to bypass CDN when requested.
# Cleared on app restart.
_DNS_OVERRIDE: dict[str, tuple[str, float]] = {}  # host -> (ip, expires_at)


def set_dns_override(host: str, ip: str, ttl: float = 300.0) -> None:
    """Set a DNS override: *host* will resolve to *ip* for all HTTPClient instances.

    Args:
        host: hostname to override (e.g. "example.com").
        ip: IP address to resolve to (e.g. "203.0.113.1").
        ttl: time-to-live in seconds (default 5 minutes).
    """
    import time
    _DNS_OVERRIDE[host.lower().strip()] = (ip, time.monotonic() + ttl)


def clear_dns_override(host: str | None = None) -> None:
    """Clear DNS override(s). Pass ``host`` to clear one, or None to clear all."""
    if host:
        _DNS_OVERRIDE.pop(host.lower().strip(), None)
    else:
        _DNS_OVERRIDE.clear()


def get_dns_overrides() -> dict[str, str]:
    """Return current active DNS overrides (host -> ip), cleaning expired ones."""
    import time
    now = time.monotonic()
    expired = [h for h, (_, exp) in _DNS_OVERRIDE.items() if now > exp]
    for h in expired:
        del _DNS_OVERRIDE[h]
    return {h: ip for h, (ip, _) in _DNS_OVERRIDE.items()}


class _OverrideResolver:
    """aiohttp resolver that checks _DNS_OVERRIDE before default resolution.

    When a host is in the override table, returns its IP directly.
    Otherwise falls through to the default aiohttp resolver (which uses the OS DNS).
    """

    def __init__(self) -> None:
        self._default = aiohttp.AsyncResolver()

    async def resolve(self, host: str, port: int = 0, family: int = 0) -> list[dict]:
        import time as _time_mod
        now = _time_mod.monotonic()
        host_lower = host.lower().strip()
        if host_lower in _DNS_OVERRIDE:
            ip, expires = _DNS_OVERRIDE[host_lower]
            if now < expires:
                logger.debug("_OverrideResolver: %s -> %s (override)", host, ip)
                return [
                    {
                        "hostname": host,
                        "host": ip,
                        "port": port,
                        "family": socket.AF_INET,
                        "proto": 6,
                        "flags": socket.AI_NUMERICHOST,
                    }
                ]
            # Expired — remove
            del _DNS_OVERRIDE[host_lower]
        return await self._default.resolve(host, port, family)

    async def close(self) -> None:
        await self._default.close()


class HTTPClient:
    """Async HTTP client for sending intercepted requests.

    Supports proxies, timeouts, redirects, and a logging callback.
    """

    def __init__(
        self,
        proxy_url: str | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify_ssl: bool = False,
        on_request_sent: RequestCallback | None = None,
        extra_headers: dict | None = None,
        scan_marker_name: str | None = None,
        scan_marker_value: str | None = None,
        scan_marker_enabled: bool = False,
    ) -> None:
        self._proxy_url = proxy_url
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._follow_redirects = follow_redirects
        self._verify_ssl = verify_ssl
        self._on_request_sent = on_request_sent
        # scan_marker injected from outside (Config layer) — no direct import of core.config
        if extra_headers is None and scan_marker_enabled and scan_marker_name and scan_marker_value:
            extra_headers = {scan_marker_name: scan_marker_value}
            logger.debug("HTTPClient: scan_marker injected: %s: %s",
                         scan_marker_name, scan_marker_value)
        self._extra_headers = extra_headers or {}
        self._session: aiohttp.ClientSession | None = None
        self._dns_override_enabled: bool = False  # set True to use _OverrideResolver

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            if self._dns_override_enabled:
                resolver = _OverrideResolver()
                connector = aiohttp.TCPConnector(ssl=self._verify_ssl, resolver=resolver)
            else:
                connector = aiohttp.TCPConnector(ssl=self._verify_ssl)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
            )
        return self._session

    async def send(self, request: ParsedRequest) -> ParsedResponse:
        session = await self._get_session()

        # Strip hop-by-hop headers + replace Accept-Encoding to exclude br
        send_headers = {}
        for k, v in request.headers.items():
            if k.lower() in ("host", "content-length", "transfer-encoding",
                             "connection", "keep-alive", "proxy-connection"):
                continue
            if k.lower() == "accept-encoding":
                # Remove brotli — aiohttp cannot decode it
                encodings = [e.strip() for e in v.split(",")
                             if e.strip().lower() not in ("br", "zstd")]
                v = ", ".join(encodings) if encodings else "gzip, deflate"
            send_headers[k] = v

        # Inject extra headers (e.g., scan markers passed from scanner layer)
        if self._extra_headers:
            send_headers.update(self._extra_headers)

        body_data = request.body.encode("utf-8") if request.body else None
        kwargs: dict = {
            "headers": send_headers,
            "allow_redirects": self._follow_redirects,
            "data": body_data,
        }
        if self._proxy_url:
            kwargs["proxy"] = self._proxy_url

        start = time.monotonic()
        async with session.request(request.method, request.url, **kwargs) as resp:
            # Read raw bytes — aiohttp decodes gzip/deflate automatically via read()
            resp_body_bytes: bytes = await resp.read()

            # Decode for storage in ParsedResponse (for TUI/reports)
            try:
                resp_body = resp_body_bytes.decode(
                    resp.charset or "utf-8", errors="replace"
                )
            except (LookupError, TypeError):
                resp_body = resp_body_bytes.decode("utf-8", errors="replace")

            resp_headers = dict(resp.headers)
            parsed_resp = ParsedResponse(
                status=resp.status,
                reason=resp.reason or "",
                headers=resp_headers,
                body=resp_body,
                _raw_body=resp_body_bytes,
            )

        if self._on_request_sent:
            self._on_request_sent(request, parsed_resp)

        return parsed_resp

    async def send_raw(self, raw_request: str) -> ParsedResponse:
        from pentool.utils.parser import parse_http_request
        req = parse_http_request(raw_request)
        return await self.send(req)

    def enable_dns_override(self, enabled: bool = True) -> None:
        """Enable/disable DNS override (CDN bypass) for this client.

        When enabled, hosts in the override table (set via set_dns_override())
        will be resolved to the override IP instead of the real DNS.
        The session is recreated on next request.
        """
        if enabled != self._dns_override_enabled:
            self._dns_override_enabled = enabled
            # Force session recreation
            if self._session and not self._session.closed:
                self._session._connector._resolver = None  # type: ignore[attr-defined]
            self._session = None
            logger.debug("HTTPClient: DNS override %s", "enabled" if enabled else "disabled")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get(self, url: str, headers: dict | None = None) -> "ParsedResponse":
        """Convenience method: GET request by URL."""
        req = ParsedRequest(
            method="GET",
            url=url,
            headers=headers or {},
            body="",
        )
        return await self.send(req)

    async def post(self, url: str, body: str = "", headers: dict | None = None) -> "ParsedResponse":
        """Convenience method: POST request by URL."""
        req = ParsedRequest(
            method="POST",
            url=url,
            headers=headers or {"Content-Type": "application/x-www-form-urlencoded"},
            body=body,
        )
        return await self.send(req)

    async def __aenter__(self) -> "HTTPClient":
        """Context manager support: return self."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Context manager support: close session on exit."""
        await self.close()


def get_shared_http_client(
    follow_redirects: bool = True,
    extra_headers: dict | None = None,
    cfg: Any | None = None,
) -> "HTTPClient":
    """Build an HTTPClient from Config (new per call, config is single source of truth)."""
    if cfg is None:
        return HTTPClient(
            verify_ssl=True,
            timeout=10,
            follow_redirects=follow_redirects,
            extra_headers=extra_headers,
        )
    return HTTPClient(
        verify_ssl=cfg.verify_ssl,
        timeout=cfg.request_timeout,
        follow_redirects=follow_redirects,
        extra_headers=extra_headers,
        scan_marker_name=getattr(cfg, "scan_marker_name", None),
        scan_marker_value=getattr(cfg, "scan_marker_value", None),
        scan_marker_enabled=getattr(cfg, "scan_marker_enabled", False),
    )
