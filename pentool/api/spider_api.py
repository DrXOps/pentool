"""SpiderAPI — public Spider module interface for TUI and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from pentool.api.base_api import ExportableAPI
from pentool.core.logging import get_logger
from pentool.modules.spider import DEFAULT_CONCURRENCY, DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from pentool.modules.spider import (
    AsyncSpider,
    SpiderEndpoint,
    SpiderForm,
    SpiderResult,
    is_playwright_available,
    shutdown_proc_pool,
)
from pentool.utils.auth_headers import extract_auth_headers

logger = get_logger(__name__)


def shutdown_spider_pool() -> None:
    """API-level wrapper so the TUI can shut the Spider CPU pool down without
    importing ``pentool.modules`` directly (architecture layer rule)."""
    shutdown_proc_pool()

# Re-export types — TUI uses them from here
__all__ = [
    "SpiderAPI", "SpiderResult", "SpiderForm", "SpiderEndpoint", "SpiderConfig",
    "is_playwright_available",
]


@dataclass
class SpiderConfig:
    """Crawler configuration."""
    # Defaults come from the single source (pentool.modules.spider) so the
    # crawl depth/pages/concurrency aren't copy-pasted across modules.
    max_depth: int = DEFAULT_MAX_DEPTH
    max_pages: int = DEFAULT_MAX_PAGES
    concurrency: int = DEFAULT_CONCURRENCY
    timeout: float = 10.0
    user_agent: str = "pentool/1.0"
    respect_scope: bool = True   # stay on the target host/subdomains — don't crawl external links
    js_render: bool = False  # Playwright JS rendering (if installed)


class SpiderAPI(ExportableAPI):

    def __init__(self, config: SpiderConfig | None = None) -> None:
        self._config = config or SpiderConfig()
        self._spider: AsyncSpider | None = None
        self._stop_requested = False

    @classmethod
    def from_params(
        cls,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_pages: int = DEFAULT_MAX_PAGES,
        concurrency: int = 5,
        timeout: float = 10.0,
    ) -> "SpiderAPI":
        """Convenience factory method."""
        return cls(SpiderConfig(
            max_depth=max_depth,
            max_pages=max_pages,
            concurrency=concurrency,
            timeout=timeout,
        ))

    async def crawl(
        self,
        url: str,
        on_page: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        extra_headers: dict | None = None,
        db_path: str | None = None,
    ) -> SpiderResult:
        self._stop_requested = False
        cfg = self._config

        # Auto-discover an already-authenticated session for this host from
        # Proxy's HTTP History, so Spider doesn't crawl protected areas
        # "blind" (e.g. DVWA's /vulnerabilities/* redirecting to /login.php
        # for every request without a valid PHPSESSID cookie). This is
        # fully automatic — no manual cookie entry: the user just browses
        # the target through Proxy once, then crawling picks up whatever
        # Cookie/Authorization/etc. header Proxy last captured for that
        # host. Explicit `extra_headers` (e.g. from a Scanner seed request)
        # still wins on key conflicts — this is only a fallback for when
        # nothing more specific was supplied.
        discovered = await self._discover_auth_headers(url, db_path) if db_path else {}
        merged_headers = {**discovered, **(extra_headers or {})}

        self._spider = AsyncSpider(
            max_depth=cfg.max_depth,
            max_pages=cfg.max_pages,
            concurrency=cfg.concurrency,
            respect_scope=cfg.respect_scope,
            js_render=cfg.js_render,
            extra_headers=merged_headers,
        )
        if on_page:
            self._spider.on_page = on_page
        if on_progress:
            self._spider.on_progress = on_progress

        try:
            result = await self._spider.crawl(url)
            logger.info(
                "SpiderAPI.crawl: %s -> %d pages, %d forms, %d endpoints",
                url, len(result.pages), len(result.forms), len(result.endpoints),
            )
            return result
        except Exception as exc:
            logger.warning("SpiderAPI.crawl error for %s: %s", url, exc)
            return SpiderResult(pages=[], forms=[], endpoints=[], js_files=[], errors=[str(exc)])

    def stop(self) -> None:
        """Request crawling to stop."""
        self._stop_requested = True
        if self._spider is not None:
            try:
                self._spider._stop = True
            except Exception:
                pass

    async def _discover_auth_headers(self, url: str, db_path: str) -> dict:
        """Look up the most recent Proxy-captured request for this host and
        pull out any auth-looking headers (Cookie, Authorization, ...).

        Best-effort: opens a short-lived HttpStorage connection (same
        pattern as ScannerAPI.get_history_requests — a temp connection just
        for this one lookup, not the live Proxy connection), reads the
        single most recent row for the target host, and returns whatever
        extract_auth_headers() finds in its request_headers. Returns {} on
        any failure (no project DB yet, host never seen, corrupt row,
        column missing on an old DB) — this is a convenience fallback, not
        a hard dependency; crawling must still work with no history at all.
        """
        try:
            host = urlparse(url).netloc
            if not host:
                return {}
            # Match Proxy/Target's own scope-matching convention: compare
            # by hostname only, ignoring port (see utils/scope.py — Proxy
            # already strips ports before comparing hosts).
            bare_host = host.split(":")[0]

            from pentool.storage.http_storage import HttpStorage
            storage = HttpStorage()
            try:
                await storage.init_db(db_path)
                rows = await storage.get_metadata_batch(
                    limit=1,
                    filters={"hosts": [bare_host]},
                    order_by="id",
                    desc=True,
                )
                if not rows:
                    return {}
                entry = await storage.get_full_entry(rows[0]["id"])
            finally:
                await storage.close()

            if not entry:
                return {}
            headers = entry.get("request_headers") or {}
            found = extract_auth_headers(headers)
            if found:
                logger.info(
                    "SpiderAPI: auto-discovered %d auth header(s) for %s from Proxy History",
                    len(found), bare_host,
                )
            return found
        except Exception as exc:
            logger.debug("SpiderAPI._discover_auth_headers: %s", exc)
            return {}

    @property
    def config(self) -> SpiderConfig:
        """Current crawler configuration (max_depth, max_pages, concurrency)."""
        return self._config

    def export_project_data(self) -> dict:
        """Spider results are transient — no persistent state to serialize."""
        return {"spider": {}}

    def import_project_data(self, data: dict) -> int:
        """Spider results are not restored between sessions."""
        return 0
