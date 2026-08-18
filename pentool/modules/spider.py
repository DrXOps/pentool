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

# ── CPU-оптимизация (GIL) ──────────────────────────────────────────────────
# Профиль показал: ~55% CPU спайдера уходит на urllib-обработку ссылок в
# _add_link (urljoin/urlparse/urlsplit/normalize) — это Python-код под GIL.
# Выносим эту работу в ProcessPoolExecutor на ПАЧКАХ ссылок (даёт ~4x на
# бенчмарке), НО только когда пачка достаточно большая, чтобы оправдать
# IPC-перенос (на мелких — IPC задавит: 0.1x). Парсинг же ускоряем lxml
# (11x, C-реализация, освобождает GIL) — см. bench_cpu_parsing.py.
#
# Порог: если страница даёт меньше _PROC_THRESHOLD кандидатов-ссылок,
# обрабатываем синхронно (дешёвле), иначе — пачкой через пул.
# ── Single source of truth for the crawler's default limits ──────────────
# Consumed by AsyncSpider, SpiderConfig/SpiderAPI, ScanConfig/ScanService,
# the Spider screen, and the Scanner screen's crawl options — so the default
# crawl depth/pages/concurrency are defined in ONE place instead of being
# copy-pasted as magic numbers across modules.
DEFAULT_MAX_DEPTH: int = 5
DEFAULT_MAX_PAGES: int = 200
DEFAULT_CONCURRENCY: int = 5

_PROC_POOL_ENABLED: bool = True
_PROC_POOL_WORKERS: int = min(8, max(2, (os.cpu_count() or 4)))
_PROC_THRESHOLD: int = 64

# Ленивый module-level пул процессов: один на процесс, делится всеми
# спайдерами. Создаётся только при первом использовании.
#
# Пул намеренно закрывают явно через shutdown_proc_pool() при выходе
# приложения (action_quit): fork воркеры наследуют все открытые fd родителя,
# включая слушающий сокет прокси на 8080. Если оставить их висеть, после
# штатного выхода TUI они осиротеют (PPID=1) и будут держать 8080 — следующий
# запуск падал с "address already in use".
_PROC_POOL: ProcessPoolExecutor | None = None


def _get_proc_pool() -> ProcessPoolExecutor | None:
    global _PROC_POOL
    if not _PROC_POOL_ENABLED:
        return None
    if _PROC_POOL is None:
        try:
            # fork (spawn небезопасен: при установке через uv console-script
            # __main__ не является .py модулем, и spawn-воркеры не могут его
            # переимпортировать — пул падал/зависал на *start up*). При fork
            # воркеры наследуют fd 8080, поэтому пул закрывают явно через
            # shutdown_proc_pool() при выходе приложения (action_quit).
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
    """Модульная urllib-нормализация (fragment, trailing slash) — picklizable.

    Одна и та же логика используется и в sync-пути, и работающими в
    процессах воркерами пула (ProcessPoolExecutor требует модульную функцию,
    а не метод инстанса — иначе не попиклизуется).
    """
    try:
        parsed = urlparse(url)
        normalized = parsed._replace(fragment="")
        return normalized.geturl().rstrip("/")
    except Exception:
        return url


def _link_cpu_work(raw: str, page_url: str, base_domain: str,
                   respect_scope: bool) -> tuple[bool, str, str]:
    """Модульная CPU-половина _add_link: тяжёлая urllib-обработка одной ссылки.

    Возвращает (ok, abs_url, norm_url):
      ok      — True если ссылку надо добавить (протокол http(s), в scope)
      abs_url — абсолютный URL (для result.links)
      norm_url— нормализованный (fragment без trailing slash) для дедупликации
    Дедупликация (seen_links) остаётся в ОСНОВНОМ потоке — сеть сета set-add
    дёшева и не требует GIL-обхода.
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
    """Батч-версия _link_cpu_work: обрабатывает весь СПИСОК кандидатов.

    Нужен для ProcessPoolExecutor: если отдавать в пул по одной ссылке
    (pool.map(_link_cpu_work, cands)), каждая ссылка — отдельный IPC-перенос
    (одна микро-задача туда + результат обратно). На пачке из тысяч ссылок
    IPC-накладные > выигрыша от распараллеливания. Батч передаёт весь список
    одним IPC (pickle), воркер перебирает его построчно и возвращает список
    результатов одним IPC — всего 2 IPC на пачку, а urllib-работа выполняется
    в подпроцессе без GIL (см. bench_cpu_parsing.py: urllib-задача 4.16x).
    """
    return [_link_cpu_work(c, page_url, base_domain, respect_scope)
            for c in cands]


# ── lxml/bs4 единый интерфейс для парсинга ─────────────────────────────────

class _LxmlSoup:
    """Тонкая адаптация lxml.html.Element → bs4-подобный find_all/get.

    Позволяет писать общий код итерации по soup независимо от того, парсим
    lxml (быстро, C-код) или bs4 (фолбэк). find_all по имени тега возвращает
    список-подобный объект, у которого элементы имеют .get(name)/.text.
    """

    __slots__ = ("_tree",)

    def __init__(self, html: str, lxml_html) -> None:
        # fromstring бросает на пустом/мусорном HTML; делаем tolerant через
        # разбор в фрагмент: lxml.html.document_fromstring требует полный док.
        try:
            self._tree = lxml_html.fromstring(html)
        except Exception:
            self._tree = lxml_html.Element("html")

    def find_all(self, name):
        """Все элементы с тегом name (str или list[str]) либо все (True)."""
        if name is True:
            return list(self._tree.iter())
        if isinstance(name, (list, tuple)):
            out = []
            for n in name:
                out.extend(self._tree.iter(n))
            return out
        return list(self._tree.iter(name))


    def get_text_strip(self, el) -> str:
        # lxml Element.text_content — полный текстовый контент (аналог bs4 get_text)
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
    """<a>/<link> href-значения."""
    for tag in soup.find_all(tags if not isinstance(tags, str) else tags):
        href = _el_get(tag, "href")
        if href:
            yield href


def _iter_attr_urls(soup):
    """data-url/href/src/action/content атрибуты на всех тегах."""
    for tag in soup.find_all(True):
        for attr in _URL_ATTRIBUTES:
            val = _el_get(tag, attr)
            if val and val.startswith(("http", "/", "./")):
                yield val


def _iter_meta_refresh(soup):
    """content у <meta http-equiv>.lxml атрибуты регистрозависимы — http-equiv
    может быть передано как http-quiv; lxml сохраняет регистр атрибута. Пробуем
    оба варианта."""
    for tag in soup.find_all("meta"):
        eq = _el_get(tag, "http-equiv", _el_get(tag, "http_equiv"))
        if eq and "refresh" in eq.lower():
            yield _el_get(tag, "content")


def _iter_script_src(soup):
    for script in soup.find_all("script"):
        yield _el_get(script, "src")


def _iter_inline_scripts(soup):
    """Текстовый контент инлайн-скриптов (без src)."""
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
    """input/textarea/select внутри формы. Работает и с bs4, и с lxml-элементом."""
    # bs4: .find_all([...]); lxml: .iter() по тегам
    if hasattr(form, "find_all"):
        try:
            return list(form.find_all(["input", "textarea", "select"]))
        except Exception:
            return list(form.find_all(True))
    # lxml-элемент — итерируем по тегам через iter()
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
            # Firefox — lighter than Chromium, shared with --real.
            browser = await pw.firefox.launch(headless=True)
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
        """Внутренняя реализация _parse_html (lxml + пачечная обработка URL).

        Парсинг: предпочитаем lxml (C-код, ~11x быстрее bs4/html.parser и
        освобождает GIL). Если lxml не установлен — фолбэк на BeautifulSoup.

        Обработка ссылок: собираем все raw-кандидаты в один список, затем
        if len(candidates) >= _PROC_THRESHOLD — обрабатываем пачкой через
        ProcessPoolExecutor (_link_cpu_work, urllib-Часть в подпроцессах,
        обходит GIL, ~4x), иначе синхронно построчно (тот же _link_cpu_work,
        но в текущем процессе). Дедупликация (seen_links) всегда в основном
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

        # JS files (<script src>) — отдельно, не через пул (немного urljoin)
        for src in _iter_script_src(soup):
            if src:
                abs_url = urljoin(page_url, src)
                if urlparse(abs_url).scheme in ("http", "https"):
                    js_links.append(abs_url)

        # Inline <script> — search in them too (не через пул: извлекает
        # endpoints, а не просто нормализует ссылку)
        for inline in _iter_inline_scripts(soup):
            if inline and len(inline) > 20:
                endpoints = self._extract_js_endpoints(inline, page_url)
                for ep in endpoints:
                    candidates.append(ep.url)

        # ── Обработка пачки кандидатов (пул или синхронно) ────────────────
        if candidates:
            links = self._commit_links(
                candidates, page_url, base_domain, seen_links)

        # ── Forms (по-прежнему bs4/lxml-итерация, без пула) ───────────────
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
                        # form-query трактуем как кандидата (может попасть в пул)
                        candidates2 = [f"{action}{sep}{query}"]
                        links.extend(self._commit_links(
                            candidates2, page_url, base_domain, seen_links))

        return links, forms, js_links

    def _make_soup(self, html: str):
        """Парсер: lxml (быстро) или bs4 (фолбэк), с защитой от ImportError."""
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
        """Обработать пачку кандидатов через пул/синхронно, вернуть добавленные.

        Использует _link_cpu_work (модульную): если кандидатов много — через
        ProcessPoolExecutor (обход GIL), иначе синхронно. Дедуп — здесь.
        """
        if not candidates:
            return []
        # Пытаемся через пул, если кандидатов достаточно. Используем БАТЧ:
        # pool.submit(_bulk_links_cpu, candidates) — весь список одним IPC
        #  туда и результатом — обратно (всего 2 IPC на пачку). НЕ pool.map
        #  по одной ссылке: то было бы N IPC на микро-задачу и вредило бы
        #  (см. Ремарка в _bulk_links_cpu).
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
                # Пул сломался/завис — падаем на синхронный путь (тот же
                # движок _link_cpu_work, результат не меняется)
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
        urlparse(url)

        # TODO: implement path variants (replace numeric/UUID segments with injection marker)
        # Currently returns empty list to avoid adding duplicate original URLs to scan targets.
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
