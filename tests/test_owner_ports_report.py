"""Unit tests for owner-report formatting."""

from collector.true_port_utilization import (
    TruePortUtilRecord,
    format_owner_ports_report,
)


def _record(**kwargs) -> TruePortUtilRecord:
    defaults = dict(
        chassis="10.0.0.1",
        port="1.1",
        owner="IxNetwork/admin",
        transmit_state="0",
        cp=False,
        dp=False,
        utilization=False,
        blocked=True,
    )
    defaults.update(kwargs)
    return TruePortUtilRecord(**defaults)


def test_default_report_blocked_only():
    records = [
        _record(port="1.1", blocked=True),
        _record(port="1.2", blocked=False, cp=True, utilization=True),
        _record(port="1.3", owner="Free", blocked=False),
    ]
    out = format_owner_ports_report(records)
    assert "1 blocked port(s)" in out
    assert "1.1" in out
    assert "1.2" not in out


def test_all_owned_includes_utilized_not_blocked():
    records = [
        _record(port="1.1", blocked=True),
        _record(
            port="1.2",
            blocked=False,
            cp=True,
            utilization=True,
            transmit_state="1",
        ),
        _record(port="1.3", owner="Free", blocked=False),
    ]
    out = format_owner_ports_report(records, all_owned=True)
    assert "2 owned port(s)" in out
    assert "1.1" in out
    assert "1.2" in out
    header = out.splitlines()[1]
    assert "transmitState" in header
    assert "dp" in header
    assert "utilization" in header
    assert "blocked" in header
    assert "1.3" not in out
