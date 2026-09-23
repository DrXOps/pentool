"""Generic session-login helper for the crawler/scanner.

Vendored out of tests/perf/dvwa_session.py so production code can establish a
cookie session against a classic CSRF-protected login form (e.g. DVWA) instead
of being limited to static Cookie headers pasted by the user.

Flow (must be one round-trip-friendly):
  1. GET the login URL -> read PHPSESSID (Set-Cookie) + user_token (hidden CSRF)
  2. POST creds + user_token with the same cookie jar
  3. GET an index/app URL at the same host; if it still redirects to login the
     auth failed -> raise.

Reuses the same HTTPClient stack as the scan engines for a single network stack.
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote_plus
from typing import Optional

__all__ = [
    "extract_user_token",
    "extract_phpsessid",
    "build_session_headers",
]

# Session cache: {key: (expiry_ts, headers)} shared process-wide so repeated
# auth (e.g. one login per crawl run) doesn't resubmit creds every request.
_SESSION_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_CACHE_TTL = 60.0  # sec


def _cache_key(url: str, username: str) -> str:
    return f"{url}|{username}"


def extract_user_token(html: str) -> Optional[str]:
    """Pull a hidden `user_token` CSRF field out of an HTML login form.

    Accepts either attribute order (`name=... value=...` or `value=... name=...`).
    Returns None when absent (no CSRF / a different form shape).
    """
    m = re.search(
        r"name=[\"']user_token[\"'][^>]*value=[\"']([0-9a-fA-F]{32})[\"']",
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m2 = re.search(
        r"value=[\"']([0-9a-fA-F]{32})[\"'][^>]*name=[\"']user_token[\"']",
        html,
        re.IGNORECASE,
    )
    return m2.group(1) if m2 else None


def extract_phpsessid(set_cookie: object) -> Optional[str]:
    """Extract `PHPSESSID` from a Set-Cookie value (string or list).

    Accepts a single `'PHPSESSID=x; path=/...'` string OR a list (the shape
    aiohttp gives for duplicated Set-Cookie headers).
    """
    if isinstance(set_cookie, list):
        for part in set_cookie:
            sid = _phpsessid_from_str(str(part))
            if sid:
                return sid
        return None
    return _phpsessid_from_str(str(set_cookie))


def _phpsessid_from_str(cookie_str: str) -> Optional[str]:
    m = re.search(r"(?:^|;\s*)PHPSESSID=([0-9a-zA-Z]+)", cookie_str)
    return m.group(1) if m else None


async def build_session_headers(
    *,
    url: str,
    username: str,
    password: str,
    login_path: str = "/login.php",
    app_path: str = "/index.php",
    extra_cookie_fragment: str = "",
    use_cache: bool = True,
    http_client=None,
) -> dict[str, str]:
    """Establish a logged-in Cookie header for a CSRF-protected app.

    Returns `{"Cookie": "PHPSESSID=...; ..."}` (plus any `extra_cookie_fragment`,
    e.g. DVWA's `security=low`). Raises RuntimeError if login doesn't stick.
    Uses a process cache (default) so repeated calls reuse the live session.
    """
    if use_cache:
        ck = _cache_key(url, username)
        hit = _SESSION_CACHE.get(ck)
        if hit and hit[0] > time.monotonic():
            return hit[1]

    owns_client = http_client is None
    if http_client is None:
        from pentool.utils.http_client import HTTPClient
        http_client = HTTPClient(verify_ssl=False)

    try:
        final_headers = await _do_login(
            http_client, url, username, password, login_path, app_path, extra_cookie_fragment,
        )
    finally:
        if owns_client:
            try:
                await http_client.close()
            except Exception:
                pass

    if use_cache:
        _SESSION_CACHE[_cache_key(url, username)] = (time.monotonic() + _CACHE_TTL, final_headers)
    return final_headers


async def _do_login(
    http_client,
    url: str,
    username: str,
    password: str,
    login_path: str,
    app_path: str,
    extra_cookie_fragment: str,
) -> dict[str, str]:
    """Internal login over a caller-provided http_client (does not own it)."""
    login_url = url + login_path
    index_url = url + app_path

    # 1) GET login -> PHPSESSID (Set-Cookie) + CSRF user_token (HTML).
    login_resp = await http_client.send(_req("GET", login_url))
    if login_resp.status not in (200, 302):
        raise RuntimeError(f"login GET {login_url}: status {login_resp.status}")

    phpsessid = extract_phpsessid(login_resp.headers.get("Set-Cookie")) or ""
    user_token = extract_user_token(login_resp.body or "")

    cookie_fragment = f"PHPSESSID={phpsessid}" if phpsessid else ""
    if extra_cookie_fragment:
        cookie_fragment = "; ".join(x for x in (cookie_fragment, extra_cookie_fragment) if x)

    # 2) POST creds + user_token with the session cookie.
    fields: dict[str, str] = {"username": username, "password": password, "Login": "Login"}
    if user_token:
        fields["user_token"] = user_token
    body = "&".join(f"{k}={quote_plus(str(v))}" for k, v in fields.items())
    post_resp = await http_client.send(_req(
        "POST", login_url, cookie_fragment, body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ))

    # Session id may rotate after POST -> re-read it.
    new_sid = extract_phpsessid(post_resp.headers.get("Set-Cookie"))
    if new_sid:
        phpsessid = new_sid
        cookie_fragment = f"PHPSESSID={phpsessid}"
        if extra_cookie_fragment:
            cookie_fragment = "; ".join([cookie_fragment, extra_cookie_fragment])

    # 3) Confirm on the app page that we are NOT redirected back to login.
    index_resp = await http_client.send(_req("GET", index_url, cookie_fragment))
    final_cookie = {"Cookie": cookie_fragment}
    if index_resp.status in (301, 302, 303):
        loc = index_resp.headers.get("Location", "")
        if "login" in loc.lower():
            raise RuntimeError(f"auth failed: redirected to {loc}")
    if index_resp.status not in (200, 301, 302, 303):
        raise RuntimeError(f"app {index_url}: unexpected status {index_resp.status}")
    return final_cookie


def _req(method: str, url: str, cookie: str = "", body: str = "",
         headers: dict[str, str] | None = None) -> object:
    from pentool.utils.parser import ParsedRequest

    h: dict[str, str] = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    return ParsedRequest(method=method, url=url, headers=h, body=body)
