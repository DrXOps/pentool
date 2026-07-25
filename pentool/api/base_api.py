"""ExportableAPI — base mixin for API classes supporting project persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ExportableAPI(ABC):
    """Mixin for API classes that support project data export/import.

    Subclasses must implement export_project_data and import_project_data.
    These methods are called by core.project.save_project/load_project.

    Usage::

        class MyAPI(ExportableAPI):
            def export_project_data(self) -> dict:
                return {"my_data": [...]}

            def import_project_data(self, data: dict) -> int:
                items = data.get("my_data", [])
                # restore items
                return len(items)
    """

    @abstractmethod
    def export_project_data(self) -> dict:
        """Export module state to a serializable dict.

        Returns:
            dict: Module-specific data structure (e.g., {"results": [...]}).
                  Must be JSON-serializable (no datetime, use .isoformat()).
        """
        raise NotImplementedError

    @abstractmethod
    def import_project_data(self, data: dict) -> int | tuple[int, str]:
        """Import module state from a loaded project dict.

        Args:
            data: The module's block from project.json (e.g., data["intruder"]).

        Returns:
            int: Number of items loaded successfully.
            OR
            tuple[int, str]: (count, error_message) — empty string if OK.
        """
        raise NotImplementedError
