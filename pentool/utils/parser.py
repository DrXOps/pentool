"""Парсинг и сборка HTTP-запросов/ответов из сырых строк."""

from __future__ import annotations

from dataclasses import dataclass, field

from urllib.parse import urlparse


@dataclass
class ParsedRequest:
    """Распарсенный HTTP-запрос."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def host(self) -> str:
        """Хост из URL или заголовка Host."""
        parsed = urlparse(self.url)
        if parsed.netloc:
            return parsed.netloc
        return self.headers.get("Host", self.headers.get("host", ""))

    @property
    def path(self) -> str:
        """Путь из URL (включая query string)."""
        parsed = urlparse(self.url)
        result = parsed.path or "/"
        if parsed.query:
            result += "?" + parsed.query
        return result

    @property
    def is_https(self) -> bool:
        """True, если URL начинается с https://."""
        return self.url.lower().startswith("https://")


@dataclass
class ParsedResponse:
    """Распарсенный HTTP-ответ."""

    status: int
    reason: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    http_version: str = "HTTP/1.1"
    # Сырые байты тела — используются при проксировании чтобы не перекодировать
    _raw_body: bytes | None = field(default=None, repr=False, compare=False)


def parse_http_request(raw: str) -> ParsedRequest:
    """Распарсить сырую строку HTTP-запроса в ParsedRequest.

    Args:
        raw: Сырая строка запроса (например, содержимое перехваченного запроса).

    Returns:
        Объект ParsedRequest.

    Raises:
        ValueError: Если строка не является корректным HTTP-запросом.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty HTTP request")

    # Разделить заголовки и тело
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

    # Первая строка: METHOD PATH HTTP/VERSION
    request_line = lines[0].strip()
    parts = request_line.split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid request line: {request_line!r}")

    method = parts[0].upper()
    path = parts[1]

    # Разобрать заголовки
    headers: dict[str, str] = {}
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()

    # Собрать полный URL
    host = headers.get("Host", headers.get("host", ""))
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    elif host:
        scheme = "https" if "443" in host or headers.get("X-Forwarded-Proto", "") == "https" else "http"
        url = f"{scheme}://{host}{path}"
    else:
        url = path

    return ParsedRequest(method=method, url=url, headers=headers, body=body)


def parse_http_response(raw: str) -> ParsedResponse:
    """Распарсить сырую строку HTTP-ответа в ParsedResponse.

    Args:
        raw: Сырая строка ответа.

    Returns:
        Объект ParsedResponse.

    Raises:
        ValueError: Если строка не является корректным HTTP-ответом.
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
    """Собрать сырую строку HTTP-запроса из ParsedRequest."""
    path = req.path
    lines = [f"{req.method} {path} HTTP/1.1"]

    headers_lower = {k.lower(): k for k in req.headers}

    # Host — обязателен, добавляем первым если отсутствует
    if "host" not in headers_lower:
        host = req.host
        if host:
            lines.append(f"Host: {host}")

    for key, value in req.headers.items():
        lines.append(f"{key}: {value}")

    # Стандартные заголовки если отсутствуют
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
    """Собрать сырую строку HTTP-ответа из ParsedResponse.

    Args:
        resp: Объект ответа.

    Returns:
        Строка в формате HTTP/1.1.
    """
    lines = [f"{resp.http_version} {resp.status} {resp.reason}"]

    for key, value in resp.headers.items():
        lines.append(f"{key}: {value}")

    raw = "\r\n".join(lines) + "\r\n\r\n"
    if resp.body:
        raw += resp.body

    return raw
