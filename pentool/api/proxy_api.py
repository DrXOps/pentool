"""Публичный API прокси-модуля для TUI и CLI."""

from __future__ import annotations

from typing import Callable

from pentool.modules.proxy import InterceptedRequest, MatchReplaceRule, ProxyServer
from pentool.core.logging import get_logger

logger = get_logger(__name__)

# Реэкспорт типов — TUI импортирует их отсюда, не из modules.proxy
__all__ = ["ProxyAPI", "InterceptedRequest", "MatchReplaceRule", "ProxyServer"]


class ProxyAPI:

    def __init__(self) -> None:
        self._proxy: ProxyServer | None = None

    def set_proxy(self, proxy: ProxyServer) -> None:
        logger.debug("ProxyAPI: set_proxy called, proxy=%s", proxy)
        self._proxy = proxy

    def get_proxy(self) -> ProxyServer | None:
        return self._proxy

    @property
    def proxy(self) -> ProxyServer | None:
        """Легитимный доступ к ProxyServer через API-слой.

        Используется там где нужен прямой доступ к серверу
        (proxy/screen.py для intercept, repeater/screen.py для scope).
        """
        return self._proxy

    def create_proxy(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        cert_dir: str = "/tmp/pentool_certs",
        db_path: str | None = None,
    ) -> ProxyServer:
        proxy = ProxyServer(host=host, port=port, cert_dir=cert_dir, db_path=db_path)
        self._proxy = proxy
        return proxy

    def is_running(self) -> bool:
        return bool(self._proxy and self._proxy.is_running)

    def get_port(self) -> int:
        if self._proxy:
            return self._proxy.port
        return 8080

    def get_host(self) -> str:
        if self._proxy:
            return self._proxy.host
        return "127.0.0.1"

    def get_status(self) -> dict:
        if self._proxy is None:
            return {
                "running": False,
                "host": "127.0.0.1",
                "port": 8080,
                "intercept_enabled": False,
                "scope": [],
                "rules_count": 0,
                "requests_count": 0,
                "waiting_count": 0,
            }
        return self._proxy.get_status()

    def get_requests(
        self,
        limit: int = 100,
        method: str | None = None,
        host: str | None = None,
    ) -> list[InterceptedRequest]:
        if self._proxy is None:
            return []
        return self._proxy.get_requests(limit=limit, method=method, host=host)

    def find_request(self, req_id: str) -> InterceptedRequest | None:
        """Найти запрос по ID.

        Args:
            req_id: UUID запроса (полный или частичный).

        Returns:
            InterceptedRequest или None.
        """
        if self._proxy is None:
            return None
        return self._proxy._find_request(req_id)

    def clear_requests(self) -> None:
        if self._proxy:
            self._proxy.clear_requests()

    def forward(self, req_id: str, modified_raw: str | None = None) -> None:
        """Переслать ожидающий запрос на целевой сервер.

        Args:
            req_id: ID перехваченного запроса.
            modified_raw: Изменённый сырой HTTP-текст (опционально).

        Returns:
            None

        Raises:
            RuntimeError: Если прокси не инициализирован.
        """
        if self._proxy is None:
            raise RuntimeError("ProxyAPI: прокси не инициализирован")
        logger.debug("ProxyAPI: forward req_id=%s, has_modified=%s", req_id, bool(modified_raw))
        self._proxy.forward(req_id, modified_raw)

    def drop(self, req_id: str) -> None:
        """Сбросить ожидающий запрос (вернуть браузеру 502).

        Args:
            req_id: ID перехваченного запроса.

        Returns:
            None

        Raises:
            RuntimeError: Если прокси не инициализирован.
        """
        if self._proxy is None:
            raise RuntimeError("ProxyAPI: прокси не инициализирован")
        logger.debug("ProxyAPI: drop req_id=%s", req_id)
        self._proxy.drop(req_id)

    def set_intercept(self, enabled: bool) -> None:
        if self._proxy:
            # ProxyServer.set_intercept() использует call_soon_threadsafe —
            # обязательно для безопасного изменения флага из TUI-треда,
            # пока proxy-loop работает в своём asyncio-треде.
            self._proxy.set_intercept(enabled)

    def get_intercept(self) -> bool:
        return bool(self._proxy and self._proxy.intercept_enabled)

    def set_scope(self, hosts: list[str]) -> None:
        if self._proxy:
            self._proxy.set_scope(hosts)

    def get_scope(self) -> list[str]:
        if self._proxy:
            return list(self._proxy.scope)
        return []

    def get_match_replace_rules(self) -> list[MatchReplaceRule]:
        if self._proxy:
            return list(self._proxy.match_replace_rules)
        return []

    def set_match_replace_rules(self, rules: list[MatchReplaceRule]) -> None:
        """Заменить все правила match/replace.

        Args:
            rules: Новый список правил MatchReplaceRule.

        Returns:
            None
        """
        if self._proxy:
            self._proxy.match_replace_rules = rules

    def export_project_data(self) -> dict:
        if self._proxy is None:
            return {"proxy": {"scope": [], "match_replace": []}, "http_history": []}

        return {
            "proxy": {
                "scope": list(self._proxy.scope),
                "match_replace": [r.to_dict() for r in self._proxy.match_replace_rules],
            },
            "http_history": [r.to_dict() for r in self._proxy.get_requests(limit=10000)],
        }

    def import_project_data(self, data: dict) -> tuple[int, str]:
        if self._proxy is None:
            return 0, "Proxy not initialized"

        from pentool.utils.parser import ParsedResponse
        from datetime import datetime, timezone

        # Scope
        self._proxy.scope = data.get("proxy", {}).get("scope", [])

        # Match/Replace
        mr_data = data.get("proxy", {}).get("match_replace", [])
        self._proxy.match_replace_rules = [MatchReplaceRule.from_dict(r) for r in mr_data]

        # HTTP History
        self._proxy.requests.clear()
        loaded = 0
        for req_data in data.get("http_history", []):
            try:
                req = InterceptedRequest.from_dict(req_data)
                self._proxy.requests.append(req)
                loaded += 1
            except Exception as e:
                logger.warning("import_project_data: failed to restore request: %s", e)

        return loaded, ""
