"""IntruderResultsTable — DataTable for Intruder attack results.

Inherits ArrowBackendDataTable (widgets/data_table.py) and adds:
- The standard column configuration
- Display parameters matching the equivalent tables elsewhere in the project
"""

from __future__ import annotations

from pentool.tui.widgets.data_table import ArrowBackendDataTable

_RESULTS_COL_NAMES = ["#", "Payload(s)", "Status", "Length", "Time(ms)", "Error"]
_RESULTS_COL_WIDTHS = [5, 45, 8, 10, 10, 30]


class IntruderResultsTable(ArrowBackendDataTable):
    """DataTable for Intruder results, the way ProxyDataTable serves Proxy.

    Does not hard-code columns and widths — they are passed in from outside
    at compose time, exactly like ProxyDataTable.
    """

    pass
