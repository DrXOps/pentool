"""IntruderResultsTable — DataTable для результатов атак Intruder.

Наследует ArrowBackendDataTable (widgets/data_table.py), добавляет:
- Стандартную конфигурацию колонок
- Параметры отображения, совпадающие с аналогичными таблицами в проекте
"""

from __future__ import annotations

from pentool.tui.widgets.data_table import ArrowBackendDataTable


_RESULTS_COL_NAMES = ["#", "Payload(s)", "Status", "Length", "Time(ms)", "Error"]
_RESULTS_COL_WIDTHS = [5, 45, 8, 10, 10, 30]


class IntruderResultsTable(ArrowBackendDataTable):
    """DataTable для результатов Intruder, как ProxyDataTable для Proxy.

    Не задаёт колонки и ширины жёстко — они передаются снаружи
    при compose, аналогично ProxyDataTable.
    """

    pass