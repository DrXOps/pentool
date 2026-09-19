"""ExportableAPI — base mixin for API classes supporting project persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ExportableAPI(ABC):
    """Mixin for API classes with export/import project data (save_project/load_project)."""

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
