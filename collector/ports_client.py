"""Fetch port inventory from Ixia Inventory Explorer and normalize to a simple schema."""

from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://ixnse.ashai.online:3001"
PORTS_PATH = "/api/ports"
POLL_PORTS_PATH = "/api/poll/ports"


def inventory_base_url(base_url: str | None = None) -> str:
    """Resolve Inventory Explorer base URL from arg or ``INVENTORY_EXPLORER_URL``."""
    return (base_url or os.environ.get("INVENTORY_EXPLORER_URL", DEFAULT_BASE_URL)).rstrip("/")


@dataclass(frozen=True)
class PortRecord:
    chassis_ip: str
    port: str
    owner: str
    transmit_state: str
    traffic_running: bool

    @property
    def chassis(self) -> str:
        """Alias for ``chassis_ip`` (inventory API field ``chassisIp``)."""
        return self.chassis_ip

    def as_row(self) -> dict[str, str]:
        return {
            "Chassis": self.chassis_ip,
            "Port": self.port,
            "Owner": self.owner,
            "transmitState": self.transmit_state,
            "Traffic Running": "Yes" if self.traffic_running else "No",
        }


def _port_label(card_number: int | None, port_number: int | str | None) -> str:
    from .join_keys import normalize_port_label

    if card_number is not None and port_number is not None:
        return normalize_port_label(f"{card_number}.{port_number}")
    if port_number is not None:
        return normalize_port_label(str(port_number))
    return ""


_TRANSMIT_ACTIVE = {"1", "true", "True", "YES", "Yes", "Active", "Transmitting"}
_TRANSMIT_IDLE = {"0", "false", "False", "NO", "No", "Idle", "idle"}


def normalize_transmit_state(transmit_state: str | int | None) -> str:
    """Normalize API transmitState to ``\"0\"`` (idle) or ``\"1\"`` (active)."""
    if transmit_state is None:
        return "0"
    raw = str(transmit_state).strip()
    if raw in _TRANSMIT_ACTIVE:
        return "1"
    if raw in _TRANSMIT_IDLE:
        return "0"
    return raw


def _traffic_running(transmit_state: str | int | None) -> bool:
    """True when transmitState is 1 (active transmit on the port)."""
    return normalize_transmit_state(transmit_state) == "1"


def normalize_port_entry(raw: dict[str, Any]) -> PortRecord:
    transmit = normalize_transmit_state(raw.get("transmitState"))
    return PortRecord(
        chassis_ip=str(raw.get("chassisIp", "")).strip(),
        port=_port_label(raw.get("cardNumber"), raw.get("portNumber")),
        owner=str(raw.get("owner", "")),
        transmit_state=transmit,
        traffic_running=transmit == "1",
    )


def normalize_ports_response(payload: dict[str, Any]) -> list[PortRecord]:
    ports = payload.get("ports") or []
    return [normalize_port_entry(p) for p in ports]


def trigger_ports_poll(
    base_url: str | None = None,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    POST /api/poll/ports — on-demand refresh of port data from all chassis.

    Call before GET /api/ports when background inventory intervals are long.
    Timeout defaults to ``INVENTORY_POLL_TIMEOUT`` env or 120s.
    """
    if timeout is None:
        timeout = float(os.environ.get("INVENTORY_POLL_TIMEOUT", "120"))
    url = f"{inventory_base_url(base_url)}{POLL_PORTS_PATH}"
    req = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={"accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def fetch_ports_raw(
    base_url: str | None = None,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    url = f"{inventory_base_url(base_url)}{PORTS_PATH}"
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_port_records(
    base_url: str | None = None,
    *,
    timeout: float = 30.0,
) -> list[PortRecord]:
    """
    Call GET /api/ports and return rows: Chassis | Port | Owner | Traffic Running.

    Port is formatted as ``{cardNumber}.{portNumber}`` (e.g. ``3.1``).
    Traffic Running is derived from ``transmitState`` (1 = Yes, 0 = No).
    """
    payload = fetch_ports_raw(base_url, timeout=timeout)
    return normalize_ports_response(payload)


def write_port_records_csv(records: list[PortRecord], path: str | Path) -> None:
    fieldnames = ["Chassis", "Port", "Owner", "Traffic Running"]
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_row())


def format_port_table(records: list[PortRecord]) -> str:
    rows = [r.as_row() for r in records]
    if not rows:
        return "Chassis | Port | Owner | Traffic Running\n(no ports)"

    headers = list(rows[0].keys())
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row[h])))

    def fmt_row(cells: dict[str, str]) -> str:
        return " | ".join(str(cells[h]).ljust(widths[h]) for h in headers)

    lines = [fmt_row({h: h for h in headers}), fmt_row({h: "-" * widths[h] for h in headers})]
    lines.extend(fmt_row(r) for r in rows)
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        records = fetch_port_records()
        print(format_port_table(records))
        print(f"\n{len(records)} port(s)")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to fetch ports: {exc}") from exc
