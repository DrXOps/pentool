"""Technology stack detector — identifies backend language, framework, CMS, DB, WAF, security headers.

Caches results per host with TTL to avoid redundant requests. Used by scanner
and crawler to feed AI with context for better check selection and endpoint
suggestion.

Detection strategies:
1. HTTP GET — parse headers + body (basic)
2. JS rendering (optional) — headless Chromium via SpiderAPI for SPA apps
3. GraphQL introspection probe — POST /graphql with schema query
4. WordPress version probe — GET /wp-json/wp/v2/ or /readme.html
"""

from __future__ import annotations

import re
import time
from typing import Any

# Cache TTL in seconds (4 hours)
_CACHE_TTL: float = 14400.0
_TECH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}  # host -> (timestamp, profile)


def _clear_cache() -> None:
    _TECH_CACHE.clear()


def get_cached_tech(url: str) -> dict[str, Any] | None:
    """Return cached tech profile for the given URL's host, or None if expired/missing."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or url
    entry = _TECH_CACHE.get(host)
    if entry is None:
        return None
    ts, profile = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _TECH_CACHE[host]
        return None
    return profile


def _cache_set(host: str, profile: dict[str, Any]) -> None:
    _TECH_CACHE[host] = (time.monotonic(), profile)


# ── WAF signatures ──────────────────────────────────────────────────────────
_WAF_SIGNATURES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'cloudflare|ray\s*id:', re.I), "Cloudflare"),
    (re.compile(r'sucuri|cloudproxy', re.I), "Sucuri"),
    (re.compile(r'akamaighost|akamai', re.I), "Akamai"),
    (re.compile(r'incapsula|imperva', re.I), "Imperva / Incapsula"),
    (re.compile(r'f5\s*bigip|big-ip|ts\w{5,}=', re.I), "F5 BIG-IP ASM"),
    (re.compile(r'mod_security|modsecurity', re.I), "ModSecurity"),
    (re.compile(r'aws.*waf|awswaf|aws-waf', re.I), "AWS WAF"),
    (re.compile(r'barracuda', re.I), "Barracuda WAF"),
    (re.compile(r'fortinet|fortiweb', re.I), "Fortinet FortiWeb"),
    (re.compile(r'comodo.*waf|cwatch', re.I), "Comodo WAF"),
    (re.compile(r'sitelock|site_lock', re.I), "SiteLock"),
    (re.compile(r'stackpath', re.I), "StackPath"),
    (re.compile(r'azure.*waf|appgw', re.I), "Azure WAF"),
    (re.compile(r'x-sucuri|x-sucuri-id', re.I), "Sucuri CloudProxy"),
    (re.compile(r'cf-ray', re.I), "Cloudflare"),
]

# ── Security header checks ──────────────────────────────────────────────────
_SECURITY_HEADERS = [
    "content-security-policy",
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy",
    "access-control-allow-origin",
]


async def detect_tech(url: str, force: bool = False, js_render: bool = False) -> dict[str, Any]:
    """Detect technology stack for the given URL.

    Args:
        url: Target URL.
        force: Re-detect even if cached.
        js_render: Enable headless JS rendering (Lightpanda) for SPA detection.

    Returns a dict with keys:
        language, framework, cms, database, server, spa, waf, waf_name,
        graphql, wp_version, security_headers, details.
    """
    from urllib.parse import urlparse
    host = urlparse(url).hostname or url
    if not force:
        cached = get_cached_tech(url)
        if cached is not None:
            return cached

    import aiohttp
    timeout = aiohttp.ClientTimeout(total=10)
    req_headers = {"User-Agent": "Mozilla/5.0 Pentool TechDetector/1.0"}
    signals: dict[str, Any] = {"headers": {}, "html": [], "cookies": []}

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=req_headers, ssl=False) as resp:
                signals["status"] = resp.status
                for k, v in resp.headers.items():
                    signals["headers"][k.lower()] = v
                for c in resp.headers.getall("set-cookie", []):
                    signals["cookies"].append(c)
                body = await resp.content.read(1024 * 100)
                text = body.decode("utf-8", errors="replace")
    except Exception:
        empty = _make_profile(signals, {}, "")
        _cache_set(host, empty)
        return empty

    h = signals["headers"]
    server_raw = h.get("server", h.get("via", "")).lower() or ""
    powered = h.get("x-powered-by", "").lower()
    generator = ""
    for m in re.finditer(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', text, re.I):
        generator = m.group(1).lower()

    profile = _make_profile(signals, h, text, server_raw, powered, generator)

    # ── JS rendering probe (optional) ──
    if js_render and profile.get("spa"):
        try:
            rendered = await _js_render_probe(url)
            if rendered:
                profile["details"]["js_rendered"] = True
                text = rendered  # use rendered HTML for deeper analysis
        except Exception:
            pass

    # ── WordPress version probe ──
    if profile.get("cms") == "WordPress":
        wp_ver = await _probe_wp_version(url)
        if wp_ver:
            profile["wp_version"] = wp_ver
            profile["details"]["wp_version_source"] = wp_ver

    # ── GraphQL introspection probe ──
    gql = await _probe_graphql(url)
    if gql:
        profile["graphql"] = gql

    _cache_set(host, profile)
    return profile


def _make_profile(
    signals: dict, h: dict, text: str,
    server_raw: str = "", powered: str = "", generator: str = "",
) -> dict[str, Any]:
    """Build the full tech profile from raw signals."""
    server = server_raw or h.get("server", h.get("via", "")).lower() or None

    # --- WAF detection ---
    waf_name = _detect_waf(h, text)
    waf = waf_name is not None

    # --- Security headers ---
    sec_hdrs: dict[str, str] = {}
    for sh in _SECURITY_HEADERS:
        val = h.get(sh)
        if val:
            sec_hdrs[sh] = val

    # --- Language ---
    language = None
    if "php" in powered or "php" in server_raw or re.search(r'\.php[?\s#]', text, re.I):
        language = "PHP"
    elif "asp.net" in powered or "asp.net" in server_raw or "aspx" in text.lower():
        language = "C#"
    elif "java" in powered or "jsessionid" in text.lower() or "servlet" in text.lower():
        language = "Java"
    elif "python" in powered or "django" in powered or "flask" in powered:
        language = "Python"
    elif "ruby" in powered or "rails" in powered or "passenger" in server_raw:
        language = "Ruby"
    elif "node" in powered or "express" in powered.lower():
        language = "JS/Node"
    elif "go" in server_raw or "gin" in powered:
        language = "Go"
    elif "rust" in server_raw or "actix" in server_raw:
        language = "Rust"
    elif "perl" in powered or "catalyst" in powered:
        language = "Perl"
    elif server_raw and ("nginx" in server_raw or "apache" in server_raw or "iis" in server_raw):
        language = "Unknown"

    # --- Framework ---
    framework = None
    tc = text.lower()
    if "laravel" in powered or "laravel" in tc:
        framework = "Laravel"
    elif "symfony" in powered or "symfony" in tc:
        framework = "Symfony"
    elif "django" in powered or "csrftoken" in tc:
        framework = "Django"
    elif "flask" in powered:
        framework = "Flask"
    elif "spring" in tc or "spring" in powered:
        framework = "Spring"
    elif ".net" in server_raw or ".net" in powered:
        framework = "ASP.NET"
    elif "ruby on rails" in tc or "rails" in powered:
        framework = "Rails"
    elif "express" in tc:
        framework = "Express"
    elif "gin" in powered:
        framework = "Gin"
    elif "actix" in server_raw:
        framework = "Actix"

    # --- CMS ---
    cms = None
    if "wordpress" in generator or "wp-content" in text or "wp-json" in text:
        cms = "WordPress"
    elif "drupal" in generator or "drupal" in tc:
        cms = "Drupal"
    elif "joomla" in generator or "joomla" in tc:
        cms = "Joomla"
    elif "magento" in generator or "mage" in tc:
        cms = "Magento"
    elif "shopify" in tc or "myshopify" in tc:
        cms = "Shopify"
    elif "wix" in tc and "wix" in server_raw:
        cms = "Wix"
    elif "squarespace" in tc:
        cms = "Squarespace"

    # --- Database ---
    database = None
    if "mysql" in tc or "maria" in tc:
        database = "MySQL"
    elif "postgres" in tc or "pgsql" in tc:
        database = "PostgreSQL"
    elif "sqlite" in tc:
        database = "SQLite"
    elif "microsoft" in server_raw or "mssql" in tc or "sql server" in tc:
        database = "MSSQL"
    elif "oracle" in tc or "oracle" in server_raw:
        database = "Oracle"
    elif "mongodb" in tc or "mongo" in tc:
        database = "MongoDB"

    # --- SPA detection ---
    spa = None
    if "react" in tc and "react" in tc:
        spa = "React"
    elif "vue" in tc and "vue" in tc:
        spa = "Vue"
    elif "angular" in tc and "angular" in tc:
        spa = "Angular"
    elif "next" in tc and ("_next" in text or "next.js" in tc):
        spa = "Next.js"
    elif "nuxt" in tc:
        spa = "Nuxt"

    return {
        "language": language,
        "framework": framework,
        "cms": cms,
        "database": database,
        "server": server,
        "spa": spa,
        "waf": waf,
        "waf_name": waf_name,
        "graphql": None,
        "wp_version": None,
        "generator": generator or None,
        "security_headers": sec_hdrs,
        "details": {
            "status": signals.get("status"),
            "powered_by": powered or None,
            "server_header": server,
            "cookies": signals.get("cookies", [])[:5],
            "has_forms": bool(re.search(r'<form[> ]', text, re.I)),
            "has_api": bool(re.search(r'/api/', text, re.I)) or bool(re.search(r'application/json', text, re.I)),
            "has_csp": "content-security-policy" in h,
            "has_hsts": "strict-transport-security" in h,
            "js_rendered": False,
        },
    }


def _detect_waf(headers: dict[str, str], body: str) -> str | None:
    """Detect WAF from response headers and body."""
    for pattern, name in _WAF_SIGNATURES:
        for k, v in headers.items():
            if pattern.search(f"{k}: {v}"):
                return name
        if pattern.search(body):
            return name
    # Check for WAF block page indicators
    block_indicators = [
        (r'attention required!|cloudflare.*block', "Cloudflare (blocked)"),
        (r'incapsula.*block|blocked.*incapsula', "Imperva / Incapsula (blocked)"),
        (r'reference.*#[0-9a-f]{8,}', "Generic WAF (blocked)"),
        (r'your request has been blocked', "Generic WAF (blocked)"),
    ]
    for pattern, name in block_indicators:
        if re.search(pattern, body, re.I):
            return name
    return None


async def _probe_wp_version(url: str) -> str | None:
    """Detect WordPress version via wp-json or readme.html."""
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {"User-Agent": "Pentool TechDetector/1.0"}

    # Try /wp-json/wp/v2/
    try:
        api_url = url.rstrip("/") + "/wp-json/wp/v2/"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ver = data.get("namespaces") or data.get("routes", {}).keys()
                    if ver:
                        return f"WP API ({list(ver)[:3]})"
    except Exception:
        pass

    # Try /readme.html
    try:
        readme_url = url.rstrip("/") + "/readme.html"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(readme_url, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    body = await resp.text()
                    m = re.search(r'WordPress\s*([\d.]+)', body)
                    if m:
                        return m.group(1)
    except Exception:
        pass

    return None


async def _probe_graphql(url: str) -> bool:
    """Check if the target has a publicly accessible GraphQL endpoint."""
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {"User-Agent": "Pentool TechDetector/1.0", "Content-Type": "application/json"}
    query = {"query": "{__schema{types{name}}}"}

    gql_paths = ["/graphql", "/api/graphql", "/gql", "/query"]
    for path in gql_paths:
        try:
            gql_url = url.rstrip("/") + path
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(gql_url, json=query, headers=headers, ssl=False) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and data.get("data", {}).get("__schema"):
                            return True
        except Exception:
            continue
    return False


async def _js_render_probe(url: str) -> str | None:
    """Render page and return the post-JS HTML if the target is an SPA.

    Uses Lightpanda (preferred) for a cheap JS render; falls back to the old
    Playwright crawl path only when Lightpanda is unavailable.
    """
    try:
        from pentool.utils.lightpanda import is_lightpanda_available, lightpanda_fetch_html
        if is_lightpanda_available():
            html = await lightpanda_fetch_html(url, timeout=20.0)
            if html:
                return html
    except Exception:
        pass
    try:
        from pentool.api.spider_api import SpiderAPI, SpiderConfig
        spider = SpiderAPI(config=SpiderConfig(js_render=True))
        result = await spider.crawl(url, max_pages=1)
        if result and result.pages:
            return result.pages[0] if isinstance(result.pages[0], str) else None
    except Exception:
        pass
    return None