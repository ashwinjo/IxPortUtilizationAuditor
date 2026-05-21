"""Composite join key: inventory ``chassis_ip`` + ``port``."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ports_client import PortRecord
    from .session_ports_client import SessionPortRecord


def normalize_chassis_ip(value: str) -> str:
    """Strip whitespace; inventory and session must use the same chassis IP string."""
    return value.strip()


def normalize_port_label(label: str) -> str:
    """Canonical ``card.port`` label (dot-separated) for cross-API joins."""
    label = label.strip()
    if "/" in label:
        return label.replace("/", ".")
    return label


def port_join_key(chassis_ip: str, port: str) -> tuple[str, str]:
    """Return (chassis_ip, port) used to match inventory ⟕ session rows."""
    return (normalize_chassis_ip(chassis_ip), normalize_port_label(port))


def inventory_join_key(record: PortRecord) -> tuple[str, str]:
    """Key from inventory row (``chassisIp`` → chassis_ip, ``card.port``)."""
    return port_join_key(record.chassis_ip, record.port)


def session_join_key(record: SessionPortRecord) -> tuple[str, str]:
    """Key from session row (chassis IP/name + port label)."""
    return port_join_key(record.chassis_ip, record.port)
