"""Blocked-port detection from inventory owner + transmitState and session CP."""

from __future__ import annotations


def is_port_owned(owner: str) -> bool:
    """True when the port has a non-free owner (cases 1–3 apply)."""
    label = (owner or "").strip()
    if not label:
        return False
    return label.casefold() != "free"


def compute_blocked(*, owner: str, transmit_state: str, cp: bool) -> bool:
    """
    Derive blocked flag from owner, transmitState, and CP.

    Case 1 — owned, transmitState 0, CP False  → blocked (reserved, no traffic)
    Case 2 — owned, transmitState 0, CP True   → in use (control plane)
    Case 3 — owned, transmitState 1             → in use (data plane)
    No owner / Free owner                       → not blocked
    """
    if not is_port_owned(owner):
        return False

    ts = str(transmit_state).strip()
    if ts == "1":
        return False
    if ts == "0":
        return not cp
    return False
