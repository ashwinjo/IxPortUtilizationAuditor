"""Join inventory + session port APIs in memory (no intermediate SQLite tables)."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from .join_keys import inventory_join_key, session_join_key
from .port_blocked import (
    compute_blocked,
    compute_blocked_without_session,
    is_port_owned,
)
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
    "owner",
    "session",
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
    cp: bool | None
    dp: bool | None
    utilization: bool | None
    blocked: bool | None
    ixnet_server: str = ""
    session_id: str = ""
    session_name: str = ""

    @property
    def in_session(self) -> bool:
        """True when this port appears on an IxNetwork session (CP/DP/util known)."""
        return self.cp is not None

    @property
    def session_display(self) -> str:
        """IxNetwork server/session label, or N/A when not in any session."""
        if not self.in_session:
            return "N/A"
        if self.ixnet_server and self.session_name:
            return f"{self.ixnet_server}/{self.session_name}"
        if self.session_name:
            return self.session_name
        if self.ixnet_server:
            return self.ixnet_server
        if self.session_id:
            return self.session_id
        return "N/A"

    @property
    def traffic_running(self) -> bool:
        """Backward-compatible alias: transmitState ``1``."""
        return self.transmit_state == "1"

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "chassis": self.chassis,
            "port": self.port,
            "session": self.session_display,
            "owner": self.owner,
            "transmitState": self.transmit_state,
            "cp": _metric_label(self.cp),
            "dp": _metric_label(self.dp),
            "utilization": _metric_label(self.utilization),
            "blocked": _blocked_label(self.blocked),
        }


def join_port_utilization(
    inventory: list[PortRecord],
    sessions: list[SessionPortRecord],
) -> list[TruePortUtilRecord]:
    """
    LEFT JOIN inventory ports with session flags on (chassis_ip, port).

    Ports with no session row get cp/dp/utilization ``None`` (N/A) and session ``N/A``.
    """
    session_by_key: dict[tuple[str, str], SessionPortRecord] = {}
    for row in sessions:
        session_by_key[session_join_key(row)] = row

    merged: list[TruePortUtilRecord] = []
    for inv in inventory:
        sess = session_by_key.get(inventory_join_key(inv))
        if sess:
            cp, dp, utilization = sess.cp, sess.dp, sess.utilization
            ixnet_server = sess.ixnet_server
            session_id = sess.session_id
            session_name = sess.session_name
        else:
            cp = dp = utilization = None
            ixnet_server = session_id = session_name = ""
            blocked = compute_blocked_without_session(
                owner=inv.owner,
                transmit_state=inv.transmit_state,
            )
        if sess:
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
                ixnet_server=ixnet_server,
                session_id=session_id,
                session_name=session_name,
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


def _metric_label(value: bool | None) -> str:
    """Session metric display: True / False, or N/A when not in any session."""
    if value is None:
        return "N/A"
    return _bool_label(value)


def _blocked_label(value: bool | None) -> str:
    """Blocked display: True / False when in session, N/A when unknown."""
    return _metric_label(value)


def format_calculated_fields_legend() -> str:
    """
    End-user legend: every joined row lists transmitState with CP, DP, and utilization.

    ``blocked`` is derived from owner + transmitState + CP; DP/utilization are
    informational (always displayed, including N/A when the port is not in a session).
    """
    return "\n".join(
        [
            "--- Calculated fields (shown on every port row) ---",
            "transmitState   Inventory Explorer — 0 = idle on chassis, 1 = active transmit",
            "cp              Session Explorer control plane (N/A if not in any session)",
            "dp              Session Explorer data plane (N/A if not in any session)",
            "utilization     Session Explorer utilized flag (N/A if not in any session)",
            "blocked         Derived: owned + in session + transmitState 0 + CP False → True",
            "                Owned, no session: transmitState 1 → False; transmitState 0 → N/A",
            "DP and utilization are always listed with transmitState; they do not change blocked.",
            "Full rubric: docs/blocked_port_rubric.md",
        ]
    )


def format_true_util_table(records: list[TruePortUtilRecord]) -> str:
    if not records:
        return " | ".join(DISPLAY_COLUMNS) + "\n(no rows)"

    display = [
        {
            "chassis": r.chassis,
            "port": r.port,
            "owner": r.owner,
            "session": r.session_display,
            "transmitState": r.transmit_state,
            "cp": _metric_label(r.cp),
            "dp": _metric_label(r.dp),
            "utilization": _metric_label(r.utilization),
            "blocked": _blocked_label(r.blocked),
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


OWNER_REPORT_COLUMNS = (
    "chassis",
    "port",
    "session",
    "owner",
    "transmitState",
    "cp",
    "dp",
    "utilization",
    "blocked",
)


def format_owner_ports_report(
    records: list[TruePortUtilRecord],
    *,
    all_owned: bool = False,
) -> str:
    """
    Tabular owner report for triage.

    Default (no flags): blocked ports only.
    ``all_owned``: all owned ports (blocked, utilized, idle).
    """
    if all_owned:
        filtered = [r for r in records if is_port_owned(r.owner)]
        label = "owned"
    else:
        filtered = [r for r in records if r.blocked is True]
        label = "blocked"
    if not filtered:
        if all_owned:
            return "No owned ports."
        return "No blocked ports."

    headers = OWNER_REPORT_COLUMNS
    rows = [
        {
            "chassis": r.chassis,
            "port": r.port,
            "session": r.session_display,
            "owner": r.owner,
            "transmitState": r.transmit_state,
            "cp": _metric_label(r.cp),
            "dp": _metric_label(r.dp),
            "utilization": _metric_label(r.utilization),
            "blocked": _blocked_label(r.blocked),
        }
        for r in filtered
    ]
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row[h])))

    def fmt(cells: dict[str, str]) -> str:
        return " | ".join(str(cells[h]).ljust(widths[h]) for h in headers)

    lines = [
        f"{len(filtered)} {label} port(s):",
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


def influx_metric_value(value: bool | None) -> int:
    """Map bool metric to Influx integer: 1/0, or -1 for N/A."""
    if value is None:
        return -1
    return int(value)


def influx_blocked_value(blocked: bool | None) -> int:
    """Map blocked to Influx integer: 1=true, 0=false, -1=unknown (no session)."""
    return influx_metric_value(blocked)
