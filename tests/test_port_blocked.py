"""Unit tests for blocked-port detection."""

from collector.port_blocked import (
    compute_blocked,
    compute_blocked_without_session,
    is_port_owned,
)


def test_no_owner_not_blocked():
    assert not is_port_owned("")
    assert not is_port_owned("Free")
    assert not compute_blocked(owner="Free", transmit_state="0", cp=False)


def test_case1_blocked():
    assert compute_blocked(owner="IxNetwork/admin", transmit_state="0", cp=False)


def test_case2_cp_in_use():
    assert not compute_blocked(owner="IxNetwork/admin", transmit_state="0", cp=True)


def test_case3_dp_in_use():
    assert not compute_blocked(owner="IxNetwork/admin", transmit_state="1", cp=False)


def test_unowned_without_session_not_blocked():
    assert compute_blocked_without_session(owner="", transmit_state="0") is False
    assert compute_blocked_without_session(owner="Free", transmit_state="0") is False


def test_owned_not_in_session_transmit_idle_unknown():
    assert compute_blocked_without_session(
        owner="IxNetwork/WIN-0TITARHGJ7D/Justin",
        transmit_state="0",
    ) is None


def test_owned_not_in_session_transmit_active_not_blocked():
    """Windows-style: owned, no session row, transmitState 1 → not blocked."""
    assert compute_blocked_without_session(
        owner="IxNetwork/WIN-0TITARHGJ7D/Justin",
        transmit_state="1",
    ) is False
