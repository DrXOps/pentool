"""URL helpers shared by the CLI start-up path and the browser fetch."""

from __future__ import annotations

from urllib.parse import urlsplit

DEFAULT_SCHEME = "https"


def normalize_url(target: str) -> str:
    """Turn a user-supplied target into a URL with a scheme.

    ``telemetry.lightpanda.io:443`` -> ``https://telemetry.lightpanda.io:443/``;
    ``example.com/login?a=1`` -> ``https://example.com/login?a=1``; anything that already
    has a scheme is returned unchanged (trailing slash added for a bare host).

    Why it matters: a scheme-less target is what the user types, and Lightpanda/node fetch
    interpret it as a relative or default URL — the run then produces one unexpected request
    instead of the page, and Proxy history stays empty.
    """
    value = (target or "").strip()
    if not value:
        return value

    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https", "ws", "wss"} and parsed.netloc:
        return value

    # `host:port` splits as scheme="host" / path="port": that is not a scheme we know, so the
    # whole string is the authority.
    if parsed.scheme and parsed.scheme not in {"http", "https", "ws", "wss"} and not value.startswith("//"):
        return f"{DEFAULT_SCHEME}://{value.rstrip('/')}/"

    if value.startswith("//"):
        return f"{DEFAULT_SCHEME}:{value}"

    return f"{DEFAULT_SCHEME}://{value}"
