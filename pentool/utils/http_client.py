"""Async HTTP client based on aiohttp."""

from __future__ import annotations

import time
from typing import Callable

import aiohttp

from pentool.utils.parser import ParsedRequest, ParsedResponse

# Callback type: called after each request
RequestCallback = Callable[[ParsedRequest, ParsedResponse], None]


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
    ) -> None:
        self._proxy_url = proxy_url
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._follow_redirects = follow_redirects
        self._verify_ssl = verify_ssl
        self._on_request_sent = on_request_sent
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
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

        # Note: scan marker injection removed to fix layer violation
        # (utils cannot import core.config). If needed, pass scan_marker_headers
        # explicitly via constructor parameter.

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
            int((time.monotonic() - start) * 1000)

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
