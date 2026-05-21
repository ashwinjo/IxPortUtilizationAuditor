"""Fetch session-assigned ports from IxNetwork Session Explorer (CP / DP / utilization)."""

from __future__ import annotations

import asyncio
import csv
import os
from dataclasses import dataclass
from pathlib import Path  # used by __main__ for db path display
from typing import Any

import aiohttp

DEFAULT_BASE_URL = "http://localhost:8080"
SESSIONS_PATH = "/sessions/"
POLL_TRIGGER_PATH = "/poll/trigger"


def session_base_url(base_url: str | None = None) -> str:
    """Resolve Session Explorer base URL from arg or ``SESSION_EXPLORER_URL``."""
    return (base_url or os.environ.get("SESSION_EXPLORER_URL", DEFAULT_BASE_URL)).rstrip("/")


@dataclass(frozen=True)
class SessionPortRecord:
    chassis_ip: str
    port: str
    cp: bool
    dp: bool
    utilization: bool

    @property
    def chassis(self) -> str:
        """Alias for ``chassis_ip`` (session API chassis identifier)."""
        return self.chassis_ip

    def as_row(self) -> dict[str, str]:
        return {
            "Chassis": self.chassis_ip,
            "Port": self.port,
            "CP": _yes_no(self.cp),
            "DP": _yes_no(self.dp),
            "Utilization": _yes_no(self.utilization),
        }


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _chassis_ip_from_port(port_obj: dict[str, Any]) -> str:
    """Resolve chassis IP for join with inventory ``chassis_ip``."""
    for key in ("chassis_ip", "chassisIp", "chassis_name", "chassis"):
        value = port_obj.get(key)
        if value:
            from .join_keys import normalize_chassis_ip

            return normalize_chassis_ip(str(value))
    return ""


def _port_label(port_obj: dict[str, Any]) -> str:
    from .join_keys import normalize_port_label
    fq = str(port_obj.get("fully_qualified_port_name") or "").strip()
    if fq and fq != "N/A":
        return normalize_port_label(fq)
    card = port_obj.get("card")
    port_num = port_obj.get("port")
    if card is not None and port_num is not None:
        return normalize_port_label(f"{card}.{port_num}")
    return ""


def normalize_session_port(port_obj: dict[str, Any]) -> SessionPortRecord | None:
    chassis_ip = _chassis_ip_from_port(port_obj)
    port = _port_label(port_obj)
    if not chassis_ip or not port:
        return None
    return SessionPortRecord(
        chassis_ip=chassis_ip,
        port=port,
        cp=bool(port_obj.get("cp_active")),
        dp=bool(port_obj.get("dp_active")),
        utilization=bool(port_obj.get("utilized")),
    )


def normalize_sessions_response(payload: dict[str, Any]) -> list[SessionPortRecord]:
    """Flatten GET /sessions/ envelope into one row per session port."""
    data = payload.get("data", payload)
    servers = data.get("servers") or []
    records: list[SessionPortRecord] = []

    for server in servers:
        for session in server.get("sessions") or []:
            for port_obj in session.get("ports") or []:
                if not isinstance(port_obj, dict):
                    continue
                record = normalize_session_port(port_obj)
                if record is not None:
                    records.append(record)

    records.sort(key=lambda r: (r.chassis_ip, r.port))
    return records


def normalize_sessions_with_metadata(
    payload: dict[str, Any],
) -> tuple[list[SessionPortRecord], list[dict[str, str]]]:
    """Flatten GET /sessions/ with ixnet_server / session_id / session_name per row."""
    data = payload.get("data", payload)
    servers = data.get("servers") or []
    records: list[SessionPortRecord] = []
    metadata: list[dict[str, str]] = []

    for server in servers:
        server_name = str(server.get("name") or "")
        for session in server.get("sessions") or []:
            session_id = str(session.get("id") or "")
            session_name = str(session.get("name") or "")
            for port_obj in session.get("ports") or []:
                if not isinstance(port_obj, dict):
                    continue
                record = normalize_session_port(port_obj)
                if record is None:
                    continue
                records.append(record)
                metadata.append(
                    {
                        "ixnet_server": server_name,
                        "session_id": session_id,
                        "session_name": session_name,
                    }
                )

    combined = sorted(
        zip(records, metadata),
        key=lambda pair: (pair[0].chassis_ip, pair[0].port),
    )
    if not combined:
        return [], []
    records, metadata = zip(*combined)
    return list(records), list(metadata)


async def trigger_session_poll(
    base_url: str | None = None,
    *,
    session: aiohttp.ClientSession | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    POST /poll/trigger — kick off an immediate Session Explorer poll cycle.

    Timeout defaults to ``SESSION_POLL_TIMEOUT`` env or 120s.
    """
    if timeout is None:
        timeout = float(os.environ.get("SESSION_POLL_TIMEOUT", "120"))
    url = f"{session_base_url(base_url)}{POLL_TRIGGER_PATH}"

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()

    try:
        async with session.post(
            url,
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    finally:
        if owns_session:
            await session.close()


def trigger_session_poll_sync(
    base_url: str | None = None,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    return asyncio.run(trigger_session_poll(base_url, timeout=timeout))


async def fetch_sessions_raw(
    base_url: str | None = None,
    *,
    server: str | None = None,
    tag: str | None = None,
    session: aiohttp.ClientSession | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    url = f"{session_base_url(base_url)}{SESSIONS_PATH}"
    params: dict[str, str] = {}
    if server:
        params["server"] = server
    if tag:
        params["tag"] = tag

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()

    try:
        async with session.get(
            url,
            params=params or None,
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    finally:
        if owns_session:
            await session.close()


async def fetch_session_port_records(
    base_url: str | None = None,
    *,
    server: str | None = None,
    tag: str | None = None,
    session: aiohttp.ClientSession | None = None,
    timeout: float = 60.0,
) -> list[SessionPortRecord]:
    """GET /sessions/ and return Chassis | Port | CP | DP | Utilization rows."""
    payload = await fetch_sessions_raw(
        base_url,
        server=server,
        tag=tag,
        session=session,
        timeout=timeout,
    )
    return normalize_sessions_response(payload)


def fetch_session_port_records_sync(
    base_url: str | None = None,
    *,
    server: str | None = None,
    tag: str | None = None,
    timeout: float = 60.0,
) -> list[SessionPortRecord]:
    return asyncio.run(
        fetch_session_port_records(
            base_url,
            server=server,
            tag=tag,
            timeout=timeout,
        )
    )


async def fetch_session_ports_with_metadata(
    base_url: str | None = None,
    *,
    server: str | None = None,
    tag: str | None = None,
    session: aiohttp.ClientSession | None = None,
    timeout: float = 60.0,
) -> tuple[list[SessionPortRecord], list[dict[str, str]]]:
    """Fetch sessions and return (records, per-row session metadata)."""
    payload = await fetch_sessions_raw(
        base_url,
        server=server,
        tag=tag,
        session=session,
        timeout=timeout,
    )
    return normalize_sessions_with_metadata(payload)


def fetch_session_ports_with_metadata_sync(
    base_url: str | None = None,
    *,
    server: str | None = None,
    tag: str | None = None,
    timeout: float = 60.0,
) -> tuple[list[SessionPortRecord], list[dict[str, str]]]:
    return asyncio.run(
        fetch_session_ports_with_metadata(
            base_url,
            server=server,
            tag=tag,
            timeout=timeout,
        )
    )


def write_session_port_records_csv(records: list[SessionPortRecord], path: str | Path) -> None:
    fieldnames = ["Chassis", "Port", "CP", "DP", "Utilization"]
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_row())


def format_session_port_table(records: list[SessionPortRecord]) -> str:
    rows = [r.as_row() for r in records]
    if not rows:
        return "Chassis | Port | CP | DP | Utilization\n(no session ports)"

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
    import argparse

    parser = argparse.ArgumentParser(
        description="List ports assigned to IxNetwork sessions (Session Explorer API)."
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Session Explorer base URL (or set SESSION_EXPLORER_URL)",
    )
    parser.add_argument("--server", default=None, help="Filter by IxNetwork server name")
    parser.add_argument("--tag", default=None, help="Filter sessions by tag")
    parser.add_argument("-o", "--output", default=None, help="Write CSV to this path")
    args = parser.parse_args()

    records = fetch_session_port_records_sync(
        args.url,
        server=args.server,
        tag=args.tag,
    )
    print(format_session_port_table(records))
    print(f"\n{len(records)} port(s)")

    if args.output:
        write_session_port_records_csv(records, args.output)
        print(f"Wrote {args.output}")
