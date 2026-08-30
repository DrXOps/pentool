"""AsyncSpider — recursive site crawler."""

from __future__ import annotations

import asyncio
import os
import re
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pickle import PicklingError
from typing import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from pentool.core.logging import get_logger
from pentool.utils.scope import domain_in_scope

logger = get_logger(__name__)

# ── CPU optimization (GIL) ─────────────────────────────────────────────────
# Profiling showed ~55% of the spider's CPU goes to urllib link processing in
# _add_link (urljoin/urlparse/urlsplit/normalize) — Python code under the GIL.
# This is offloaded to a ProcessPoolExecutor over BATCHES of links (~4x on the
# benchmark), but only when the batch is large enough to justify the IPC
# transfer (small batches are dominated by IPC overhead: ~0.1x). Parsing is
# instead sped up with lxml (11x, C implementation, releases the GIL) — see
# bench_cpu_parsing.py.
#
# Threshold: when a page yields fewer than _PROC_THRESHOLD link candidates they
# are processed synchronously (cheaper); otherwise they go through the pool.
# ── Single source of truth for the crawler's default limits ──────────────
# Consumed by AsyncSpider, SpiderConfig/SpiderAPI, ScanConfig/ScanService,
# the Spider screen, and the Scanner screen's crawl options — so the default
# crawl depth/pages/concurrency are defined in ONE place instead of being
# copy-pasted as magic numbers across modules.
DEFAULT_MAX_DEPTH: int = 5
DEFAULT_MAX_PAGES: int = 200
DEFAULT_CONCURRENCY: int = 5

# Interactive SPA discovery (N1): how many in-page clicks the JS crawl will
# perform on a single page to surface client-side routes/tabs. Bounded so a
# deep interactive app can't explode the request budget.
_SPA_MAX_CLICKS_PER_PAGE: int = 12

_PROC_POOL_ENABLED: bool = True
_PROC_POOL_WORKERS: int = min(8, max(2, (os.cpu_count() or 4)))
_PROC_THRESHOLD: int = 64

# Lazy module-level process pool: one per process, shared by all spiders.
# Created only on first use.
#
# The pool is deliberately closed explicitly via shutdown_proc_pool() when the
# app exits (action_quit): fork workers inherit all of the parent's open fds,
# including the proxy's listening socket on 8080. If left running they orphan
# (PPID=1) after a normal TUI exit and hold onto 8080 — the next launch failed
# with "address already in use".
_PROC_POOL: ProcessPoolExecutor | None = None


def _get_proc_pool() -> ProcessPoolExecutor | None:
    global _PROC_POOL
    if not _PROC_POOL_ENABLED:
        return None
    if _PROC_POOL is None:
        try:
            # fork (spawn is unsafe: when installed via a uv console-script,
            # __main__ is not a .py module, so spawn workers cannot re-import
            # it — the pool failed/hung at *start up*). With fork, workers
            # inherit fd 8080, so the pool is closed explicitly via
            # shutdown_proc_pool() on app exit (action_quit).
            _PROC_POOL = ProcessPoolExecutor(max_workers=_PROC_POOL_WORKERS)
        except (ImportError, OSError, RuntimeError):
            _PROC_POOL = None
    return _PROC_POOL


def shutdown_proc_pool() -> None:
    """Stop the shared CPU pool, releasing its workers' inherited fds.

    Only needed for long-lived processes (the TUI). Without this, a pool
    created via fork leaves workers that remain after the main process
    exits (orphans with PPID=1) and keep the proxy's 8080 listener fd open.
    Terminating them cleanly on quit releases the port for the next launch.
    """
    global _PROC_POOL
    pool = _PROC_POOL
    _PROC_POOL = None
    if pool is not None:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            logger.debug("shutdown_proc_pool: %s", exc)


def _normalize_url_cpu(url: str) -> str:
    """Modular urllib normalization (fragment, trailing slash) — picklizable.

    The same logic is used by the sync path and by pool workers running in
    separate processes (ProcessPoolExecutor needs a module-level function,
    not an instance method — otherwise it won't pickle).
    """
    try:
        parsed = urlparse(url)
        normalized = parsed._replace(fragment="")
        return normalized.geturl().rstrip("/")
    except Exception:
        return url


def _link_cpu_work(raw: str, page_url: str, base_domain: str,
                   respect_scope: bool) -> tuple[bool, str, str]:
    """Modular CPU half of _add_link: the heavy urllib handling of one link.

    Returns (ok, abs_url, norm_url):
      ok       — True if the link should be added (http(s) protocol, in scope)
      abs_url  — absolute URL (for result.links)
      norm_url — normalized (fragment/trailing-slash-free) for dedup
    Dedup (seen_links) stays in the MAIN thread — a set add is cheap and does
    not need the GIL workaround.
    """
    if not raw:
        return False, "", ""
    raw = raw.strip()
    if raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return False, "", ""
    try:
        abs_url = urljoin(page_url, raw)
        parsed = urlparse(abs_url)
    except Exception:
        return False, "", ""
    if parsed.scheme not in ("http", "https"):
        return False, "", ""
    if respect_scope and parsed.netloc != base_domain:
        return False, "", ""
    norm = _normalize_url_cpu(abs_url)
    return True, abs_url, norm


def _bulk_links_cpu(cands, page_url: str, base_domain: str,
                    respect_scope: bool) -> list[tuple[bool, str, str]]:
    """Batch version of _link_cpu_work: processes the whole list of candidates.

    Needed for ProcessPoolExecutor: if you hand the pool one link at a time
    (pool.map(_link_cpu_work, cands)) each link is a separate IPC transfer (one
    micro-task out and one result back). On a batch of thousands of links the
    IPC overhead outweighs the parallelism win. The batch sends the whole list
    in a single IPC (pickle), the worker iterates it line by line and returns
    the results list in one IPC — just 2 IPCs per batch, and the urllib work
    runs in the subprocess without the GIL (see bench_cpu_parsing.py: the
    urllib task is 4.16x).
    """
    return [_link_cpu_work(c, page_url, base_domain, respect_scope)
            for c in cands]


# ── lxml/bs4 unified parsing interface ──────────────────────────────────────

class _LxmlSoup:
    """Thin adaptation of lxml.html.Element → bs4-like find_all/get.

    Lets iteration code be written against one soup interface regardless of
    whether parsing via lxml (fast, C code) or bs4 (fallback). find_all by tag
    name returns
    список-подобный объект, у которого элементы имеют .get(name)/.text.
    """

    __slots__ = ("_tree",)

    def __init__(self, html: str, lxml_html) -> None:
        # fromstring raises on empty/junk HTML; be tolerant by parsing into
        # a fragment: lxml.html.document_fromstring requires a full document.
        try:
            self._tree = lxml_html.fromstring(html)
        except Exception:
            self._tree = lxml_html.Element("html")

    def find_all(self, name):
        """All elements with the tag *name* (str or list[str]) or everything (True)."""
        if name is True:
            return list(self._tree.iter())
        if isinstance(name, (list, tuple)):
            out = []
            for n in name:
                out.extend(self._tree.iter(n))
            return out
        return list(self._tree.iter(name))


    def get_text_strip(self, el) -> str:
        # lxml Element.text_content — full text content (bs4 get_text equivalent)
        if hasattr(el, "text_content"):
            return el.text_content() or ""
        return el.text or ""


class _EmptySoup:
    """Пустой soup, если ни lxml, ни bs4 недоступны — парсинг даёт ничего."""

    def find_all(self, name):
        return []


def _el_get(el, attr: str, default: str = "") -> str:
    return el.get(attr, default)


def _iter_hrefs(soup, tags):
    """<a>/<link> href values."""
    for tag in soup.find_all(tags if not isinstance(tags, str) else tags):
        href = _el_get(tag, "href")
        if href:
            yield href


def _iter_attr_urls(soup):
    """data-url/href/src/action/content attributes on every tag."""
    for tag in soup.find_all(True):
        for attr in _URL_ATTRIBUTES:
            val = _el_get(tag, attr)
            if val and val.startswith(("http", "/", "./")):
                yield val


def _iter_meta_refresh(soup):
    """The content of <meta http-equiv>. lxml attributes are case-sensitive —
    http-equiv may arrive as http-quiv; lxml keeps the attribute's case. Try
    both variants."""
    for tag in soup.find_all("meta"):
        eq = _el_get(tag, "http-equiv", _el_get(tag, "http_equiv"))
        if eq and "refresh" in eq.lower():
            yield _el_get(tag, "content")


def _iter_script_src(soup):
    for script in soup.find_all("script"):
        yield _el_get(script, "src")


def _iter_inline_scripts(soup):
    """The text content of inline scripts (ones without a src)."""
    for script in soup.find_all("script"):
        if _el_get(script, "src"):
            continue
        # lxml: text_content; bs4: get_text(strip=True)
        if hasattr(script, "get_text"):
            txt = script.get_text(strip=True)
        elif hasattr(script, "text_content"):
            txt = (script.text_content() or "").strip()
        else:
            txt = getattr(script, "text", "") or ""
        yield txt


def _iter_forms(soup):
    yield from soup.find_all("form")


def _iter_form_inputs(form):
    """input/textarea/select inside a form. Works with both bs4 and lxml elements."""
    # bs4: .find_all([...]); lxml: .iter() over tags
    if hasattr(form, "find_all"):
        try:
            return list(form.find_all(["input", "textarea", "select"]))
        except Exception:
            return list(form.find_all(True))
    # lxml element — iterate tags via iter()
    tags = ("input", "textarea", "select")
    return [el for el in form.iter() if el.tag in tags]


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
    # Headers the crawler actually used after merging Proxy-discovered auth
    # + explicit extra_headers. Filled by SpiderAPI.crawl; lets the scanner
    # reuse the same session (Cookie/Authorization) in its own active phase.
    auth_headers: dict = field(default_factory=dict)

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
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_pages: int = DEFAULT_MAX_PAGES,
        concurrency: int = DEFAULT_CONCURRENCY,
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

            # Callers (Target's "Crawl Scope"/"Crawl selected host", Spider's
            # own URL input when the user typed a bare host) default a
            # scheme-less host to https:// unconditionally. That's wrong for
            # a plain-HTTP target on a non-standard port (e.g. a local
            # dvwa.local:7474 test box) — TLS ClientHello sent to a plain
            # HTTP listener comes back as "SSL: WRONG_VERSION_NUMBER" and the
            # crawl silently produces 0 pages/0 forms/0 endpoints with no
            # obvious explanation in the UI (see log:
            # "SpiderAPI.crawl: https://dvwa.local:7474 -> 0 pages, 0 forms,
            # 0 endpoints" right after a WRONG_VERSION_NUMBER debug line).
            # Probe once and fall back to http:// on that specific failure
            # before doing anything else — cheap (single GET, short timeout)
            # and never runs for a URL the caller already gave an explicit
            # scheme for with a working TLS listener.
            base_scheme, start_url = await self._resolve_scheme(
                start_url, base_scheme, base_domain,
            )
            parsed = urlparse(start_url)
            base_domain = parsed.netloc
            queue = [(start_url, 0)]

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

    async def _resolve_scheme(
        self, start_url: str, scheme: str, domain: str,
    ) -> tuple[str, str]:
        """If `scheme` is https and the target actually only speaks plain
        HTTP (common on internal/test targets with non-standard ports —
        e.g. dvwa.local:7474), fall back to http:// after one quick probe.

        Only probes when scheme == "https" — an explicit http:// URL is
        never "corrected" to https, and a working https target pays only
        one extra GET (same host, already about to be crawled anyway).
        Any failure other than the specific SSL handshake mismatch (timeout,
        DNS error, connection refused, real cert error, ...) is left alone
        so the existing crawl (and its own error reporting) still runs and
        surfaces the real problem instead of masking it as a scheme issue.
        """
        if scheme != "https" or not domain:
            return scheme, start_url

        import ssl

        import aiohttp

        try:
            probe_timeout = aiohttp.ClientTimeout(total=min(self.timeout, 5.0))
            async with aiohttp.ClientSession(timeout=probe_timeout) as session:
                async with session.get(start_url, ssl=False, allow_redirects=False):
                    pass
            return scheme, start_url
        except (aiohttp.ClientConnectorSSLError, ssl.SSLError) as exc:
            if "WRONG_VERSION_NUMBER" not in str(exc):
                return scheme, start_url
            http_url = start_url.replace("https://", "http://", 1)
            logger.info(
                "AsyncSpider: %s speaks plain HTTP, not HTTPS (WRONG_VERSION_NUMBER) "
                "— retrying crawl as %s",
                domain, http_url,
            )
            return "http", http_url
        except Exception:
            # Any other failure (timeout, DNS, connection refused, real TLS
            # cert error, ...) — leave scheme as-is, let the real crawl hit
            # (and report) the same error itself.
            return scheme, start_url

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

    @staticmethod
    def _is_auth_redirect(final_url: str, requested_url: str) -> bool:
        """True if a redirected final URL lands on a login/signin page.

        Distinct -> login only when the final URL actually changed AND it
        looks like an auth entry point. Benign redirects (e.g. "/" ->
        "/index.html") are not flagged.
        """
        if final_url.rstrip("/") == requested_url.rstrip("/"):
            return False
        low = final_url.lower()
        return any(
            marker in low
            for marker in ("/login", "login.php", "signin", "/auth", "logon")
        )

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

                    # Detect "the server quietly bounced us to a login page".
                    # With allow_redirects=True a 302 → /login.php resolves to a
                    # 200 on the login page, so this code would otherwise
                    # silently treat the login page as a successful crawl page
                    # (0 findings, empty errors) instead of telling the user the
                    # target needs auth. Only flag when the FINAL URL is a
                    # login/signin/auth page to avoid noise on benign redirects
                    # (e.g. "/" -> "/index.html").
                    if self._is_auth_redirect(str(resp.url), url):
                        result.errors.append(
                            f"Auth required: {url} redirected to {resp.url} "
                            f"(login page) — session/Cookie needed to crawl protected pages"
                        )
                        return []

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
            # Chromium — same browser as --real, reliable proxy/JS rendering.
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

                # Interactive SPA discovery (N1): client-side apps build their
                # next-level routes/tabs only after a click. After rendering the
                # static DOM we click through a bounded set of interactive
                # elements, re-read the DOM after each click, and harvest any
                # *new* in-scope URLs — the classic XSS-Game /level4-style tab
                # navigation, Angular/React pagination, etc. Without this a JS
                # crawl only reads the initial shell and misses deep routes.
                await self._crawl_spa_clicks(
                    page, base_domain, result, visited, queue, depth,
                )

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

    async def _crawl_spa_clicks(
        self,
        page,
        base_domain: str,
        result: SpiderResult,
        visited: set,
        queue: list,
        depth: int,
    ) -> None:
        """Click through client-side tabs/links to surface SPA routes (N1).

        After the initial render of a JS page, many app frameworks (hash-based
        tabs, React/Angular routing, image galleries) only materialise their
        real endpoints after a user interaction. This bounded pass clicks the
        interactive elements seen in the current DOM, re-reads the DOM after
        each click (waiting for network idle so XHR-driven content lands), and
        harvests any *new* in-scope URLs into the crawl queue and as endpoints.

        It never mutates `visited` in a way that starves page — it only ADD
        newly discovered URLs; normal crawl dedup still applies. `page` stays
        on the last-clicked state, which is fine because the outer loop
        re-navigates via page.goto() on the next queued URL.
        """
        import asyncio
        from urllib.parse import urljoin

        clicked: set[str] = set()
        for _ in range(_SPA_MAX_CLICKS_PER_PAGE):
            if self._stop or len(visited) >= self.max_pages:
                break
            try:
                candidates = await page.eval_on_selector_all(
                    "a[href], button, [role='tab'], .tab, [onclick]",
                    """els => els.map((el, i) => {
                        const h = el.getAttribute('href') || el.textContent || el.innerText || '';
                        const k = h.trim().slice(0, 120);
                        return {i, k};
                    })""",
                )
            except Exception:
                break
            chosen = None
            for cand in candidates:
                key = cand.get("k", "")
                # Skip elements with no text/href (empty tab, spacer) and
                # anything already clicked on this page-pass.
                if key and key not in clicked:
                    chosen = cand
                    break
            if chosen is None:
                break

            idx = chosen.get("i")
            key = chosen.get("k", "")
            clicked.add(key)
            try:
                await page.evaluate(f"""() => {{
                    const els = document.querySelectorAll("a[href], button, [role='tab'], .tab, [onclick]");
                    const el = els[{idx}];
                    if (el) el.click();
                }}""")
                # Give the client-side handler time to run and any XHR to land.
                await page.wait_for_load_state("networkidle", timeout=2000)
                await asyncio.sleep(0.2)
            except Exception:
                # Click or wait failed (nav/redirect) — move on, don't panic.
                continue

            try:
                html = await page.content()
            except Exception:
                continue

            links, forms, js_links = self._parse_html(html, page.url, base_domain)
            result.forms.extend(forms)
            result.js_files.extend(
                j for j in js_links if j not in result.js_files
            )
            new_urls: list[str] = []
            for raw in links + js_links:
                try:
                    abs_url = raw if raw.startswith("http") else urljoin(page.url, raw)
                except Exception:
                    continue
                norm = self._normalize_url(abs_url)
                if norm not in visited and self._in_scope(abs_url, base_domain):
                    visited.add(norm)
                    new_urls.append(norm)
            # Surface the discovered SPA routes as endpoints AND push them back
            # into the crawl queue (depth+1) so the outer playwright loop will
            # navigate to them and audit their own forms/JS. `visited` guards
            # against re-visiting; per-page click budget bounds the explosion.
            result.endpoints.extend(
                SpiderEndpoint(url=u, source="spa", method="GET") for u in new_urls
            )
            if depth < self.max_depth:
                queue.extend((u, depth + 1) for u in new_urls)

    # ── HTML parsing ─────────────────────────────────────────────────────────

    def _parse_html(
        self, html: str, page_url: str, base_domain: str
    ) -> tuple[list[str], list[SpiderForm], list[str]]:
        """Parse HTML: links, forms, JS files, data attributes.

        CPU-оптимизация (см. header): парсинг — lxml (C, освобождает GIL),
        урllib-обработка ссылок — пачкой через ProcessPoolExecutor, когда
        кандидатов достаточно; в противном случае синхронно (тот же движок).
        Результат (дедуплицированные links/forms/js) идентичен прежнему bs4+
        построчному _add_link — это покрыто тестами test_spider.py.
        """
        return self._parse_html_internal(html, page_url, base_domain)

    def _parse_html_internal(
        self, html: str, page_url: str, base_domain: str
    ) -> tuple[list[str], list[SpiderForm], list[str]]:
        """Internal implementation of _parse_html (lxml + batched URL handling).

        Parsing: prefer lxml (C code, ~11x faster than bs4/html.parser and it
        releases the GIL). When lxml is not installed — fall back to (BeautifulSoup).

        Link handling: gather all raw candidates into one list, then
        if len(candidates) >= _PROC_THRESHOLD — process them as a batch through
        ProcessPoolExecutor (_link_cpu_work, the urllib part in subprocesses,
        works around the GIL, ~4x), otherwise synchronously line by line (the
        same _link_cpu_work, but in the current process). Dedup (seen_links) is
        always in the main
        потоке — сеть set-add дешёва. Итог идентичен прежнему bs4-пути.
        """
        soup = self._make_soup(html)
        links: list[str] = []
        js_links: list[str] = []
        forms: list[SpiderForm] = []
        seen_links: set[str] = set()

        candidates: list[str] = []

        # <a href> and <link href>
        for href in _iter_hrefs(soup, ["a", "link"]):
            candidates.append(href)

        # All tags — look for data-url / data-href / data-src / data-action
        for val in _iter_attr_urls(soup):
            candidates.append(val)

        # <meta http-equiv="refresh" content="0;url=...">
        for content in _iter_meta_refresh(soup):
            m = re.search(r'url=([^\s"\']+)', content, re.IGNORECASE)
            if m:
                candidates.append(m.group(1))

        # JS files (<script src>) — kept separate, not through the pool (just urljoin)
        for src in _iter_script_src(soup):
            if src:
                abs_url = urljoin(page_url, src)
                if urlparse(abs_url).scheme in ("http", "https"):
                    js_links.append(abs_url)

        # Inline <script> — search in them too (not through the pool: it extracts
        # endpoints, not just normalizes a link)
        for inline in _iter_inline_scripts(soup):
            if inline and len(inline) > 20:
                endpoints = self._extract_js_endpoints(inline, page_url)
                for ep in endpoints:
                    candidates.append(ep.url)

        # ── Candidate batch handling (pool or sync) ────────────────────────
        if candidates:
            links = self._commit_links(
                candidates, page_url, base_domain, seen_links)

        # ── Forms (still bs4/lxml iteration, no pool) ──────────────────────
        for form in _iter_forms(soup):
            action = (form.get("action") or page_url)
            action = urljoin(page_url, action)
            method = (form.get("method", "GET") or "GET").upper()
            fields: list[FormField] = []

            for inp in _iter_form_inputs(form):
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
                # Auto-submit GET forms with their default field values so
                # pages only reachable through a form (search boxes,
                # filters, ...) still get crawled. GET-only: submitting POST
                # forms could trigger real side effects (see old comment).
                if method == "GET" and any(f.value for f in fields):
                    query = urlencode([(f.name, f.value) for f in fields])
                    if query:
                        sep = "&" if urlparse(action).query else "?"
                        # treat the form query as a candidate (may reach the pool)
                        candidates2 = [f"{action}{sep}{query}"]
                        links.extend(self._commit_links(
                            candidates2, page_url, base_domain, seen_links))

        return links, forms, js_links

    def _make_soup(self, html: str):
        """Parser: lxml (fast) or bs4 (fallback), guarded against ImportError."""
        try:
            import lxml.html as lxml_html
            return _LxmlSoup(html, lxml_html)
        except ImportError:
            pass
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, "html.parser")
        except ImportError:
            return _EmptySoup()

    def _commit_links(self, candidates, page_url, base_domain, seen_links):
        """Process a batch of candidates via pool/sync, return the added ones.

        Uses the modular _link_cpu_work: when there are many candidates it
        goes through ProcessPoolExecutor (works around the GIL), otherwise
        synchronously. Dedup happens here.
        """
        if not candidates:
            return []
        # Try the pool when candidates are plenty. Use one BATCH call:
        # pool.submit(_bulk_links_cpu, candidates) — the whole list in a single
        # IPC in and one result — back (2 IPC per batch total). NOT pool.map
        # per link: that would be N IPCs per micro-task and would hurt
        # (see the note in _bulk_links_cpu).
        pool = _get_proc_pool() if len(candidates) >= _PROC_THRESHOLD else None
        respect_scope = self.respect_scope
        if pool is not None:
            try:
                fut = pool.submit(
                    _bulk_links_cpu, candidates, page_url, base_domain,
                    respect_scope,
                )
                results = fut.result(timeout=60)
            except (BrokenProcessPool, PicklingError, RuntimeError, OSError,
                    TimeoutError):
                # Pool broke/hung — fall back to the synchronous path (same
                # _link_cpu_work engine, result unchanged)
                results = [_link_cpu_work(c, page_url, base_domain, respect_scope)
                           for c in candidates]
        else:
            results = [_link_cpu_work(c, page_url, base_domain, respect_scope)
                       for c in candidates]

        added: list[str] = []
        for ok, abs_url, norm in results:
            if not ok:
                continue
            if norm not in seen_links:
                seen_links.add(norm)
                added.append(abs_url)
        return added

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
        try:
            parsed = urlparse(url)
        except Exception:
            return variants
        if not self._in_scope(url, base_domain):
            return variants

        path = parsed.path
        seen: set[str] = set()
        origin = self._normalize_url(url)
        query = f"?{parsed.query}" if parsed.query else ""
        for match in _PATH_SEGMENT_RE.finditer(path):
            # _PATH_SEGMENT_RE captures the value *after* the leading "/",
            # so group(1) start/end delimit exactly the segment to replace.
            seg_start, seg_end = match.start(1), match.end(1)
            swapped = path[:seg_start] + "{id}" + path[seg_end:]
            variant_url = f"{parsed.scheme}://{parsed.netloc}{swapped}{query}"
            norm = self._normalize_url(variant_url)
            # Never return the original URL itself (existing test contract),
            # only the variant with the segment swapped out. Dedup on the
            # normalized (query-free) form so ?page=2 vs ?page=3 collapse.
            if norm and norm not in seen and norm != origin and not (
                any(
                    self._normalize_url(existing) == norm
                    for existing in seen
                )
            ):
                seen.add(norm)
                variants.append(variant_url)
        return variants

    # ── utilities ─────────────────────────────────────────────────────────────

    def _normalize_url(self, url: str) -> str:
        """Normalize URL (remove fragment, trailing slash).

        Делегирует в модульную _normalize_url_cpu — единая реализация с
        воркерами ProcessPoolExecutor (см. _link_cpu_work).
        """
        return _normalize_url_cpu(url)

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


__all__ = [
    "AsyncSpider", "SpiderResult", "SpiderForm", "FormField", "SpiderEndpoint",
    "DEFAULT_MAX_DEPTH", "DEFAULT_MAX_PAGES", "DEFAULT_CONCURRENCY",
]
