"""IntruderStorage — DEPRECATED. Import from `pentool.storage.intruder_storage` instead.

This file remains as a proxy for backward compatibility. New code must import
from `pentool.storage.intruder_storage` directly.
"""

from __future__ import annotations

import warnings

from pentool.storage.intruder_storage import IntruderStorage  # noqa: F401

warnings.warn(
    "Import from pentool.api.intruder_storage is deprecated. "
    "Use pentool.storage.intruder_storage instead.",
    DeprecationWarning,
    stacklevel=2,
)