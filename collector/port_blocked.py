"""Blocked-port detection from inventory owner + transmitState and session CP."""

from __future__ import annotations


def is_port_owned(owner: str) -> bool:
    """True when the port has a non-free owner (cases 1–3 apply)."""
    label = (owner or "").strip()
    if not label:
        return False
    return label.casefold() != "free"


def compute_blocked(*, owner: str, transmit_state: str, cp: bool | None) -> bool:
    """
    Derive blocked flag from owner, transmitState, and CP.

    Owned port not assigned to any IxNetwork session (``cp is None``) → not evaluated
    here; join sets ``blocked=None`` (unknown).
    Case 1 — owned, in session, transmitState 0, CP False  → blocked (reserved, no traffic)
    Case 2 — owned, in session, transmitState 0, CP True   → in use (control plane)
    Case 3 — owned, in session, transmitState 1            → in use (chassis transmit active)

    DP and utilization are collected from Session Explorer and always shown on joined
    rows; they do not change the blocked flag (only owner, transmitState, and CP do).
    No owner / Free owner                                → not blocked
    """
    if not is_port_owned(owner):
        return False
    if cp is None:
        return False

    ts = str(transmit_state).strip()
    if ts == "1":
        return False
    if ts == "0":
        return not cp
    return False


def compute_blocked_without_session(*, owner: str, transmit_state: str) -> bool | None:
    """
    Blocked when port is owned on chassis but not in any IxNetwork session.

    transmitState ``1`` (e.g. Windows clients with active chassis transmit) → ``False``.
    transmitState ``0`` or unknown → ``None`` (cannot determine without session CP).
    Unowned / Free / omitted owner → ``False`` (available, not hogging).
    """
    if not is_port_owned(owner):
        return False
    if str(transmit_state).strip() == "1":
        return False
    return None
