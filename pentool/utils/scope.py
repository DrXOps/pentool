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
    """Return True if `host` matches any of `patterns`.

    - Empty `patterns` means "no scope configured" -> everything is in
      scope (matches prior Proxy behavior).
    - Patterns support a `*.example.com` wildcard, which also matches the
      bare `example.com` itself (subdomain-or-exact), in addition to plain
      exact-match patterns.
    - strip_port: by default both `host` and each pattern have any
      `:port` suffix removed before comparing — this is the unified
      behavior Proxy already had. Pass `strip_port=False` for a
      port-sensitive match; reserved for a possible future "match port"
      toggle in the scope UI, not currently exposed anywhere.
    """
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
    """Spider-style scope check: `netloc` is in scope if it equals
    `base_domain` or is a subdomain of it.

    Thin wrapper around host_in_scope() expressed as two patterns (exact
    match + wildcard subdomain match) — kept as a separate function
    because Spider's call sites pass a URL's netloc plus a single crawl
    base_domain, not a user-configured pattern list like Proxy's.
    """
    if not netloc:
        return True
    return host_in_scope(netloc, [base_domain, f"*.{base_domain}"], strip_port=strip_port)
