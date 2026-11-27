"""Project schema and project-level settings — TUI's only door to the database schema.

TUI screens (`app`, `project_manager`, the Proxy screen's scope) need three schema-level
operations: create a project database, read and write a project setting. Importing
`pentool.core.db_schema` from `pentool.tui` put the data layer straight into the UI — the
layer guard (`tools/check_layers.py`) now forbids that. This module is the service-layer
façade the guard expects: the UI asks a service, the service owns the schema calls.

The module is imported (not the functions) so tests that patch
`pentool.core.db_schema.get_project_setting` keep working.
"""

from __future__ import annotations

from pentool.core import db_schema


async def init_project_db(db_path: str) -> None:
    """Create the schema of a new project database."""
    await db_schema.init_db(db_path)


async def get_setting(db_path: str, key: str, default: str | None = None) -> str | None:
    """Read one project setting; `default` when the key was never written."""
    return await db_schema.get_project_setting(db_path, key, default)


async def set_setting(db_path: str, key: str, value: str) -> None:
    """Write one project setting (upsert)."""
    await db_schema.set_project_setting(db_path, key, value)
