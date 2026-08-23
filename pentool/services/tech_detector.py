"""Technology stack detector — identifies backend language, framework, CMS and DB from HTTP response.

Caches results per host to avoid redundant requests. Used by scanner and
crawler to feed AI with context for better check selection and endpoint
suggestion.
"""

from __future__ import annotations

import re
from typing import Any

_TECH_CACHE: dict[str, dict[str, Any]] = {}


def _clear_cache() -> None:
    _TECH_CACHE.clear()


def get_cached_tech(url: str) -> dict[str, Any] | None:
    """Return cached tech profile for the given URL's host, or None."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or url
    return _TECH_CACHE.get(host)


async def detect_tech(url: str, force: bool = False) -> dict[str, Any]:
    """Detect technology stack for the given URL.

    Returns a dict with keys:
        language: str | None — PHP, Python, Java, C#, Ruby, JS/Node, Go, Rust, Perl, Unknown
        framework: str | None — Laravel, Symfony, Django, Flask, Spring, ASP.NET, Rails, Express, Gin, Actix, Catalyst, None
        cms: str | None — WordPress, Drupal, Joomla, Magento, Shopify, Wix, Squarespace, None
        database: str | None — MySQL, PostgreSQL, SQLite, MSSQL, Oracle, MongoDB, None
        server: str | None — nginx, apache, iis, caddy, None
        details: dict — raw signals found in headers/html

    Results are cached per host. Set force=True to re-detect.
    """
    from urllib.parse import urlparse
    host = urlparse(url).hostname or url
    if not force and host in _TECH_CACHE:
        return _TECH_CACHE[host]

    import aiohttp
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {"User-Agent": "Mozilla/5.0 Pentool TechDetector/1.0"}
    signals: dict[str, Any] = {"headers": {}, "html": [], "cookies": []}

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, ssl=False) as resp:
                signals["status"] = resp.status
                # Collect response headers
                for k, v in resp.headers.items():
                    signals["headers"][k.lower()] = v
                # Collect Set-Cookie values
                for c in resp.headers.getall("set-cookie", []):
                    signals["cookies"].append(c)
                # Read first 100KB of body
                body = await resp.content.read(1024 * 100)
                text = body.decode("utf-8", errors="replace")
    except Exception:
        _TECH_CACHE[host] = {"language": None, "framework": None, "cms": None, "database": None, "server": None, "details": signals}
        return _TECH_CACHE[host]

    # --- Detect signals ---
    h = signals["headers"]
    server = h.get("server", h.get("via", "")).lower() or None
    powered = h.get("x-powered-by", "").lower()
    generator = ""
    for m in re.finditer(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', text, re.I):
        generator = m.group(1).lower()

    # --- Language ---
    language = None
    if "php" in powered or "php" in server or re.search(r'\.php[?\s#]', text, re.I):
        language = "PHP"
    elif "asp.net" in powered or "asp.net" in server or "aspx" in text.lower():
        language = "C#"
    elif "java" in powered.lower() or "jsessionid" in text.lower() or "servlet" in text.lower():
        language = "Java"
    elif "python" in powered or "django" in powered or "flask" in powered:
        language = "Python"
    elif "ruby" in powered or "rails" in powered or "passenger" in server:
        language = "Ruby"
    elif "node" in powered or "express" in powered.lower():
        language = "JS/Node"
    elif "go" in server or "gin" in powered:
        language = "Go"
    elif "rust" in server or "actix" in server:
        language = "Rust"
    elif "perl" in powered or "catalyst" in powered:
        language = "Perl"
    elif "nginx" in server or "apache" in server or "iis" in server:
        language = "Unknown"

    # --- Framework ---
    framework = None
    if "laravel" in powered.lower() or "laravel" in text.lower():
        framework = "Laravel"
    elif "symfony" in powered.lower() or "symfony" in text.lower():
        framework = "Symfony"
    elif "django" in powered.lower() or "csrftoken" in text.lower():
        framework = "Django"
    elif "flask" in powered.lower():
        framework = "Flask"
    elif "spring" in text.lower() or "spring" in powered.lower():
        framework = "Spring"
    elif ".net" in server or ".net" in powered.lower():
        framework = "ASP.NET"
    elif "ruby on rails" in text.lower() or "rails" in powered.lower():
        framework = "Rails"
    elif "express" in text.lower():
        framework = "Express"
    elif "gin" in powered.lower():
        framework = "Gin"
    elif "actix" in server:
        framework = "Actix"

    # --- CMS ---
    cms = None
    if "wordpress" in generator or "wp-content" in text or "wp-json" in text:
        cms = "WordPress"
    elif "drupal" in generator or "drupal" in text.lower():
        cms = "Drupal"
    elif "joomla" in generator or "joomla" in text.lower():
        cms = "Joomla"
    elif "magento" in generator or "mage" in text.lower():
        cms = "Magento"
    elif "shopify" in text.lower() or "myshopify" in text.lower():
        cms = "Shopify"
    elif "wix" in text.lower() and "wix" in server:
        cms = "Wix"
    elif "squarespace" in text.lower():
        cms = "Squarespace"

    # --- Database ---
    database = None
    if "mysql" in text.lower() or "maria" in text.lower():
        database = "MySQL"
    elif "postgres" in text.lower() or "pgsql" in text.lower():
        database = "PostgreSQL"
    elif "sqlite" in text.lower():
        database = "SQLite"
    elif "microsoft" in server or "mssql" in text.lower() or "sql server" in text.lower():
        database = "MSSQL"
    elif "oracle" in text.lower() or "oracle" in server:
        database = "Oracle"
    elif "mongodb" in text.lower() or "mongo" in text.lower():
        database = "MongoDB"

    # --- Scripts / SPA detection ---
    spa = None
    if "react" in text.lower() and "react" in text[:100000].lower():
        spa = "React"
    elif "vue" in text.lower() and "vue" in text[:100000].lower():
        spa = "Vue"
    elif "angular" in text.lower() and "angular" in text[:100000].lower():
        spa = "Angular"
    elif "next" in text.lower() and ("_next" in text or "next.js" in text.lower()):
        spa = "Next.js"
    elif "nuxt" in text.lower():
        spa = "Nuxt"

    profile = {
        "language": language,
        "framework": framework,
        "cms": cms,
        "database": database,
        "server": server,
        "spa": spa,
        "generator": generator or None,
        "details": {
            "status": signals.get("status"),
            "powered_by": powered or None,
            "server_header": server,
            "cookies": signals["cookies"][:5],
            "has_forms": bool(re.search(r'<form[> ]', text, re.I)),
            "has_api": bool(re.search(r'/api/', text, re.I)) or bool(re.search(r'application/json', text, re.I)),
        },
    }

    _TECH_CACHE[host] = profile
    return profile