"""SpiderAPI — публичный интерфейс Spider-модуля для TUI и CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pentool.core.logging import get_logger
from pentool.modules.spider import (
    AsyncSpider,
    SpiderEndpoint,
    SpiderForm,
    SpiderResult,
    is_playwright_available,
)

logger = get_logger(__name__)

# Реэкспорт типов — TUI использует их отсюда
__all__ = [
    "SpiderAPI", "SpiderResult", "SpiderForm", "SpiderEndpoint", "SpiderConfig",
    "is_playwright_available",
]


@dataclass
class SpiderConfig:
    """Конфигурация краулера."""
    max_depth: int = 3
    max_pages: int = 100
    concurrency: int = 5
    timeout: float = 10.0
    user_agent: str = "pentool/1.0"
    respect_scope: bool = False
    js_render: bool = False  # Playwright JS-рендеринг (если установлен)


class SpiderAPI:

    def __init__(self, config: SpiderConfig | None = None) -> None:
        self._config = config or SpiderConfig()
        self._spider: AsyncSpider | None = None
        self._stop_requested = False

    @classmethod
    def from_params(
        cls,
        max_depth: int = 3,
        max_pages: int = 100,
        concurrency: int = 5,
        timeout: float = 10.0,
    ) -> "SpiderAPI":
        """Удобный фабричный метод."""
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
    ) -> SpiderResult:
        self._stop_requested = False
        cfg = self._config
        self._spider = AsyncSpider(
            max_depth=cfg.max_depth,
            max_pages=cfg.max_pages,
            concurrency=cfg.concurrency,
            respect_scope=cfg.respect_scope,
            js_render=cfg.js_render,
            extra_headers=extra_headers or {},
        )
        if on_page:
            self._spider.on_page = on_page
        if on_progress:
            self._spider.on_progress = on_progress

        try:
            result = await self._spider.crawl(url)
            logger.info(
                "SpiderAPI.crawl: %s → %d pages, %d forms, %d endpoints",
                url, len(result.pages), len(result.forms), len(result.endpoints),
            )
            return result
        except Exception as exc:
            logger.warning("SpiderAPI.crawl error for %s: %s", url, exc)
            return SpiderResult(pages=[], forms=[], endpoints=[], js_files=[], errors=[str(exc)])

    def stop(self) -> None:
        """Запросить остановку краулинга."""
        self._stop_requested = True
        if self._spider is not None:
            try:
                self._spider._stop_requested = True
            except Exception:
                pass

    @property
    def config(self) -> SpiderConfig:
        """Текущая конфигурация краулера (max_depth, max_pages, concurrency)."""
        return self._config
