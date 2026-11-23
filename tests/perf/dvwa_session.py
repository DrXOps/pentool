"""Log in to the test DVWA instance (http://dvwa.local:7474) and collect Cookie headers.

Needed for Level C load runs, where the engines (Scanner/Intruder/Spider)
must reach a live DVWA with a valid session — otherwise DVWA will send a blue
redirect to /login.php and the scanner/spider will find 0 pages.

DVWA (classic) uses a CSRF token on the login form: `user_token`
is present on /login.php as a hidden field and changes on every page
load. So a simple POST with a single user_token does not work: you must
 1) GET /login.php  → take PHPSESSID from Set-Cookie and user_token from HTML;
 2) POST /login.php with username/password/Login/user_token and Cookie: PHPSESSID;
 3) GET /index.php with the Cookie → check that it is NOT a redirect to login.php;
 4) assemble the header {"Cookie": "PHPSESSID=<id>; security=low"}.

Uses the same HTTPClient as the engines (pentool.utils.http_client), so the
network stack is uniform. The pure functions (extract_headers_from_set_cookie,
extract_user_token) are split out — they can be unit-tested without network.

Example:
    from tests.perf.dvwa_session import build_session_headers
    headers = await build_session_headers()   # async
    # -> {"Cookie": "PHPSESSID=…; security=low"}
"""

from __future__ import annotations

import re
import time
from typing import Optional

DVWA_URL = "http://dvwa.local:7474"
DVWA_LOGIN = DVWA_URL + "/login.php"
DVWA_INDEX = DVWA_URL + "/index.php"
DVWA_CREDS = {"username": "admin", "password": "password"}

# After login we want 'security' low → set the cookie explicitly and use it.
# (Some versions do not treat it as a separate form parameter.)
_SECURITY = "low"

# Process-wide session cache: {key: (expiry_ts, headers)}.
_SESSION_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_CACHE_TTL = 60.0  # sec


def _make_cache_key(url: str, username: str) -> str:
    return f"{url}|{username}"


def extract_user_token(html: str) -> Optional[str]:
    """Pull user_token out of the DVWA login form HTML (no network).

    We look for <input type='hidden' name='user_token' value='…'>. Return None
    if the token is absent (the page may look different — then either login
    is not needed, or the markup has changed).
    """
    m = re.search(
        r"name=[\"']user_token[\"'][^>]*value=[\"']([0-9a-fA-F]{32})[\"']",
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    # The browser-common attribute order puts value before name; DVWA is fixed,
    # but we handle the reverse order too for robustness.
    m2 = re.search(
        r"value=[\"']([0-9a-fA-F]{32})[\"'][^>]*name=[\"']user_token[\"']",
        html,
        re.IGNORECASE,
    )
    return m2.group(1) if m2 else None


def extract_phpsessid(set_cookie: object) -> Optional[str]:
    """Extract PHPSESSID from a Set-Cookie value (a string or a list of headers).

    Accepts either a single string 'PHPSESSID=x; path=/_…' or the value
    from aiohttp dict headers (list[str] when duplicated).
    """
    if isinstance(set_cookie, list):
        for part in set_cookie:
            sid = _phpsessid_from_str(part)
            if sid:
                return sid
        return None
    return _phpsessid_from_str(str(set_cookie))


def _phpsessid_from_str(cookie_str: str) -> Optional[str]:
    m = re.search(r"(?:^|;\s*)PHPSESSID=([0-9a-zA-Z]+)", cookie_str)
    return m.group(1) if m else None


async def build_session_headers(
    *,
    url: str = DVWA_URL,
    username: str = DVWA_CREDS["username"],
    password: str = DVWA_CREDS["password"],
    use_cache: bool = True,
    http_client=None,
) -> dict[str, str]:
    """Get Cookie headers for a valid DVWA session (async).

    Returns {"Cookie": "PHPSESSID=…; security=low"}. On repeated calls
    within a single process it returns the cached session (use_cache=True)
    until the TTL expires.
    """
    if use_cache:
        cache_key = _make_cache_key(url, username)
        hit = _SESSION_CACHE.get(cache_key)
        if hit and hit[0] > time.monotonic():
            return hit[1]

    owns_client = http_client is None
    if http_client is None:
        from pentool.utils.http_client import HTTPClient

        http_client = HTTPClient(verify_ssl=False)

    try:
        final_headers = await _do_login(http_client, url, username, password)
    finally:
        if owns_client:
            try:
                await http_client.close()
            except Exception:
                pass

    if use_cache:
        _SESSION_CACHE[_make_cache_key(url, username)] = (
            time.monotonic() + _CACHE_TTL,
            final_headers,
        )
    return final_headers


async def _do_login(http_client, url: str, username: str, password: str) -> dict[str, str]:
    """Internal login on top of the passed-in http_client (without owning it)."""
    login_url = url + "/login.php"
    index_url = url + "/index.php"

    # ── 1) GET /login.php: PHPSESSID from Set-Cookie + user_token from HTML ─
    login_resp = await http_client.send(_req("GET", login_url))
    if login_resp.status not in (200, 302):
        raise RuntimeError(f"DVWA login GET: status {login_resp.status}")

    phpsessid = extract_phpsessid(login_resp.headers.get("Set-Cookie"))
    user_token = extract_user_token(login_resp.body or "")

    # The token/session may be absent if we are already logged in (redirect to index).
    if phpsessid is None:
        # Try without it — maybe a session already exists or the site has no CSRF.
        phpsessid = ""

    cookie_header = f"PHPSESSID={phpsessid}; security={_SECURITY}"

    # ── 2) POST /login.php with user_token ─────────────────────────────────
    fields: dict[str, str] = {
        "username": username,
        "password": password,
        "Login": "Login",
    }
    if user_token:
        fields["user_token"] = user_token
    body = "&".join(f"{k}={_urlenc(v)}" for k, v in fields.items())
    post_resp = await http_client.send(
        _req(
            "POST",
            login_url,
            cookie_header,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )

    # In case PHPSESSID was refreshed after login — re-read it.
    new_sid = extract_phpsessid(post_resp.headers.get("Set-Cookie"))
    if new_sid:
        phpsessid = new_sid
        cookie_header = f"PHPSESSID={phpsessid}; security={_SECURITY}"

    # ── 3) Confirmation on /index.php ──────────────────────────────────────
    index_resp = await http_client.send(_req("GET", index_url, cookie_header))
    final_headers = {"Cookie": cookie_header}
    if index_resp.status in (301, 302, 303):
        # Redirect to login.php → the session did not take
        loc = index_resp.headers.get("Location", "")
        if "login" in loc.lower():
            raise RuntimeError("DVWA авторизация не прошла: редирект на login.php")
    if index_resp.status not in (200, 301, 302, 303):
        raise RuntimeError(f"DVWA index: status {index_resp.status}")

    return final_headers


def _req(method: str, url: str, cookie: str = "", body: str = "", headers: dict[str, str] | None = None) -> object:
    from pentool.utils.parser import ParsedRequest

    h: dict[str, str] = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    return ParsedRequest(method=method, url=url, headers=h, body=body)


def _urlenc(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(value)
