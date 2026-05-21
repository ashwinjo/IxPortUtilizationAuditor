#!/usr/bin/env python3
"""
Fetch inventory + session ports, join in memory, print utilization view.

By default triggers a fresh poll on both Explorer services before each read:
  Inventory: POST /api/poll/ports  (chassis port inventory)
  Session:   POST /poll/trigger    (IxNetwork session ports)

Use --no-refresh* to read Explorer cache only (faster, may be stale).

Output columns: chassis, port, owner, session, transmitState, cp, dp, utilization, blocked.
Blocked summary section lists ports where blocked=True.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from collector.true_port_utilization import (
    TruePortUtilRecord,
    fetch_true_port_utilization_sync,
    format_calculated_fields_legend,
    format_owner_ports_report,
    format_true_util_record,
    format_true_util_table,
)


def run_end_to_end(
    *,
    inventory_url: str | None = None,
    session_url: str | None = None,
    session_server: str | None = None,
    session_tag: str | None = None,
    refresh_inventory: bool = False,
    refresh_sessions: bool = False,
    settle_seconds: float | None = None,
) -> tuple[list[TruePortUtilRecord], int, int]:
    if refresh_inventory or refresh_sessions:
        parts = []
        if refresh_inventory:
            parts.append("inventory POST /api/poll/ports")
        if refresh_sessions:
            parts.append("session POST /poll/trigger")
        print(f"On-demand refresh: {', '.join(parts)}")
    print("Fetching inventory + session ports in parallel, joining in memory...")
    try:
        records, ports_count, session_count = fetch_true_port_utilization_sync(
            inventory_url=inventory_url,
            session_url=session_url,
            session_server=session_server,
            session_tag=session_tag,
            refresh_inventory=refresh_inventory,
            refresh_sessions=refresh_sessions,
            settle_seconds=settle_seconds,
        )
    except urllib.error.URLError as exc:
        raise SystemExit(f"Inventory API failed: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"Session API failed: {exc}") from exc

    print(f"    inventory: {ports_count} port(s), session: {session_count} port(s)")
    print(f"    -> {len(records)} joined row(s)")
    return records, ports_count, session_count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Fetch both APIs, join on chassis_ip + port, print "
            "chassis | port | owner | session | transmitState | cp | dp | utilization | blocked"
        )
    )
    parser.add_argument(
        "--inventory-url",
        default=None,
        help="Inventory Explorer base URL (or INVENTORY_EXPLORER_URL)",
    )
    parser.add_argument(
        "--session-url",
        default=None,
        help="Session Explorer base URL (or SESSION_EXPLORER_URL)",
    )
    parser.add_argument("--server", default=None, help="Filter sessions by IxNetwork server")
    parser.add_argument("--tag", default=None, help="Filter sessions by tag")
    parser.add_argument("--chassis", default=None, help="Filter output by chassis IP")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Print at most N rows (default: all)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Print one joined record as JSON plus key=value detail",
    )
    view = parser.add_mutually_exclusive_group()
    view.add_argument(
        "--all",
        action="store_true",
        help="Owner report: all owned ports (blocked, utilized, idle)",
    )
    view.add_argument(
        "--blocked-only",
        "--blocked",
        action="store_true",
        dest="blocked_only",
        help="Main table and owner report: only blocked=True rows",
    )
    parser.add_argument(
        "--no-refresh-inventory",
        action="store_true",
        help="Skip POST /api/poll/ports (read cached inventory only)",
    )
    parser.add_argument(
        "--no-refresh-sessions",
        action="store_true",
        help="Skip POST /poll/trigger (read cached sessions only)",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip both poll triggers (fastest, may be stale)",
    )
    parser.add_argument(
        "--refresh-settle",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Wait after refresh triggers before GET (default: REFRESH_SETTLE_SECONDS or 3)",
    )
    parser.add_argument(
        "--no-legend",
        action="store_true",
        help="Skip calculated-fields legend after tables",
    )
    args = parser.parse_args()

    refresh_inventory = not (args.no_refresh_inventory or args.no_refresh)
    refresh_sessions = not (args.no_refresh_sessions or args.no_refresh)

    records, _, _ = run_end_to_end(
        inventory_url=args.inventory_url,
        session_url=args.session_url,
        session_server=args.server,
        session_tag=args.tag,
        refresh_inventory=refresh_inventory,
        refresh_sessions=refresh_sessions,
        settle_seconds=args.refresh_settle,
    )

    if args.chassis:
        records = [r for r in records if r.chassis == args.chassis]

    report_records = records

    if args.blocked_only:
        records = [r for r in records if r.blocked is True]

    if args.sample and records:
        sample = records[0]
        print("\n--- Sample joined record (JSON) ---")
        print(json.dumps(sample.as_dict(), indent=2))
        print("\n--- Sample joined record (detail) ---")
        print(format_true_util_record(sample))

    if args.limit is not None:
        records = records[: args.limit]

    print()
    print(format_true_util_table(records))
    print(f"\n{len(records)} row(s) shown")

    owner_title = (
        "All owned ports (owner)"
        if args.all
        else "Blocked ports (owner)"
    )
    print()
    print(f"--- {owner_title} ---")
    print(
        format_owner_ports_report(
            report_records,
            all_owned=args.all,
        )
    )
    if not args.no_legend:
        print()
        print(format_calculated_fields_legend())
