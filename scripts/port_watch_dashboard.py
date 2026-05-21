#!/usr/bin/env python3
"""
Simple HTML dashboard mirroring CLI output:

  sync_true_port_utilization.py --blocked
  sync_true_port_utilization.py --all

Serves a single page that auto-refreshes every 5 minutes (server caches
snapshots for the same interval so Explorer APIs are not hammered).

  .venv/bin/python scripts/port_watch_dashboard.py
  # open http://<this-host>:8765  (listens on 0.0.0.0 by default)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from collector.port_blocked import is_port_owned  # noqa: E402
from collector.true_port_utilization import (  # noqa: E402
    BLOCKED_OWNER_SUMMARY_COLUMNS,
    DISPLAY_COLUMNS,
    OWNER_REPORT_COLUMNS,
    TruePortUtilRecord,
    build_blocked_owner_summary,
    fetch_true_port_utilization_async,
    format_calculated_fields_legend,
)

log = logging.getLogger("port_watch_dashboard")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765
REFRESH_SECONDS = 300
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _row_dict(record: TruePortUtilRecord) -> dict[str, str]:
    return record.as_dict()


def build_snapshot(
    records: list[TruePortUtilRecord],
    *,
    inventory_count: int,
    session_count: int,
) -> dict:
    blocked = [r for r in records if r.blocked is True]
    owned = [r for r in records if is_port_owned(r.owner)]

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "inventory_count": inventory_count,
        "session_count": session_count,
        "joined_count": len(records),
        "blocked_count": len(blocked),
        "owned_count": len(owned),
        "blocked": {
            "main_table": [_row_dict(r) for r in blocked],
            "owner_report": build_blocked_owner_summary(blocked),
            "columns": list(DISPLAY_COLUMNS),
            "owner_columns": list(BLOCKED_OWNER_SUMMARY_COLUMNS),
        },
        "all_owned": {
            "owner_report": [_row_dict(r) for r in owned],
            "owner_columns": list(OWNER_REPORT_COLUMNS),
        },
        "legend": format_calculated_fields_legend().splitlines(),
    }


class SnapshotCache:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: dict | None = None
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(
        self,
        *,
        inventory_url: str | None,
        session_url: str | None,
        session_server: str | None,
        session_tag: str | None,
        refresh_inventory: bool,
        refresh_sessions: bool,
        settle_seconds: float | None,
        force: bool = False,
    ) -> dict:
        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._data is not None
                and (now - self._fetched_at) < self.ttl_seconds
            ):
                return self._data

            log.info("Fetching inventory + session ports...")
            records, inv_count, sess_count = await fetch_true_port_utilization_async(
                inventory_url=inventory_url,
                session_url=session_url,
                session_server=session_server,
                session_tag=session_tag,
                refresh_inventory=refresh_inventory,
                refresh_sessions=refresh_sessions,
                settle_seconds=settle_seconds,
            )
            snapshot = build_snapshot(
                records,
                inventory_count=inv_count,
                session_count=sess_count,
            )
            self._data = snapshot
            self._fetched_at = now
            log.info(
                "Snapshot ready: joined=%s blocked=%s owned=%s",
                snapshot["joined_count"],
                snapshot["blocked_count"],
                snapshot["owned_count"],
            )
            return snapshot


def create_app(
    *,
    cache: SnapshotCache,
    inventory_url: str | None,
    session_url: str | None,
    session_server: str | None,
    session_tag: str | None,
    refresh_inventory: bool,
    refresh_sessions: bool,
    settle_seconds: float | None,
) -> web.Application:
    async def index(_request: web.Request) -> web.Response:
        html_path = _WEB_DIR / "port_watch.html"
        return web.FileResponse(html_path)

    async def api_snapshot(request: web.Request) -> web.Response:
        force = request.query.get("force", "").lower() in ("1", "true", "yes")
        try:
            data = await cache.get(
                inventory_url=inventory_url,
                session_url=session_url,
                session_server=session_server,
                session_tag=session_tag,
                refresh_inventory=refresh_inventory,
                refresh_sessions=refresh_sessions,
                settle_seconds=settle_seconds,
                force=force,
            )
        except OSError as exc:
            log.exception("Snapshot fetch failed")
            return web.json_response(
                {"error": str(exc)},
                status=502,
            )
        return web.json_response(data)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/snapshot", api_snapshot)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HTML port watch dashboard (blocked + all owned), 5m refresh",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=REFRESH_SECONDS,
        help="Browser and server cache interval (default: 300)",
    )
    parser.add_argument("--inventory-url", default=None)
    parser.add_argument("--session-url", default=None)
    parser.add_argument("--server", default=None, help="Filter sessions by IxNetwork server")
    parser.add_argument("--tag", default=None, help="Filter sessions by tag")
    parser.add_argument(
        "--no-refresh-inventory",
        action="store_true",
        help="Skip POST /api/poll/ports on each snapshot",
    )
    parser.add_argument(
        "--no-refresh-sessions",
        action="store_true",
        help="Skip POST /poll/trigger on each snapshot",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip both poll triggers (faster snapshots, may be stale)",
    )
    parser.add_argument("--refresh-settle", type=float, default=None)
    args = parser.parse_args()

    load_dotenv(_REPO_ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    refresh_inventory = not (args.no_refresh_inventory or args.no_refresh)
    refresh_sessions = not (args.no_refresh_sessions or args.no_refresh)

    cache = SnapshotCache(ttl_seconds=args.refresh_seconds)
    app = create_app(
        cache=cache,
        inventory_url=args.inventory_url,
        session_url=args.session_url,
        session_server=args.server,
        session_tag=args.tag,
        refresh_inventory=refresh_inventory,
        refresh_sessions=refresh_sessions,
        settle_seconds=args.refresh_settle,
    )

    print(f"Port watch dashboard: http://{args.host}:{args.port}")
    print(f"Auto-refresh every {int(args.refresh_seconds)}s")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
