"""Scope-matching utility shared by Proxy and Spider.

Both modules used to implement their own "is this host in scope" check
independently (Proxy.is_in_scope / Spider._in_scope), with slightly
different semantics — Proxy stripped the `:port` suffix from both the
host and each configured pattern before comparing, Spider compared the
full `netloc` (host[:port]) as-is. Unified here so scope logic (and any
future scope feature, e.g. wildcard patterns) is implemented once instead
of twice, with one agreed-upon default: match by host name only, ignoring
port, in both Proxy and Spider.
"""

from __future__ import annotations


def host_in_scope(host: str, patterns: list[str], strip_port: bool = True) -> bool:
    """True if host matches any pattern (empty patterns = everything in scope). Supports *.wildcard."""
    if not patterns:
        return True
    h = host.lower()
    if strip_port:
        h = h.split(":")[0]
    for pattern in patterns:
        p = pattern.lower().strip()
        if not p:
            continue
        if strip_port:
            p = p.split(":")[0]
        if p.startswith("*."):
            suffix = p[1:]  # ".example.com"
            if h.endswith(suffix) or h == suffix[1:]:
                return True
        elif p == h:
            return True
    return False


def domain_in_scope(netloc: str, base_domain: str, strip_port: bool = True) -> bool:
    """Spider scope check: netloc equals base_domain or is subdomain (wrapper around host_in_scope)."""
    if not netloc:
        return True
    return host_in_scope(netloc, [base_domain, f"*.{base_domain}"], strip_port=strip_port)
