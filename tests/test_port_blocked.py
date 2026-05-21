"""Unit tests for blocked-port detection."""

from collector.port_blocked import compute_blocked, is_port_owned


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
