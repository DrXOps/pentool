"""Public API of the repeater module for TUI and CLI."""

from __future__ import annotations



from pentool.modules.repeater import Repeater, RepeaterEntry
from pentool.utils.parser import ParsedRequest, ParsedResponse
from pentool.api.base_api import ExportableAPI

# Re-export types
__all__ = ["RepeaterAPI", "RepeaterEntry"]


class RepeaterAPI(ExportableAPI):

    def __init__(
        self,
        db_path: str,
        project_id: int | None = None,
        timeout: float = 30.0,
        verify_ssl: bool = False,
    ) -> None:
        self._repeater = Repeater(
            db_path=db_path,
            project_id=project_id,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

    async def send(
        self,
        request: ParsedRequest,
        tab_name: str = "Tab",
        save: bool = True,
    ) -> ParsedResponse:
        return await self._repeater.send(request, tab_name=tab_name, save=save)

    async def save_to_history(
        self,
        request: ParsedRequest,
        response: ParsedResponse,
        tab_name: str = "Tab",
    ) -> int:
        return await self._repeater.save_to_history(request, response, tab_name)

    async def get_history(
        self,
        limit: int = 50,
        project_id: int | None = None,
    ) -> list[RepeaterEntry]:
        return await self._repeater.get_history(limit=limit, project_id=project_id)

    async def get_entry(self, entry_id: int) -> RepeaterEntry | None:
        return await self._repeater.get_entry(entry_id)

    async def delete_entry(self, entry_id: int) -> None:
        return await self._repeater.delete_entry(entry_id)

    def export_project_data(self) -> dict:
        """Export repeater history is handled via DB — no in-memory state to serialize."""
        return {"repeater": {}}

    def import_project_data(self, data: dict) -> int:
        """Repeater history is loaded from DB on demand — nothing to restore here."""
        return 0
