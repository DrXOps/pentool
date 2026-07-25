"""AsyncSpider — рекурсивный краулер сайта."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse

from pentool.core.logging import get_logger

logger = get_logger(__name__)


def is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False

# Regex для поиска API-эндпоинтов в JS
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

# Regex для path-параметров (числа/UUID в path)
_PATH_SEGMENT_RE = re.compile(
    r'/(\d{1,10}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_\-]{8,36})(?=/|$)'
)

# Атрибуты с URL, которые ищем во всех тегах
_URL_ATTRIBUTES = ["href", "action", "src", "data-url", "data-href", "data-src",
                   "data-action", "data-link", "content"]


@dataclass
class FormField:
    """Поле HTML-формы."""
    name: str
    type: str = "text"
    value: str = ""


@dataclass
class SpiderForm:
    """Найденная HTML-форма."""
    action: str
    method: str = "GET"
    fields: list[FormField] = field(default_factory=list)
    page_url: str = ""


@dataclass
class SpiderEndpoint:
    """Найденный эндпоинт (из HTML, JS, URL или path-segment)."""
    url: str
    source: str = "html"   # html | js | param | path | robots | sitemap | form
    method: str = "GET"
    params: list[str] = field(default_factory=list)
    body: str = ""          # для POST-форм — encoded body
    headers: dict = field(default_factory=dict)


@dataclass
class SpiderResult:
    """Результат обхода сайта."""
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
    """Асинхронный рекурсивный краулер сайта."""

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
        # Playwright JS-рендеринг — включается только если playwright установлен
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
            # Playwright JS-рендеринг
            await self._crawl_playwright(
                start_url, base_domain, base_scheme, result, visited, queue, semaphore
            )
        else:
            # Обычный aiohttp краулинг
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                **self.extra_headers,
            }

            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                # Сначала парсим robots.txt и sitemap.xml
                await self._fetch_robots_sitemap(
                    session, base_scheme, base_domain, result, visited, queue
                )

                while queue and not self._stop and len(visited) < self.max_pages:
                    # Берём пачку URL для параллельной обработки
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

        # Дедупликация
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
        """Парсить robots.txt и sitemap.xml для расширенного обнаружения."""
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

        # sitemap.xml (fallback, если в robots не указана)
        try:
            sitemap_url = f"{base}/sitemap.xml"
            await self._fetch_sitemap(session, sitemap_url, result, visited, queue, domain)
        except Exception as exc:
            logger.debug("sitemap.xml fetch error: %s", exc)

    async def _fetch_sitemap(
        self, session, sitemap_url: str, result: SpiderResult,
        visited: set, queue: list, domain: str,
    ) -> None:
        """Парсить sitemap.xml и добавлять URL в очередь."""
        try:
            async with session.get(sitemap_url, ssl=False, allow_redirects=True) as resp:
                if resp.status != 200:
                    return
                text = await resp.text(errors="replace")
                result.total_requests += 1
                # Ищем <loc>URL</loc>
                for match in re.finditer(r'<loc>\s*(https?://[^<]+)\s*</loc>', text):
                    url = match.group(1).strip()
                    if self._in_scope(url, domain):
                        norm = self._normalize_url(url)
                        if norm not in visited:
                            queue.append((url, 1))
                            result.endpoints.append(SpiderEndpoint(
                                url=url, source="sitemap", method="GET",
                            ))
                # Вложенные sitemap-индексы
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
                        # JS-файл — ищем API эндпоинты и добавляем в список
                        result.js_files.append(url)
                        endpoints = self._extract_js_endpoints(body, url)
                        result.endpoints.extend(endpoints)
                        # Из JS-эндпоинтов тоже извлекаем страницы для краулинга
                        js_page_links = [
                            ep.url for ep in endpoints
                            if ep.url.startswith("http")
                            and self._in_scope(ep.url, base_domain)
                        ]
                        return js_page_links

                    if "html" not in content_type and "text/plain" not in content_type:
                        return []

                    result.pages.append(url)

                    # Парсинг HTML
                    links, forms, js_links = self._parse_html(body, url, base_domain)

                    # Добавляем формы
                    result.forms.extend(forms)

                    # JS-файлы добавляем в очередь (было пустой pass — теперь работает!)
                    for js_url in js_links:
                        norm = self._normalize_url(js_url)
                        if js_url not in result.js_files:
                            result.js_files.append(js_url)

                    # Извлекаем параметры из URL текущей страницы
                    params = parse_qs(urlparse(url).query)
                    if params:
                        result.endpoints.append(SpiderEndpoint(
                            url=url,
                            source="param",
                            method="GET",
                            params=list(params.keys()),
                        ))

                    # Обнаруживаем path-параметры (числа и UUID в пути)
                    path_variants = self._extract_path_variants(url, base_domain)
                    for pv in path_variants:
                        if pv not in [ep.url for ep in result.endpoints]:
                            result.endpoints.append(SpiderEndpoint(
                                url=pv, source="path", method="GET",
                            ))

                    # Возвращаем ссылки + JS (JS тоже в очередь краулинга)
                    return links + js_links

            except asyncio.TimeoutError:
                result.errors.append(f"Timeout: {url}")
                return []
            except Exception as exc:
                result.errors.append(f"Error {url}: {exc}")
                return []

    # ── Playwright JS-рендеринг ───────────────────────────────────────────────

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
        """Краулинг с JavaScript-рендерингом через Playwright.

        Используется только если playwright установлен и js_render=True.
        Запускает Chromium в headless-режиме, загружает страницы, ждёт
        networkidle, затем извлекает HTML с выполненным JS.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright not available, falling back to aiohttp")
            # Fallback на aiohttp
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
        """Парсинг HTML: ссылки, формы, JS-файлы, data-атрибуты."""
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

        # <a href> и <link href>
        for tag in soup.find_all(["a", "link"], href=True):
            _add_link(tag.get("href", ""))

        # Все теги — ищем data-url / data-href / data-src / data-action
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

        # JS-файлы (<script src>)
        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            if src:
                abs_url = urljoin(page_url, src)
                if urlparse(abs_url).scheme in ("http", "https"):
                    js_links.append(abs_url)

        # inline <script> — ищем в них тоже
        for script in soup.find_all("script", src=False):
            inline = script.get_text(strip=True)
            if inline and len(inline) > 20:
                endpoints = self._extract_js_endpoints(inline, page_url)
                for ep in endpoints:
                    if ep.url.startswith("http") and self._in_scope(ep.url, base_domain):
                        _add_link(ep.url)

        # Формы
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
                # Пропускаем кнопки и hidden-поля без значения
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
        """Извлечь API-эндпоинты из JS-кода."""
        endpoints: list[SpiderEndpoint] = []
        seen: set[str] = set()

        parsed_base = urlparse(js_url)
        base = f"{parsed_base.scheme}://{parsed_base.netloc}"

        for pattern in _JS_API_PATTERNS:
            for match in pattern.finditer(js_content):
                path = match.group(1).strip()
                if not path or len(path) > 300:
                    continue
                # Игнорируем явно не URL
                if any(c in path for c in [" ", "\n", "\t"]):
                    continue
                if path.startswith(("http://", "https://")):
                    full_url = path
                elif path.startswith("/"):
                    full_url = base + path
                else:
                    # Относительный путь
                    try:
                        full_url = urljoin(js_url, path)
                    except Exception:
                        continue

                # Убираем фрагменты
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
        """Обнаружить URL-варианты с path-параметрами для тестирования.

        Пример: /api/users/123/profile → /api/users/INJECT/profile
        Возвращаем URL с числовыми/UUID сегментами как потенциальные точки инъекции.
        """
        variants: list[str] = []
        parsed = urlparse(url)
        path = parsed.path

        # Ищем числа и UUID в path
        for match in _PATH_SEGMENT_RE.finditer(path):
            segment = match.group(1)
            # Создаём вариант с маркером вместо сегмента — для передачи в checks
            # Храним как SpiderEndpoint.url с оригинальным сегментом
            variants.append(url)

        return variants

    # ── utilities ─────────────────────────────────────────────────────────────

    def _normalize_url(self, url: str) -> str:
        """Нормализовать URL (убрать фрагмент, trailing slash)."""
        try:
            parsed = urlparse(url)
            normalized = parsed._replace(fragment="")
            result = normalized.geturl()
            return result.rstrip("/")
        except Exception:
            return url

    def _in_scope(self, url: str, base_domain: str) -> bool:
        """Проверить, что URL в скоупе (тот же домен или поддомен)."""
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc
            if not netloc:
                return True
            # Точное совпадение или поддомен
            return netloc == base_domain or netloc.endswith(f".{base_domain}")
        except Exception:
            return False


__all__ = ["AsyncSpider", "SpiderResult", "SpiderForm", "FormField", "SpiderEndpoint"]
