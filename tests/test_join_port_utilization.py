"""Tests for inventory + session join and N/A session metrics."""

from collector.ports_client import PortRecord
from collector.session_ports_client import SessionPortRecord
from collector.true_port_utilization import join_port_utilization


def test_owned_without_session_gets_na_and_not_blocked():
    inventory = [
        PortRecord(
            chassis_ip="10.0.0.1",
            port="3.1",
            owner="IxNetwork/admin",
            transmit_state="0",
            traffic_running=False,
        ),
    ]
    merged = join_port_utilization(inventory, sessions=[])
    row = merged[0]
    assert row.cp is None
    assert row.dp is None
    assert row.utilization is None
    assert row.blocked is None
    assert not row.in_session


def test_owned_in_session_can_be_blocked():
    inventory = [
        PortRecord(
            chassis_ip="10.0.0.1",
            port="3.1",
            owner="IxNetwork/admin",
            transmit_state="0",
            traffic_running=False,
        ),
    ]
    sessions = [
        SessionPortRecord(
            chassis_ip="10.0.0.1",
            port="3.1",
            cp=False,
            dp=False,
            utilization=False,
            ixnet_server="WIN-HOST",
            session_id="sess-42",
            session_name="lab-test",
        ),
    ]
    row = join_port_utilization(inventory, sessions)[0]
    assert row.cp is False
    assert row.blocked is True
    assert row.in_session
    assert row.session_display == "WIN-HOST/lab-test"


def test_owned_transmit_active_without_session_not_blocked():
    inventory = [
        PortRecord(
            chassis_ip="10.36.236.121",
            port="4.7",
            owner="IxNetwork/WIN-0TITARHGJ7D/Justin",
            transmit_state="1",
            traffic_running=True,
        ),
    ]
    row = join_port_utilization(inventory, sessions=[])[0]
    assert row.session_display == "N/A"
    assert row.cp is None
    assert row.blocked is False


def test_free_port_without_session_not_blocked():
    inventory = [
        PortRecord(
            chassis_ip="10.0.0.1",
            port="1.1",
            owner="Free",
            transmit_state="0",
            traffic_running=False,
        ),
    ]
    row = join_port_utilization(inventory, sessions=[])[0]
    assert row.cp is None
    assert row.utilization is None
    assert row.session_display == "N/A"
    assert row.blocked is False
    assert not row.in_session
