"""Parsing and building HTTP requests/responses from raw strings."""

from __future__ import annotations

from dataclasses import dataclass, field

from urllib.parse import urlparse


@dataclass
class ParsedRequest:
    """A parsed HTTP request."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def host(self) -> str:
        """Host from URL or Host header."""
        parsed = urlparse(self.url)
        if parsed.netloc:
            return parsed.netloc
        return self.headers.get("Host", self.headers.get("host", ""))

    @property
    def path(self) -> str:
        """Path from URL (including query string)."""
        parsed = urlparse(self.url)
        result = parsed.path or "/"
        if parsed.query:
            result += "?" + parsed.query
        return result

    @property
    def is_https(self) -> bool:
        """True if the URL starts with https://."""
        return self.url.lower().startswith("https://")


@dataclass
class ParsedResponse:
    """A parsed HTTP response."""

    status: int
    reason: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    http_version: str = "HTTP/1.1"
    # Raw body bytes — used during proxying to avoid re-encoding
    _raw_body: bytes | None = field(default=None, repr=False, compare=False)


def parse_http_request(raw: str) -> ParsedRequest:
    """Parse a raw HTTP request string into a ParsedRequest.

    Args:
        raw: Raw request string (e.g. the content of an intercepted request).

    Returns:
        A ParsedRequest object.

    Raises:
        ValueError: If the string is not a valid HTTP request.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty HTTP request")

    # Split headers and body
    if "\r\n\r\n" in raw:
        head, body = raw.split("\r\n\r\n", 1)
        lines = head.split("\r\n")
    elif "\n\n" in raw:
        head, body = raw.split("\n\n", 1)
        lines = head.split("\n")
    else:
        lines = raw.splitlines()
        body = ""

    if not lines:
        raise ValueError("Empty HTTP request")

    # First line: METHOD PATH HTTP/VERSION
    request_line = lines[0].strip()
    parts = request_line.split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid request line: {request_line!r}")

    method = parts[0].upper()
    path = parts[1]

    # Parse headers
    headers: dict[str, str] = {}
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()

    # Build full URL
    host = headers.get("Host", headers.get("host", ""))
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    elif host:
        _host_parts = host.split(":")
        _is_https_port = len(_host_parts) > 1 and _host_parts[-1] == "443"
        scheme = "https" if _is_https_port or headers.get("X-Forwarded-Proto", "") == "https" else "http"
        url = f"{scheme}://{host}{path}"
    else:
        url = path

    return ParsedRequest(method=method, url=url, headers=headers, body=body)


def parse_http_response(raw: str) -> ParsedResponse:
    """Parse a raw HTTP response string into a ParsedResponse.

    Args:
        raw: Raw response string.

    Returns:
        A ParsedResponse object.

    Raises:
        ValueError: If the string is not a valid HTTP response.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty HTTP response")

    if "\r\n\r\n" in raw:
        head, body = raw.split("\r\n\r\n", 1)
        lines = head.split("\r\n")
    elif "\n\n" in raw:
        head, body = raw.split("\n\n", 1)
        lines = head.split("\n")
    else:
        lines = raw.splitlines()
        body = ""

    if not lines:
        raise ValueError("Empty HTTP response")

    status_line = lines[0].strip()
    parts = status_line.split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid status line: {status_line!r}")

    http_version = parts[0]
    try:
        status = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid status code: {parts[1]!r}")
    reason = parts[2] if len(parts) > 2 else ""

    headers: dict[str, str] = {}
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()

    return ParsedResponse(
        status=status,
        reason=reason,
        headers=headers,
        body=body,
        http_version=http_version,
    )


def build_http_request(req: ParsedRequest) -> str:
    """Build a raw HTTP request string from a ParsedRequest."""
    path = req.path
    lines = [f"{req.method} {path} HTTP/1.1"]

    headers_lower = {k.lower(): k for k in req.headers}

    # Host is required; add it first if missing
    if "host" not in headers_lower:
        host = req.host
        if host:
            lines.append(f"Host: {host}")

    for key, value in req.headers.items():
        lines.append(f"{key}: {value}")

    # Standard headers if missing
    if "user-agent" not in headers_lower:
        lines.append("User-Agent: Mozilla/5.0 (compatible; pentool/1.0)")
    if "accept" not in headers_lower:
        lines.append("Accept: text/html,application/xhtml+xml,*/*;q=0.8")
    if "accept-language" not in headers_lower:
        lines.append("Accept-Language: en-US,en;q=0.9")
    if "connection" not in headers_lower:
        lines.append("Connection: close")

    raw = "\r\n".join(lines) + "\r\n\r\n"
    if req.body:
        raw += req.body

    return raw


def build_http_response(resp: ParsedResponse) -> str:
    """Build a raw HTTP response string from a ParsedResponse.

    Args:
        resp: Response object.

    Returns:
        String in HTTP/1.1 format.
    """
    lines = [f"{resp.http_version} {resp.status} {resp.reason}"]

    for key, value in resp.headers.items():
        lines.append(f"{key}: {value}")

    raw = "\r\n".join(lines) + "\r\n\r\n"
    if resp.body:
        raw += resp.body

    return raw
