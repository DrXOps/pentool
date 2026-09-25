"""IntruderResultsTable — DataTable для результатов атак Intruder.

Наследует ArrowBackendDataTable, добавляет:
- Поддержку извлечения/удаления колонки "Extract"
- Numeric sort key для числовых колонок
"""

from __future__ import annotations

import re

import pyarrow as pa
from textual_fastdatatable import ArrowBackend

from pentool.tui.widgets.data_table import ArrowBackendDataTable


class IntruderResultsTable(ArrowBackendDataTable):
    """DataTable для результатов Intruder с извлечением данных и числовой сортировкой.

    Динамически добавляет/удаляет колонку "Extract" для Grep-Extract.
    """

    _NUMERIC_SORT_COLS = {0, 2, 3, 4}  # #, Status, Length, Time(ms)

    _COL_WIDTHS: dict[str, int] = {
        "#": 5, "Payload(s)": 45, "Status": 8, "Length": 10, "Time(ms)": 10, "Error": 30,
    }

    def __init__(self, columns: list[str] | None = None, *args, **kwargs) -> None:  # noqa: ANN002
        # textual_fastdatatable не рендерит заголовки колонок в пустой таблице
        # (ArrowBackend не знает ширину). Добавляем одну фиктивную строку
        # при инициализации, чтобы колонки появились визуально.
        # В дальнейшем _redraw_results / add_rows перезапишут данные.
        super().__init__(columns=columns, *args, **kwargs)
        self._has_extract: bool = False
        if columns:
            import pyarrow as pa
            sample = {}
            for c in columns:
                sample[c] = pa.array([""], type=pa.string())
            self.backend = ArrowBackend(pa.table(sample))
            self._arrow_data = pa.table(sample)
            self.refresh()

    def add_extract_column(self) -> None:
        """Добавить колонку Extract (перестраивает backend с пустыми значениями)."""
        if self._has_extract:
            return
        if self._arrow_data is not None:
            current = self._arrow_data
            extract_col = pa.nulls(current.num_rows, type=pa.string())
            new_arrow = current.append_column("Extract", extract_col)
            self.set_data(new_arrow)
            self._columns.append("Extract")
        self._has_extract = True

    def remove_extract_column(self) -> None:
        """Удалить колонку Extract (перестраивает backend)."""
        if not self._has_extract:
            return
        if self._arrow_data is not None and "Extract" in self._arrow_data.column_names:
            new_arrow = self._arrow_data.drop(["Extract"])
            self.set_data(new_arrow)
            self._columns = [c for c in self._columns if c != "Extract"]
        self._has_extract = False

    def add_row(self, *values: object, key: object = None) -> None:
        """Добавить одну строку через add_rows().

        ArrowBackendDataTable не имеет add_row(), только add_rows(records).
        Этот метод оборачивает одну строку в список и вызывает add_rows.
        """
        import logging
        try:
            self.add_rows([values])
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "IntruderResultsTable.add_row failed: %s", exc
            )

    @staticmethod
    def _numeric_sort_key(raw: object) -> int:
        """Извлекает int из Rich-markup ячейки для правильной числовой сортировки."""
        text = re.sub(r"\[/?[^\]]+\]", "", str(raw)).replace("✓", "").strip()
        m = re.search(r"-?\d+", text)
        return int(m.group(0)) if m else -1