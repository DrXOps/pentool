"""LargeBodyHandler — stores bodies > 1 MB on disk."""

from __future__ import annotations

from pathlib import Path

from pentool.core.logging import get_logger

logger = get_logger(__name__)

THRESHOLD = 1 * 1024 * 1024  # 1 MB


class LargeBodyHandler:
    """Saves/loads request/response bodies > THRESHOLD to/from disk.

    File name format: <row_id>_<kind>.bin
    where kind = 'req' | 'resp'
    """

    BASE_DIR: Path = Path("~/.config/pentool/bodies").expanduser()

    @classmethod
    def _path(cls, row_id: int, kind: str) -> Path:
        return cls.BASE_DIR / f"{row_id}_{kind}.bin"

    @classmethod
    def store(cls, row_id: int, kind: str, data: bytes) -> str:
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)
        p = cls._path(row_id, kind)
        p.write_bytes(data)
        return str(p)

    @classmethod
    def load(cls, path: str) -> bytes:
        return Path(path).read_bytes()

    @classmethod
    def load_batch(cls, paths: list[str | None]) -> dict[str, bytes]:
        """Load multiple large bodies in one batch.

        Avoids N+1 disk reads in export_all_requests. Returns a dict mapping
        path → bytes for every non-None, existing path. Missing paths are
        silently skipped (logged at debug).
        """
        result: dict[str, bytes] = {}
        for p in paths:
            if not p:
                continue
            try:
                result[p] = Path(p).read_bytes()
            except Exception as _e:
                logger.debug("LargeBodyHandler: batch load failed for %s: %s", p, _e)
        return result

    @classmethod
    def delete(cls, path: str) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("LargeBodyHandler.delete: failed to delete %s: %s", path, e)

    @classmethod
    def is_large(cls, data: str | bytes | None) -> bool:
        if data is None:
            return False
        size = len(data) if isinstance(data, bytes) else len(data.encode())
        return size > THRESHOLD
