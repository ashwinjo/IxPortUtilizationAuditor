#!/usr/bin/env python3
"""
Poll Inventory + Session Explorer, join ports, write all rows to InfluxDB.

Each cycle triggers on-demand refreshes (Inventory POST /api/poll/ports and
Session POST /poll/trigger) before reading APIs, so background Explorer
intervals can stay long while collector data stays fresh.

Run once:
  .venv/bin/python scripts/poll_port_metrics.py --once

Run on an interval (default 5 minutes):
  .venv/bin/python scripts/poll_port_metrics.py

Environment:
  INVENTORY_EXPLORER_URL, SESSION_EXPLORER_URL
  REFRESH_SETTLE_SECONDS, INVENTORY_POLL_TIMEOUT, SESSION_POLL_TIMEOUT
  INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.influx_writer import write_port_snapshots  # noqa: E402
from collector.true_port_utilization import (  # noqa: E402
    fetch_true_port_utilization_sync,
    format_owner_ports_report,
)

log = logging.getLogger("poll_port_metrics")


def poll_once(
    *,
    inventory_url: str | None,
    session_url: str | None,
    session_server: str | None,
    session_tag: str | None,
    refresh_inventory: bool,
    refresh_sessions: bool,
    settle_seconds: float | None,
    dry_run: bool,
) -> int:
    records, inv_count, sess_count = fetch_true_port_utilization_sync(
        inventory_url=inventory_url,
        session_url=session_url,
        session_server=session_server,
        session_tag=session_tag,
        refresh_inventory=refresh_inventory,
        refresh_sessions=refresh_sessions,
        settle_seconds=settle_seconds,
    )
    blocked = sum(1 for r in records if r.blocked is True)
    log.info(
        "Fetched inventory=%s session=%s joined=%s blocked=%s",
        inv_count,
        sess_count,
        len(records),
        blocked,
    )

    if dry_run:
        log.info("Dry run — skipping Influx write")
        if blocked:
            print(format_owner_ports_report(records))
        return len(records)

    written = write_port_snapshots(records)
    log.info("Wrote %s points to InfluxDB", written)
    if blocked:
        print(format_owner_ports_report(records))
    return written


def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Poll port metrics into InfluxDB")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll and exit (default: schedule every --interval)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Poll interval when not using --once (default: 300)",
    )
    parser.add_argument("--inventory-url", default=None)
    parser.add_argument("--session-url", default=None)
    parser.add_argument("--server", default=None, help="Session Explorer server filter")
    parser.add_argument("--tag", default=None, help="Session Explorer tag filter")
    parser.add_argument(
        "--no-refresh-inventory",
        action="store_true",
        help="Skip POST /api/poll/ports before fetch (use cached inventory only)",
    )
    parser.add_argument(
        "--no-refresh-sessions",
        action="store_true",
        help="Skip POST /poll/trigger before fetch (use cached sessions only)",
    )
    parser.add_argument(
        "--refresh-settle",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Wait after refresh triggers before GET (default: REFRESH_SETTLE_SECONDS or 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and log only; do not write to InfluxDB",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    kwargs = {
        "inventory_url": args.inventory_url,
        "session_url": args.session_url,
        "session_server": args.server,
        "session_tag": args.tag,
        "refresh_inventory": not args.no_refresh_inventory,
        "refresh_sessions": not args.no_refresh_sessions,
        "settle_seconds": args.refresh_settle,
        "dry_run": args.dry_run,
    }

    if args.once:
        poll_once(**kwargs)
        return

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(
        poll_once,
        "interval",
        seconds=args.interval,
        kwargs=kwargs,
        id="port_metrics_poll",
        max_instances=1,
        coalesce=True,
    )
    refresh_note = []
    if kwargs["refresh_inventory"]:
        refresh_note.append("inventory")
    if kwargs["refresh_sessions"]:
        refresh_note.append("sessions")
    log.info(
        "Starting poller (interval=%ss, on-demand refresh: %s); Ctrl+C to stop",
        args.interval,
        ", ".join(refresh_note) or "none",
    )
    poll_once(**kwargs)
    scheduler.start()


if __name__ == "__main__":
    main()
