"""Авторизация в тестовый DVWA (http://dvwa.local:7474) и сбор Cookie-заголовков.

Нужен для нагрузочных прогонов Уровня C, где движки (Scanner/Intruder/Spider)
должны ходить на живой DVWA с действительной сессией — иначе DVWA синим
редиректом отправит на /login.php, и сканер/спайдер найдут 0 страниц.

DVWA (классическая) использует CSRF-токен на форме логина: `user_token`
присутствует на /login.php как скрытое поле и меняется на каждую загрузку
страницы. Поэтому простой POST с одним user_token не работает: надо
 1) GET /login.php  → взять PHPSESSID из Set-Cookie и user_token из HTML;
 2) POST /login.php c username/password/Login/user_token и Cookie: PHPSESSID;
 3) GET /index.php с Cookie → проверить, что НЕ редирект на login.php;
 4) собрать заголовок {"Cookie": "PHPSESSID=<id>; security=low"}.

Использует тот же HTTPClient, что и движки (pentool.utils.http_client), чтобы
стек сети был единым. Чистые функции (extract_headers_from_set_cookie,
extract_user_token) выделены отдельно — их можно юнит-тестить без сети.

Пример:
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

# Post-логин 'security' желаем low → ставим куку явно и используем её.
# (Некоторых версий не заботятся об этом как отдельном параметре формы.)
_SECURITY = "low"

# Кеш сессии процесса: {key: (expiry_ts, headers)}.
_SESSION_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_CACHE_TTL = 60.0  # сек


def _make_cache_key(url: str, username: str) -> str:
    return f"{url}|{username}"


def extract_user_token(html: str) -> Optional[str]:
    """Вытащить user_token из HTML формы логина DVWA (без сети).

    Ищем <input type='hidden' name='user_token' value='…'>. Возвращаем None,
    если токен отсутствует (страница может выглядеть иначе — тогда авторизация
    либо не нужна, либо формула поменялась).
    """
    m = re.search(
        r"name=[\"']user_token[\"'][^>]*value=[\"']([0-9a-fA-F]{32})[\"']",
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    # Распространён браузерный порядок атрибутов value перед name? УDVWA фиксирован,
    # но обработаем и обратный порядок для устойчивости.
    m2 = re.search(
        r"value=[\"']([0-9a-fA-F]{32})[\"'][^>]*name=[\"']user_token[\"']",
        html,
        re.IGNORECASE,
    )
    return m2.group(1) if m2 else None


def extract_phpsessid(set_cookie: object) -> Optional[str]:
    """Извлечь PHPSESSID из значения Set-Cookie (строка или список заголовков).

    Принимает либо одиночную строку 'PHPSESSID=x; path=/_…', либо значение
    из dict-заголовков aiohttp (list[str] при дубликатах).
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
    """Получить Cookie-заголовки для действующей сессии DVWA (async).

    Возвращает {"Cookie": "PHPSESSID=…; security=low"}. При повторных вызовах
    в рамках одного процесса возвращает закешированную сессию (use_cache=True)
    до истечения TTL.
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
            time.monotonic() + _CACHE_TTL, final_headers,
        )
    return final_headers


async def _do_login(http_client, url: str, username: str,
                    password: str) -> dict[str, str]:
    """Внутренняя авторизация поверх переданного http_client (без владения им)."""
    login_url = url + "/login.php"
    index_url = url + "/index.php"

    # ── 1) GET /login.php: PHPSESSID из Set-Cookie + user_token из HTML ────
    login_resp = await http_client.send(
        _req("GET", login_url)
    )
    if login_resp.status not in (200, 302):
        raise RuntimeError(f"DVWA login GET: status {login_resp.status}")

    phpsessid = extract_phpsessid(login_resp.headers.get("Set-Cookie"))
    user_token = extract_user_token(login_resp.body or "")

    # Токен/сессия могут отсутствовать, если уже залогинены (редирект на index).
    if phpsessid is None:
        # Попробуем без него — вдруг уже есть сессия или сайт без CSRF.
        phpsessid = ""

    cookie_header = f"PHPSESSID={phpsessid}; security={_SECURITY}"

    # ── 2) POST /login.php с user_token ────────────────────────────────────
    fields: dict[str, str] = {
        "username": username,
        "password": password,
        "Login": "Login",
    }
    if user_token:
        fields["user_token"] = user_token
    body = "&".join(f"{k}={_urlenc(v)}" for k, v in fields.items())
    post_resp = await http_client.send(_req(
        "POST", login_url, cookie_header, body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ))

    # На случай, если после логина PHPSESSID обновился — перечитаем.
    new_sid = extract_phpsessid(post_resp.headers.get("Set-Cookie"))
    if new_sid:
        phpsessid = new_sid
        cookie_header = f"PHPSESSID={phpsessid}; security={_SECURITY}"

    # ── 3) Подтверждение на /index.php ─────────────────────────────────────
    index_resp = await http_client.send(_req("GET", index_url, cookie_header))
    final_headers = {"Cookie": cookie_header}
    if index_resp.status in (301, 302, 303):
        # Редирект на login.php → сессия не прошла
        loc = index_resp.headers.get("Location", "")
        if "login" in loc.lower():
            raise RuntimeError("DVWA авторизация не прошла: редирект на login.php")
    if index_resp.status not in (200, 301, 302, 303):
        raise RuntimeError(f"DVWA index: status {index_resp.status}")

    return final_headers


def _req(method: str, url: str, cookie: str = "", body: str = "",
         headers: dict[str, str] | None = None) -> object:
    from pentool.utils.parser import ParsedRequest
    h: dict[str, str] = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    return ParsedRequest(method=method, url=url, headers=h, body=body)


def _urlenc(value: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(value)
