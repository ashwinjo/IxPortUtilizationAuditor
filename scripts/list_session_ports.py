#!/usr/bin/env python3
"""CLI: ports from all IxNetwork sessions (Chassis | Port | CP | DP | Utilization)."""

from collector.session_ports_client import (
    fetch_session_port_records_sync,
    format_session_port_table,
    write_session_port_records_csv,
)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="List session-assigned ports from IxNetwork Session Explorer."
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Session Explorer base URL (default: SESSION_EXPLORER_URL or http://localhost:8080)",
    )
    parser.add_argument("--server", default=None, help="Filter by IxNetwork server name")
    parser.add_argument("--tag", default=None, help="Filter sessions by tag")
    parser.add_argument("-o", "--output", default=None, help="Also write CSV to this path")
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
