"""Unit tests for Influx point mapping (no live Influx required)."""

from collector.influx_writer import record_to_point
from collector.true_port_utilization import TruePortUtilRecord


def test_record_to_point_tags_and_fields():
    record = TruePortUtilRecord(
        chassis="10.0.0.1",
        port="6.3",
        owner="IxNetwork/admin",
        transmit_state="0",
        cp=False,
        dp=False,
        utilization=False,
        blocked=True,
    )
    point = record_to_point(record)
    payload = point.to_line_protocol()
    assert "chassis_id=10.0.0.1" in payload
    assert "port_id=6.3" in payload
    assert "owner=IxNetwork/admin" in payload
    assert "blocked=1i" in payload
    assert "is_hogging=1i" in payload
    assert "cp=0i" in payload


def test_free_port_no_owner_tag():
    record = TruePortUtilRecord(
        chassis="10.0.0.1",
        port="1.1",
        owner="Free",
        transmit_state="0",
        cp=False,
        dp=False,
        utilization=False,
        blocked=False,
    )
    payload = record_to_point(record).to_line_protocol()
    assert "owner=" not in payload
    assert "blocked=0i" in payload
