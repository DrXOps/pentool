"""Guards for the one table factory (T-029).

The audit found seven `DataTable(...)` constructions with drifting defaults: fixed
widths per screen, content cap only in Proxy, flexible columns only in Proxy,
zebra stripes dropped somewhere. `make_table` is now the only place that decides
those defaults, so this test pins them.
"""

from __future__ import annotations

from pentool.tui.widgets.data_table import ArrowBackendDataTable
from pentool.tui.widgets.proxy_data_table import ProxyDataTable
from pentool.tui.widgets.table_factory import DEFAULT_MAX_COLUMN_CONTENT_WIDTH, make_table


def test_defaults_are_applied() -> None:
    table = make_table(["ID", "Host"], table_id="t1")

    assert table.id == "t1"
    assert table.cursor_type == "row", "a data table here is read, not edited"
    assert table.zebra_stripes is True
    assert table.header_height == 1
    assert table.max_column_content_width == DEFAULT_MAX_COLUMN_CONTENT_WIDTH
    assert type(table) is ArrowBackendDataTable


def test_fixed_widths_pin_the_first_column() -> None:
    table = make_table(["ID", "Host"], table_id="t2", widths=[5, 20])

    assert table.fixed_columns == 1
    # The widget keeps the widths in a private list (`_column_widths`), not an
    # attribute: `column_widths` is a constructor argument only.
    assert table._column_widths == [5, 20]


def test_no_widths_means_no_pinned_columns() -> None:
    table = make_table(["ID", "Host"], table_id="t3")

    assert table.fixed_columns == 0


def test_spare_columns_are_installed_per_instance() -> None:
    spare = {"Host": (14, 26), "URL": (20, None)}
    table = make_table(["ID", "Host", "URL"], table_id="t4", spare=spare)

    assert table.SPARE_COLUMNS == spare
    # Per instance, not on the class: another table must not inherit them.
    other = make_table(["ID", "Host"], table_id="t5")
    assert other.SPARE_COLUMNS == {}


def test_custom_table_class_is_respected() -> None:
    table = make_table(["ID"], table_id="t6", table_class=ProxyDataTable)

    assert type(table) is ProxyDataTable
