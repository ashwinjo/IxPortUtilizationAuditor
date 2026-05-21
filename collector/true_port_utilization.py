"""Join inventory + session port APIs in memory (no intermediate SQLite tables)."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from .join_keys import inventory_join_key, session_join_key
from .port_blocked import compute_blocked
from .ports_client import PortRecord, fetch_port_records, trigger_ports_poll
from .session_ports_client import (
    SessionPortRecord,
    fetch_session_port_records,
    trigger_session_poll,
)

log = logging.getLogger(__name__)


TRUE_UTIL_COLUMNS = (
    "chassis",
    "port",
    "transmitState",
    "cp",
    "dp",
    "utilization",
    "blocked",
)

DISPLAY_COLUMNS = TRUE_UTIL_COLUMNS


@dataclass(frozen=True)
class TruePortUtilRecord:
    chassis: str
    port: str
    owner: str
    transmit_state: str
    cp: bool
    dp: bool
    utilization: bool
    blocked: bool

    @property
    def traffic_running(self) -> bool:
        """Backward-compatible alias: transmitState ``1``."""
        return self.transmit_state == "1"

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "chassis": self.chassis,
            "port": self.port,
            "owner": self.owner,
            "transmitState": self.transmit_state,
            "cp": self.cp,
            "dp": self.dp,
            "utilization": self.utilization,
            "blocked": self.blocked,
        }


def join_port_utilization(
    inventory: list[PortRecord],
    sessions: list[SessionPortRecord],
) -> list[TruePortUtilRecord]:
    """
    LEFT JOIN inventory ports with session flags on (chassis_ip, port).

    Ports with no session row get cp=False, dp=False, utilization=False.
    """
    session_by_key: dict[tuple[str, str], SessionPortRecord] = {}
    for row in sessions:
        session_by_key[session_join_key(row)] = row

    merged: list[TruePortUtilRecord] = []
    for inv in inventory:
        sess = session_by_key.get(inventory_join_key(inv))
        cp = sess.cp if sess else False
        dp = sess.dp if sess else False
        utilization = sess.utilization if sess else False
        blocked = compute_blocked(
            owner=inv.owner,
            transmit_state=inv.transmit_state,
            cp=cp,
        )
        merged.append(
            TruePortUtilRecord(
                chassis=inv.chassis_ip,
                port=inv.port,
                owner=inv.owner,
                transmit_state=inv.transmit_state,
                cp=cp,
                dp=dp,
                utilization=utilization,
                blocked=blocked,
            )
        )

    merged.sort(key=lambda r: (r.chassis, r.port))
    return merged


def refresh_settle_seconds(value: float | None = None) -> float:
    """Seconds to wait after on-demand poll triggers before GET (env ``REFRESH_SETTLE_SECONDS``)."""
    if value is not None:
        return max(0.0, value)
    return max(0.0, float(os.environ.get("REFRESH_SETTLE_SECONDS", "3")))


async def refresh_explorers_async(
    *,
    inventory_url: str | None = None,
    session_url: str | None = None,
    refresh_inventory: bool = False,
    refresh_sessions: bool = False,
    inventory_poll_timeout: float | None = None,
    session_poll_timeout: float | None = None,
    settle_seconds: float | None = None,
) -> None:
    """
    Trigger on-demand polls on Inventory (ports) and/or Session Explorer.

    Runs triggers in parallel, then sleeps ``settle_seconds`` so GET sees fresh data.
    """
    if not refresh_inventory and not refresh_sessions:
        return

    loop = asyncio.get_running_loop()
    tasks = []

    if refresh_inventory:
        log.info("Triggering Inventory Explorer POST /api/poll/ports")
        tasks.append(
            loop.run_in_executor(
                None,
                lambda: trigger_ports_poll(
                    inventory_url,
                    timeout=inventory_poll_timeout,
                ),
            )
        )
    if refresh_sessions:
        log.info("Triggering Session Explorer POST /poll/trigger")
        tasks.append(
            trigger_session_poll(session_url, timeout=session_poll_timeout)
        )

    await asyncio.gather(*tasks)

    wait = refresh_settle_seconds(settle_seconds)
    if wait > 0:
        log.debug("Waiting %.1fs after refresh triggers", wait)
        await asyncio.sleep(wait)


async def fetch_true_port_utilization_async(
    *,
    inventory_url: str | None = None,
    session_url: str | None = None,
    session_server: str | None = None,
    session_tag: str | None = None,
    refresh_inventory: bool = False,
    refresh_sessions: bool = False,
    settle_seconds: float | None = None,
    inventory_poll_timeout: float | None = None,
    session_poll_timeout: float | None = None,
    inventory_timeout: float = 30.0,
    session_timeout: float = 60.0,
) -> tuple[list[TruePortUtilRecord], int, int]:
    """
    Fetch both APIs concurrently, join in memory.

    When ``refresh_inventory`` / ``refresh_sessions`` are True, on-demand poll
    triggers run first (parallel), then GET after a short settle delay.

    Returns (merged_records, inventory_count, session_count).
    """
    await refresh_explorers_async(
        inventory_url=inventory_url,
        session_url=session_url,
        refresh_inventory=refresh_inventory,
        refresh_sessions=refresh_sessions,
        inventory_poll_timeout=inventory_poll_timeout,
        session_poll_timeout=session_poll_timeout,
        settle_seconds=settle_seconds,
    )

    loop = asyncio.get_running_loop()

    inventory_task = loop.run_in_executor(
        None,
        lambda: fetch_port_records(inventory_url, timeout=inventory_timeout),
    )
    session_task = fetch_session_port_records(
        session_url,
        server=session_server,
        tag=session_tag,
        timeout=session_timeout,
    )

    inventory, sessions = await asyncio.gather(inventory_task, session_task)
    merged = join_port_utilization(inventory, sessions)
    return merged, len(inventory), len(sessions)


def fetch_true_port_utilization_sync(
    *,
    inventory_url: str | None = None,
    session_url: str | None = None,
    session_server: str | None = None,
    session_tag: str | None = None,
    refresh_inventory: bool = False,
    refresh_sessions: bool = False,
    settle_seconds: float | None = None,
    inventory_poll_timeout: float | None = None,
    session_poll_timeout: float | None = None,
    inventory_timeout: float = 30.0,
    session_timeout: float = 60.0,
) -> tuple[list[TruePortUtilRecord], int, int]:
    return asyncio.run(
        fetch_true_port_utilization_async(
            inventory_url=inventory_url,
            session_url=session_url,
            session_server=session_server,
            session_tag=session_tag,
            refresh_inventory=refresh_inventory,
            refresh_sessions=refresh_sessions,
            settle_seconds=settle_seconds,
            inventory_poll_timeout=inventory_poll_timeout,
            session_poll_timeout=session_poll_timeout,
            inventory_timeout=inventory_timeout,
            session_timeout=session_timeout,
        )
    )


def _bool_label(value: bool) -> str:
    return "True" if value else "False"


def format_true_util_table(records: list[TruePortUtilRecord]) -> str:
    if not records:
        return " | ".join(DISPLAY_COLUMNS) + "\n(no rows)"

    display = [
        {
            "chassis": r.chassis,
            "port": r.port,
            "transmitState": r.transmit_state,
            "cp": _bool_label(r.cp),
            "dp": _bool_label(r.dp),
            "utilization": _bool_label(r.utilization),
            "blocked": _bool_label(r.blocked),
        }
        for r in records
    ]
    headers = list(DISPLAY_COLUMNS)
    widths = {h: len(h) for h in headers}
    for row in display:
        for h in headers:
            widths[h] = max(widths[h], len(row[h]))

    def fmt(cells: dict[str, str]) -> str:
        return " | ".join(cells[h].ljust(widths[h]) for h in headers)

    lines = [
        fmt({h: h for h in headers}),
        fmt({h: "-" * widths[h] for h in headers}),
    ]
    lines.extend(fmt(r) for r in display)
    return "\n".join(lines)


def format_blocked_ports_report(records: list[TruePortUtilRecord]) -> str:
    """Summary of blocked ports with owner (primary metric)."""
    blocked = [r for r in records if r.blocked]
    if not blocked:
        return "No blocked ports."

    headers = ("chassis", "port", "owner", "transmitState", "cp", "dp", "utilization")
    rows = [
        {
            "chassis": r.chassis,
            "port": r.port,
            "owner": r.owner,
            "transmitState": r.transmit_state,
            "cp": _bool_label(r.cp),
            "dp": _bool_label(r.dp),
            "utilization": _bool_label(r.utilization),
        }
        for r in blocked
    ]
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row[h])))

    def fmt(cells: dict[str, str]) -> str:
        return " | ".join(str(cells[h]).ljust(widths[h]) for h in headers)

    lines = [
        f"{len(blocked)} blocked port(s):",
        fmt({h: h for h in headers}),
        fmt({h: "-" * widths[h] for h in headers}),
    ]
    lines.extend(fmt(r) for r in rows)
    return "\n".join(lines)


def format_true_util_record(record: TruePortUtilRecord) -> str:
    """Single joined row as readable key=value lines."""
    d = record.as_dict()
    return "\n".join(
        f"  {key}: {_bool_label(value) if isinstance(value, bool) else value}"
        for key, value in d.items()
    )
