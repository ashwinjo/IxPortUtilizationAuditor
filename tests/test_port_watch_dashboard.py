"""Tests for port watch dashboard snapshot builder."""

from collector.port_blocked import is_port_owned
from collector.true_port_utilization import TruePortUtilRecord
from scripts.port_watch_dashboard import build_snapshot


def _record(
    *,
    chassis: str = "10.0.0.1",
    port: str = "1/1",
    owner: str = "alice",
    blocked: bool | None = False,
    cp: bool | None = False,
) -> TruePortUtilRecord:
    return TruePortUtilRecord(
        chassis=chassis,
        port=port,
        owner=owner,
        transmit_state="0",
        cp=cp,
        dp=False,
        utilization=False,
        blocked=blocked,
        ixnet_server="srv",
        session_name="sess",
    )


def test_build_snapshot_blocked_and_owned_sections():
    records = [
        _record(owner="alice", blocked=True),
        _record(owner="bob", blocked=False),
        _record(owner="Free", blocked=None),
    ]
    snap = build_snapshot(records, inventory_count=3, session_count=2)

    assert snap["blocked_count"] == 1
    assert snap["owned_count"] == 2
    assert len(snap["blocked"]["main_table"]) == 1
    assert snap["blocked"]["main_table"][0]["owner"] == "alice"
    assert snap["blocked"]["owner_columns"] == ["owner", "ports_hogged"]
    assert snap["blocked"]["owner_report"] == [
        {"owner": "alice", "ports_hogged": "1"},
    ]
    assert len(snap["all_owned"]["owner_report"]) == 2
    assert all(is_port_owned(r["owner"]) for r in snap["all_owned"]["owner_report"])


def test_build_snapshot_blocked_owner_summary_aggregates():
    records = [
        _record(port="1/1", owner="alice", blocked=True),
        _record(port="1/2", owner="alice", blocked=True),
        _record(port="2/1", owner="bob", blocked=True),
    ]
    snap = build_snapshot(records, inventory_count=3, session_count=3)

    assert snap["blocked"]["owner_report"] == [
        {"owner": "alice", "ports_hogged": "2"},
        {"owner": "bob", "ports_hogged": "1"},
    ]
