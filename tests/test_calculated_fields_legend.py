"""Legend documents all calculated columns for end users."""

from collector.true_port_utilization import (
    OWNER_REPORT_COLUMNS,
    TRUE_UTIL_COLUMNS,
    format_calculated_fields_legend,
)


def test_main_table_columns_include_dp_and_utilization():
    assert "dp" in TRUE_UTIL_COLUMNS
    assert "utilization" in TRUE_UTIL_COLUMNS
    assert TRUE_UTIL_COLUMNS.index("transmitState") < TRUE_UTIL_COLUMNS.index("dp")


def test_owner_report_columns_include_dp_and_utilization():
    assert "dp" in OWNER_REPORT_COLUMNS
    assert "utilization" in OWNER_REPORT_COLUMNS


def test_legend_mentions_dp_utilization_and_transmit_state():
    legend = format_calculated_fields_legend()
    assert "transmitState" in legend
    assert "dp" in legend
    assert "utilization" in legend
