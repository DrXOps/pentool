"""ScannerAPI — public Scanner interface for TUI and CLI."""

from __future__ import annotations

import asyncio
from typing import Callable

from pentool.core.utils import run_async_sync

from pentool.core.logging import get_logger
from pentool.modules.scanner.base import BaseCheck, Finding
from pentool.modules.scanner.checks import (
    InfoLeakCheck,
    LFICheck,
    MissingSecurityHeadersCheck,
    OpenRedirectCheck,
    PathTraversalCheck,
    HeaderInjectionCheck,
    RCECheck,
    SQLiCheck,
    SSTICheck,
    SSRFCheck,
    XSSCheck,
    XXECheck,
    CORSCheck,
    BrokenAuthCheck,
    JWTNoneCheck,
    NoSQLInjectionCheck,
    GraphQLCheck,
    PrototypePollutionCheck,
    DOMXSSCheck,
    OAuthCheck,
    SensitiveDataCheck,
)
from pentool.modules.scanner.checks.header_injection import HostHeaderInjectionCheck
from pentool.modules.scanner.checks.sqli import SQLiUnionCheck
from pentool.modules.scanner.engine import ScanEngine
from pentool.modules.scanner.passive import PassiveScanner
from pentool.modules.scanner.report import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
)

from pentool.api.base_api import ExportableAPI

logger = get_logger(__name__)

__all__ = ["ScannerAPI", "Finding", "BaseCheck"]


class ScannerAPI(ExportableAPI):

    def __init__(self, db_path: str = "", http_client=None) -> None:
        self._db_path = db_path
        self._http_client = http_client
        self._engine: ScanEngine | None = None
        self._passive: PassiveScanner | None = None
        self._active_task: asyncio.Task | None = None
        self._scan_id: str | None = None

    def _get_engine(self) -> ScanEngine:
        if self._engine is None:
            self._engine = ScanEngine(
                db_path=self._db_path,
                http_client=self._http_client,
            )
            self._engine.register_checks([
                MissingSecurityHeadersCheck(),
                InfoLeakCheck(),
                SQLiCheck(),
                XSSCheck(),
                SSTICheck(),
                LFICheck(),
                PathTraversalCheck(),
                HeaderInjectionCheck(),
                HostHeaderInjectionCheck(),
                RCECheck(),
                OpenRedirectCheck(),
                SSRFCheck(),
                XXECheck(),
                CORSCheck(),
                BrokenAuthCheck(),
                JWTNoneCheck(),
                NoSQLInjectionCheck(),
                GraphQLCheck(),
                PrototypePollutionCheck(),
                DOMXSSCheck(),
                OAuthCheck(),
                SensitiveDataCheck(),
                SQLiUnionCheck(),
            ])
        return self._engine

    async def start_active_scan(
        self,
        targets: list[str],
        check_names: list[str] | None = None,
        on_finding: Callable[[Finding | None, None]] = None,
        on_progress: Callable[[int, int | None, None]] = None,
        on_request: Callable[[str, str | None, None]] = None,
        concurrency: int = 5,
        request_delay: float = 0.0,
    ) -> str:
        import uuid
        self._scan_id = str(uuid.uuid4())
        engine = self._get_engine()
        engine._concurrency = concurrency
        engine._request_delay = request_delay

        async def _run() -> None:
            findings = await engine.run_active(
                targets,
                check_names=check_names,
                on_finding=on_finding,
                on_progress=on_progress,
                on_request=on_request,
            )
            await engine.save_findings(findings)

        self._active_task = asyncio.create_task(_run())
        return self._scan_id

    async def stop_scan(self) -> None:
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass
        self._active_task = None

    def is_scanning(self) -> bool:
        return bool(self._active_task and not self._active_task.done())

    async def get_findings(self, limit: int = 200) -> list[Finding]:
        return await self._get_engine().get_findings(limit)

    async def mark_false_positive(self, finding_id: str) -> None:
        await self._get_engine().mark_false_positive(finding_id)

    async def attach_passive(self, proxy_api=None) -> None:
        engine = self._get_engine()
        self._passive = PassiveScanner(engine)
        self._passive.attach_bus()
        logger.info("Passive scanner attached via EventBus")

    async def detach_passive(self) -> None:
        if self._passive:
            self._passive.detach_bus()
        self._passive = None

    def set_passive_callback(self, callback: Callable[[Finding], None]) -> None:
        if self._passive:
            self._passive.on_finding = callback

    async def generate_report(self, path: str, fmt: str = "html") -> None:
        findings = await self.get_findings(limit=10000)
        fmt = fmt.lower()
        if fmt == "html":
            generate_html_report(findings, path)
        elif fmt == "json":
            generate_json_report(findings, path)
        elif fmt == "csv":
            generate_csv_report(findings, path)
        else:
            raise ValueError(f"Unknown report format: {fmt}")
        logger.info("Report generated: %s (%s)", path, fmt)

    def register_check(self, check: BaseCheck) -> None:
        self._get_engine().register_check(check)

    def get_registered_checks(self) -> list[BaseCheck]:
        return self._get_engine().get_registered_checks()

    # ── Project persistence ────────────────────────────────────────────────────

    def export_project_data(self) -> dict:
        try:
            findings = run_async_sync(self.get_findings(limit=10_000), timeout=10)
        except Exception as exc:
            logger.warning("export_project_data: %s", exc)
            findings = []
        return {"findings": [f.to_dict() for f in (findings or [])]}

    def import_project_data(self, data: dict) -> int:
        findings_data = data.get("findings", [])
        if not findings_data:
            return 0

        findings = []
        for fd in findings_data:
            try:
                findings.append(Finding.from_dict(fd))
            except Exception as exc:
                logger.warning("ScannerAPI.import_project_data: skip finding: %s", exc)

        if not findings:
            return 0

        # Write to SQLite via save_findings (requires async context)
        engine = self._get_engine()
        try:
            run_async_sync(engine.save_findings(findings), timeout=15)
            return len(findings)
        except Exception as exc:
            logger.warning("import_project_data save_findings: %s", exc)
            return 0

    async def get_stats(self) -> dict:
        return await self._get_engine().get_stats()

    async def get_host_count(self) -> int:
        try:
            from pentool.storage.http_storage import HttpStorage
            storage = HttpStorage()
            await storage.init_db(self._db_path)
            try:
                return await storage.count_distinct_hosts()
            finally:
                await storage.close()
        except Exception as exc:
            logger.debug("ScannerAPI.get_host_count: %s", exc)
            return 0

    async def get_history_requests(
        self,
        scope_host: str = "",
        limit: int = 500,
    ) -> list:
        from pentool.storage.http_storage import HttpStorage
        from pentool.utils.parser import ParsedRequest
        import re as _re

        storage = HttpStorage()
        try:
            await storage.init_db(self._db_path)
            entries = await storage.export_all_requests(limit=limit)
        finally:
            await storage.close()

        seen: set[str] = set()
        result: list[ParsedRequest] = []

        for entry in entries:
            url: str = entry.get("url", "") or ""
            method: str = (entry.get("method", "GET") or "GET").upper()
            if not url:
                continue
            if scope_host and scope_host not in url:
                continue
            # Deduplicate by (method, path without parameter values)
            path_tmpl = _re.sub(r"=[^&]*", "=", url.split("?")[0])
            dedup_key = f"{method}:{path_tmpl}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            headers: dict = entry.get("request_headers", {}) or {}
            body: str = entry.get("request_body", "") or ""
            result.append(ParsedRequest(
                method=method,
                url=url,
                headers=headers,
                body=body,
            ))

        return result

    # ── Tab state persistence ──────────────────────────────────────────────────

    async def save_tab(self, tab_name: str, target_url: str) -> None:
        """Save scanner tab state (name, target URL) to DB."""
        if not self._db_path:
            return
        from pentool.core.database import get_db

        async with get_db(self._db_path) as db:
            # Check if tab already exists
            cursor = await db.execute(
                "SELECT id FROM scanner_tabs WHERE tab_name = ?",
                (tab_name,),
            )
            row = await cursor.fetchone()
            if row:
                # Update existing tab
                await db.execute(
                    """UPDATE scanner_tabs SET target_url = ?, updated_at = datetime('now')
                       WHERE tab_name = ?""",
                    (target_url, tab_name),
                )
            else:
                # Insert new tab
                await db.execute(
                    """INSERT INTO scanner_tabs (tab_name, target_url, updated_at)
                       VALUES (?, ?, datetime('now'))""",
                    (tab_name, target_url),
                )
            await db.commit()

    async def get_tabs(self) -> list[dict]:
        """Load all scanner tabs from DB."""
        if not self._db_path:
            return []
        from pentool.core.database import get_db

        async with get_db(self._db_path) as db:
            cursor = await db.execute(
                "SELECT tab_name, target_url FROM scanner_tabs ORDER BY updated_at DESC"
            )
            rows = await cursor.fetchall()
            return [{"tab_name": row[0], "target_url": row[1]} for row in rows]

    async def delete_tab(self, tab_name: str) -> None:
        """Delete scanner tab from DB."""
        if not self._db_path:
            return
        from pentool.core.database import get_db

        async with get_db(self._db_path) as db:
            await db.execute("DELETE FROM scanner_tabs WHERE tab_name = ?", (tab_name,))
            await db.commit()
