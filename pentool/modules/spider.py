"""AsyncSpider — recursive site crawler."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse

from pentool.core.logging import get_logger
from pentool.utils.scope import domain_in_scope

logger = get_logger(__name__)


def is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False

# Regex to find API endpoints in JS
_JS_API_PATTERNS = [
    re.compile(r'["\'](/api/[^"\'?\s]{1,200})', re.IGNORECASE),
    re.compile(r'["\'](/v\d+/[^"\'?\s]{1,200})', re.IGNORECASE),
    re.compile(r'fetch\s*\(\s*["\']([^"\']{1,200})["\']', re.IGNORECASE),
    re.compile(r'axios\.[a-z]+\s*\(\s*["\']([^"\']{1,200})["\']', re.IGNORECASE),
    re.compile(r'url\s*[:=]\s*["\']([^"\']{4,200})["\']', re.IGNORECASE),
    re.compile(r'endpoint\s*[:=]\s*["\']([^"\']{4,200})["\']', re.IGNORECASE),
    re.compile(r'href\s*=\s*["\']([^"\'#\s]{4,200})["\']', re.IGNORECASE),
    re.compile(r'action\s*=\s*["\']([^"\'#\s]{4,200})["\']', re.IGNORECASE),
    re.compile(r'(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']{4,200})["\']', re.IGNORECASE),
    re.compile(r'\.open\s*\(\s*["\'][A-Z]+["\']\s*,\s*["\']([^"\']{4,200})["\']', re.IGNORECASE),
]

# Regex for path parameters (numbers/UUIDs in path)
_PATH_SEGMENT_RE = re.compile(
    r'/(\d{1,10}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_\-]{8,36})(?=/|$)'
)

# Attributes with URLs to search in all tags
_URL_ATTRIBUTES = ["href", "action", "src", "data-url", "data-href", "data-src",
                   "data-action", "data-link", "content"]


@dataclass
class FormField:
    """HTML form field."""
    name: str
    type: str = "text"
    value: str = ""


@dataclass
class SpiderForm:
    """Found HTML form."""
    action: str
    method: str = "GET"
    fields: list[FormField] = field(default_factory=list)
    page_url: str = ""


@dataclass
class SpiderEndpoint:
    """Found endpoint (from HTML, JS, URL, or path-segment)."""
    url: str
    source: str = "html"   # html | js | param | path | robots | sitemap | form
    method: str = "GET"
    params: list[str] = field(default_factory=list)
    body: str = ""          # for POST forms — encoded body
    headers: dict = field(default_factory=dict)


@dataclass
class SpiderResult:
    """Site crawl result."""
    base_url: str
    pages: list[str] = field(default_factory=list)
    forms: list[SpiderForm] = field(default_factory=list)
    endpoints: list[SpiderEndpoint] = field(default_factory=list)
    js_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_requests: int = 0

    def to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "pages_count": len(self.pages),
            "forms_count": len(self.forms),
            "endpoints_count": len(self.endpoints),
            "js_files_count": len(self.js_files),
            "errors_count": len(self.errors),
            "total_requests": self.total_requests,
        }


class AsyncSpider:
    """Asynchronous recursive site crawler."""

    def __init__(
        self,
        max_depth: int = 3,
        max_pages: int = 100,
        concurrency: int = 5,
        timeout: float = 10.0,
        user_agent: str = "Mozilla/5.0 (compatible; pentool/1.0; security scanner)",
        respect_scope: bool = True,
        on_page: Callable[[str | None, None]] = None,
        on_progress: Callable[[int, int | None, None]] = None,
        js_render: bool = False,
        extra_headers: dict | None = None,
    ) -> None:
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.timeout = timeout
        self.user_agent = user_agent
        self.respect_scope = respect_scope
        self.on_page = on_page
        self.on_progress = on_progress
        self._stop = False
        self.extra_headers: dict = extra_headers or {}
        # Playwright JS rendering — enabled only if playwright is installed
        self.js_render = js_render and is_playwright_available()

    def stop(self) -> None:
        self._stop = True

    async def crawl(self, start_url: str) -> SpiderResult:
        self._stop = False
        parsed = urlparse(start_url)
        base_domain = parsed.netloc
        base_scheme = parsed.scheme

        result = SpiderResult(base_url=start_url)
        visited: set[str] = set()
        # (url, depth)
        queue: list[tuple[str, int]] = [(start_url, 0)]
        semaphore = asyncio.Semaphore(self.concurrency)

        if self.js_render:
            # Playwright JS rendering
            await self._crawl_playwright(
                start_url, base_domain, base_scheme, result, visited, queue, semaphore
            )
        else:
            # Regular aiohttp crawling
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                **self.extra_headers,
            }

            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                # First parse robots.txt and sitemap.xml
                await self._fetch_robots_sitemap(
                    session, base_scheme, base_domain, result, visited, queue
                )

                while queue and not self._stop and len(visited) < self.max_pages:
                    # Take a batch of URLs for parallel processing
                    batch = []
                    while queue and len(batch) < self.concurrency:
                        url, depth = queue.pop(0)
                        norm = self._normalize_url(url)
                        if norm in visited:
                            continue
                        if self.respect_scope and not self._in_scope(url, base_domain):
                            continue
                        visited.add(norm)
                        batch.append((url, depth))

                    if not batch:
                        break

                    tasks = [
                        self._fetch_page(session, url, depth, result, base_domain, semaphore)
                        for url, depth in batch
                    ]
                    pages_results = await asyncio.gather(*tasks, return_exceptions=True)

                    for i, page_result in enumerate(pages_results):
                        if isinstance(page_result, Exception):
                            result.errors.append(str(page_result))
                            continue
                        if page_result is None:
                            continue
                        url, depth = batch[i]
                        new_links = page_result
                        if depth < self.max_depth:
                            for link in new_links:
                                norm = self._normalize_url(link)
                                if norm not in visited:
                                    queue.append((link, depth + 1))

        # Deduplication
        result.pages = list(dict.fromkeys(result.pages))
        result.js_files = list(dict.fromkeys(result.js_files))
        result.total_requests = len(visited)
        return result

    # ── robots.txt + sitemap.xml ─────────────────────────────────────────────

    async def _fetch_robots_sitemap(
        self,
        session,
        scheme: str,
        domain: str,
        result: SpiderResult,
        visited: set,
        queue: list,
    ) -> None:
        """Parse robots.txt and sitemap.xml for extended discovery."""
        base = f"{scheme}://{domain}"

        # robots.txt
        try:
            robots_url = f"{base}/robots.txt"
            async with session.get(robots_url, ssl=False, allow_redirects=True) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    for line in text.splitlines():
                        line = line.strip()
                        low = line.lower()
                        if low.startswith("disallow:") or low.startswith("allow:"):
                            path = line.split(":", 1)[1].strip()
                            if path and path != "/" and "*" not in path:
                                url = urljoin(base, path)
                                norm = self._normalize_url(url)
                                if norm not in visited and self._in_scope(url, domain):
                                    queue.append((url, 1))
                                    result.endpoints.append(SpiderEndpoint(
                                        url=url, source="robots", method="GET",
                                    ))
                        elif low.startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            await self._fetch_sitemap(
                                session, sitemap_url, result, visited, queue, domain
                            )
            result.total_requests += 1
        except Exception as exc:
            logger.debug("robots.txt fetch error: %s", exc)

        # sitemap.xml (fallback if not specified in robots)
        try:
            sitemap_url = f"{base}/sitemap.xml"
            await self._fetch_sitemap(session, sitemap_url, result, visited, queue, domain)
        except Exception as exc:
            logger.debug("sitemap.xml fetch error: %s", exc)

    async def _fetch_sitemap(
        self, session, sitemap_url: str, result: SpiderResult,
        visited: set, queue: list, domain: str,
    ) -> None:
        """Parse sitemap.xml and add URLs to the queue."""
        try:
            async with session.get(sitemap_url, ssl=False, allow_redirects=True) as resp:
                if resp.status != 200:
                    return
                text = await resp.text(errors="replace")
                result.total_requests += 1
                # Look for <loc>URL</loc>
                for match in re.finditer(r'<loc>\s*(https?://[^<]+)\s*</loc>', text):
                    url = match.group(1).strip()
                    if self._in_scope(url, domain):
                        norm = self._normalize_url(url)
                        if norm not in visited:
                            queue.append((url, 1))
                            result.endpoints.append(SpiderEndpoint(
                                url=url, source="sitemap", method="GET",
                            ))
                # Nested sitemap indexes
                for match in re.finditer(r'<sitemap>.*?<loc>\s*(https?://[^<]+)\s*</loc>', text, re.DOTALL):
                    nested = match.group(1).strip()
                    await self._fetch_sitemap(session, nested, result, visited, queue, domain)
        except Exception as exc:
            logger.debug("sitemap fetch error %s: %s", sitemap_url, exc)

    # ── page fetch ───────────────────────────────────────────────────────────

    async def _fetch_page(
        self,
        session,
        url: str,
        depth: int,
        result: SpiderResult,
        base_domain: str,
        semaphore: asyncio.Semaphore,
    ) -> list[str]:
        async with semaphore:
            try:
                async with session.get(url, allow_redirects=True, ssl=False) as resp:
                    result.total_requests += 1
                    content_type = resp.headers.get("Content-Type", "")
                    body = await resp.text(errors="replace")

                    if self.on_page:
                        self.on_page(url)

                    if "javascript" in content_type or url.split("?")[0].endswith(".js"):
                        # JS file — find API endpoints and add to list
                        result.js_files.append(url)
                        endpoints = self._extract_js_endpoints(body, url)
                        result.endpoints.extend(endpoints)
                        # Also extract pages from JS endpoints for crawling
                        js_page_links = [
                            ep.url for ep in endpoints
                            if ep.url.startswith("http")
                            and self._in_scope(ep.url, base_domain)
                        ]
                        return js_page_links

                    if "html" not in content_type and "text/plain" not in content_type:
                        return []

                    result.pages.append(url)

                    # HTML parsing
                    links, forms, js_links = self._parse_html(body, url, base_domain)

                    # Add forms
                    result.forms.extend(forms)

                    # JS files added to queue
                    for js_url in js_links:
                        self._normalize_url(js_url)
                        if js_url not in result.js_files:
                            result.js_files.append(js_url)

                    # Extract parameters from current page URL
                    params = parse_qs(urlparse(url).query)
                    if params:
                        result.endpoints.append(SpiderEndpoint(
                            url=url,
                            source="param",
                            method="GET",
                            params=list(params.keys()),
                        ))

                    # Detect path parameters (numbers and UUIDs in path)
                    path_variants = self._extract_path_variants(url, base_domain)
                    for pv in path_variants:
                        if pv not in [ep.url for ep in result.endpoints]:
                            result.endpoints.append(SpiderEndpoint(
                                url=pv, source="path", method="GET",
                            ))

                    # Return links + JS (JS also goes to crawl queue)
                    return links + js_links

            except asyncio.TimeoutError:
                result.errors.append(f"Timeout: {url}")
                return []
            except Exception as exc:
                result.errors.append(f"Error {url}: {exc}")
                return []

    # ── Playwright JS rendering ───────────────────────────────────────────────

    async def _crawl_playwright(
        self,
        start_url: str,
        base_domain: str,
        base_scheme: str,
        result: SpiderResult,
        visited: set,
        queue: list,
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Crawling with JavaScript rendering via Playwright.

        Used only if playwright is installed and js_render=True.
        Launches Chromium in headless mode, loads pages, waits for
        networkidle, then extracts HTML with executed JS.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright not available, falling back to aiohttp")
            # Fallback to aiohttp
            import aiohttp
            aio_timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            async with aiohttp.ClientSession(timeout=aio_timeout, headers=headers) as session:
                await self._fetch_robots_sitemap(
                    session, base_scheme, base_domain, result, visited, queue
                )
                while queue and not self._stop and len(visited) < self.max_pages:
                    batch = []
                    while queue and len(batch) < self.concurrency:
                        url, depth = queue.pop(0)
                        norm = self._normalize_url(url)
                        if norm in visited:
                            continue
                        if self.respect_scope and not self._in_scope(url, base_domain):
                            continue
                        visited.add(norm)
                        batch.append((url, depth))
                    if not batch:
                        break
                    tasks = [
                        self._fetch_page(session, url, depth, result, base_domain, semaphore)
                        for url, depth in batch
                    ]
                    for i, page_result in enumerate(
                        await asyncio.gather(*tasks, return_exceptions=True)
                    ):
                        if isinstance(page_result, Exception):
                            result.errors.append(str(page_result))
                            continue
                        if page_result and batch[i][1] < self.max_depth:
                            for link in page_result:
                                if self._normalize_url(link) not in visited:
                                    queue.append((link, batch[i][1] + 1))
            return

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.user_agent,
                ignore_https_errors=True,
            )
            page = await context.new_page()

            while queue and not self._stop and len(visited) < self.max_pages:
                url, depth = queue.pop(0)
                norm = self._normalize_url(url)
                if norm in visited:
                    continue
                if self.respect_scope and not self._in_scope(url, base_domain):
                    continue
                visited.add(norm)

                html = await self._fetch_page_playwright(page, url, result)
                if html is None:
                    continue

                if self.on_page:
                    self.on_page(url)

                result.pages.append(url)
                links, forms, js_links = self._parse_html(html, url, base_domain)
                result.forms.extend(forms)
                result.js_files.extend(
                    j for j in js_links if j not in result.js_files
                )

                if depth < self.max_depth:
                    for link in links + js_links:
                        if self._normalize_url(link) not in visited:
                            queue.append((link, depth + 1))

                if self.on_progress:
                    self.on_progress(
                        len(visited),
                        min(self.max_pages, len(visited) + len(queue)),
                    )

            await browser.close()

    async def _fetch_page_playwright(
        self,
        page,
        url: str,
        result: SpiderResult,
    ) -> str | None:
        try:
            response = await page.goto(
                url,
                timeout=int(self.timeout * 1000),
                wait_until="networkidle",
            )
            result.total_requests += 1
            if response is None or not response.ok:
                return None
            return await page.content()
        except Exception as exc:
            result.errors.append(f"Playwright error {url}: {exc}")
            return None

    # ── HTML parsing ─────────────────────────────────────────────────────────

    def _parse_html(
        self, html: str, page_url: str, base_domain: str
    ) -> tuple[list[str], list[SpiderForm], list[str]]:
        """Parse HTML: links, forms, JS files, data attributes."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return [], [], []

        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        js_links: list[str] = []
        forms: list[SpiderForm] = []
        seen_links: set[str] = set()

        def _add_link(raw_href: str) -> None:
            if not raw_href:
                return
            raw_href = raw_href.strip()
            if raw_href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                return
            abs_url = urljoin(page_url, raw_href)
            parsed = urlparse(abs_url)
            if parsed.scheme not in ("http", "https"):
                return
            if self.respect_scope and parsed.netloc != base_domain:
                return
            norm = self._normalize_url(abs_url)
            if norm not in seen_links:
                seen_links.add(norm)
                links.append(abs_url)

        # <a href> and <link href>
        for tag in soup.find_all(["a", "link"], href=True):
            _add_link(tag.get("href", ""))

        # All tags — look for data-url / data-href / data-src / data-action
        for tag in soup.find_all(True):
            for attr in _URL_ATTRIBUTES:
                val = tag.get(attr, "")
                if val and val.startswith(("http", "/", "./")):
                    _add_link(val)

        # <meta http-equiv="refresh" content="0;url=...">
        for meta in soup.find_all("meta", attrs={"http-equiv": True}):
            content = meta.get("content", "")
            m = re.search(r'url=([^\s"\']+)', content, re.IGNORECASE)
            if m:
                _add_link(m.group(1))

        # JS files (<script src>)
        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            if src:
                abs_url = urljoin(page_url, src)
                if urlparse(abs_url).scheme in ("http", "https"):
                    js_links.append(abs_url)

        # Inline <script> — search in them too
        for script in soup.find_all("script", src=False):
            inline = script.get_text(strip=True)
            if inline and len(inline) > 20:
                endpoints = self._extract_js_endpoints(inline, page_url)
                for ep in endpoints:
                    if ep.url.startswith("http") and self._in_scope(ep.url, base_domain):
                        _add_link(ep.url)

        # Forms
        for form in soup.find_all("form"):
            action = form.get("action", "") or page_url
            action = urljoin(page_url, action)
            method = (form.get("method", "GET") or "GET").upper()
            fields: list[FormField] = []

            for inp in form.find_all(["input", "textarea", "select"]):
                name = inp.get("name", "")
                if not name:
                    continue
                input_type = inp.get("type", "text").lower()
                # Skip buttons and hidden fields without value
                if input_type in ("submit", "button", "image", "reset"):
                    continue
                fields.append(FormField(
                    name=name,
                    type=input_type,
                    value=inp.get("value", ""),
                ))

            if fields:
                forms.append(SpiderForm(
                    action=action,
                    method=method,
                    fields=fields,
                    page_url=page_url,
                ))

        return links, forms, js_links

    # ── JS endpoint extraction ────────────────────────────────────────────────

    def _extract_js_endpoints(self, js_content: str, js_url: str) -> list[SpiderEndpoint]:
        """Extract API endpoints from JS code."""
        endpoints: list[SpiderEndpoint] = []
        seen: set[str] = set()

        parsed_base = urlparse(js_url)
        base = f"{parsed_base.scheme}://{parsed_base.netloc}"

        for pattern in _JS_API_PATTERNS:
            for match in pattern.finditer(js_content):
                path = match.group(1).strip()
                if not path or len(path) > 300:
                    continue
                # Ignore clearly non-URL strings
                if any(c in path for c in [" ", "\n", "\t"]):
                    continue
                if path.startswith(("http://", "https://")):
                    full_url = path
                elif path.startswith("/"):
                    full_url = base + path
                else:
                    # Relative path
                    try:
                        full_url = urljoin(js_url, path)
                    except Exception:
                        continue

                # Remove fragments
                full_url = full_url.split("#")[0]
                if full_url in seen:
                    continue
                seen.add(full_url)

                params = list(parse_qs(urlparse(full_url).query).keys())
                endpoints.append(SpiderEndpoint(
                    url=full_url,
                    source="js",
                    method="GET",
                    params=params,
                ))

        return endpoints

    # ── path-segment injection discovery ────────────────────────────────────

    def _extract_path_variants(self, url: str, base_domain: str) -> list[str]:
        """Discover URL variants with path parameters for testing.

        Example: /api/users/123/profile -> /api/users/INJECT/profile
        Returns URLs with numeric/UUID segments as potential injection points.
        """
        variants: list[str] = []
        urlparse(url)

        # TODO: implement path variants (replace numeric/UUID segments with injection marker)
        # Currently returns empty list to avoid adding duplicate original URLs to scan targets.
        return variants

    # ── utilities ─────────────────────────────────────────────────────────────

    def _normalize_url(self, url: str) -> str:
        """Normalize URL (remove fragment, trailing slash)."""
        try:
            parsed = urlparse(url)
            normalized = parsed._replace(fragment="")
            result = normalized.geturl()
            return result.rstrip("/")
        except Exception:
            return url

    def _in_scope(self, url: str, base_domain: str) -> bool:
        """Check that a URL is in scope (same domain or subdomain).

        Delegates to the shared pentool.utils.scope.domain_in_scope() —
        also used by ProxyServer.is_in_scope (modules/proxy.py) so both
        modules implement scope matching once instead of twice.
        """
        try:
            parsed = urlparse(url)
            return domain_in_scope(parsed.netloc, base_domain)
        except Exception:
            return False


__all__ = ["AsyncSpider", "SpiderResult", "SpiderForm", "FormField", "SpiderEndpoint"]
