"""Shared helper for picking auth-related headers out of a request.

Used by both ScanService (crawling before an active scan, using the seed
request's own headers) and SpiderAPI (auto-discovering a session for a
target host from Proxy's HTTP History) so the set of "this looks like an
auth header" keys is defined once instead of twice.
"""

from __future__ import annotations

# Header names (lowercase) considered likely to carry session/auth state.
# Not an exhaustive list — just the common cases (cookie-based sessions,
# bearer/JWT tokens, common custom API-key header names).
AUTH_HEADER_KEYS: frozenset[str] = frozenset({
    "cookie", "authorization", "x-auth-token", "x-api-key",
    "x-access-token", "bearer", "session",
})


def extract_auth_headers(headers: dict) -> dict:
    """Return only the entries of `headers` that look auth-related.

    Case-insensitive on keys; the original casing of matched keys is
    preserved in the result (so it can be sent back out as-is).
    """
    if not headers:
        return {}
    return {
        k: v for k, v in headers.items()
        if k.lower() in AUTH_HEADER_KEYS
    }
