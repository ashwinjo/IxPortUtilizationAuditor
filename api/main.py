from __future__ import annotations

from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from collector.port_blocked import is_port_owned
from collector.true_port_utilization import (
    TruePortUtilRecord,
    build_blocked_owner_summary,
    fetch_true_port_utilization_sync,
)

from .models import (
    BlockedPortEntry,
    BlockedPortsResponse,
    OwnerSummaryEntry,
    OwnedPortEntry,
    OwnedPortsResponse,
)

_DASHBOARD = Path(__file__).parent.parent / "web" / "ixport_dashboard.html"

app = FastAPI(
    title="IxPort Utilization API",
    version="1.0.0",
    description="JSON API for Ixia port ownership and blocked-port analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(_DASHBOARD, media_type="text/html")


def _fetch(
    *,
    chassis: str | None,
    server: str | None,
    tag: str | None,
    refresh: bool,
) -> list[TruePortUtilRecord]:
    try:
        records, _, _ = fetch_true_port_utilization_sync(
            refresh_inventory=refresh,
            refresh_sessions=refresh,
            session_server=server,
            session_tag=tag,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc

    if chassis:
        records = [r for r in records if r.chassis == chassis]
    return records


def _to_owned_entry(r: TruePortUtilRecord) -> OwnedPortEntry:
    return OwnedPortEntry(
        chassis=r.chassis,
        port=r.port,
        owner=r.owner,
        transmit_state=r.transmit_state,
        blocked=r.blocked,
        cp=r.cp,
        dp=r.dp,
        utilization=r.utilization,
        in_session=r.in_session,
        session_id=r.session_id,
        session_name=r.session_name,
        ixnet_server=r.ixnet_server,
    )


def _to_blocked_entry(r: TruePortUtilRecord) -> BlockedPortEntry:
    return BlockedPortEntry(
        chassis=r.chassis,
        port=r.port,
        owner=r.owner,
        transmit_state=r.transmit_state,
        cp=r.cp,
        in_session=r.in_session,
        session_id=r.session_id,
        session_name=r.session_name,
        ixnet_server=r.ixnet_server,
    )


@app.get("/api/v1/ports/owned", response_model=OwnedPortsResponse)
def owned_ports(
    chassis: Annotated[str | None, Query(description="Filter by chassis IP")] = None,
    server: Annotated[str | None, Query(description="Session Explorer server filter")] = None,
    tag: Annotated[str | None, Query(description="Session Explorer tag filter")] = None,
    refresh: Annotated[bool, Query(description="Trigger fresh poll before fetch")] = False,
) -> OwnedPortsResponse:
    """All ports with a non-free owner, including per-port blocked flag."""
    records = [r for r in _fetch(chassis=chassis, server=server, tag=tag, refresh=refresh) if is_port_owned(r.owner)]
    return OwnedPortsResponse(
        total=len(records),
        ports=[_to_owned_entry(r) for r in records],
    )


@app.get("/api/v1/ports/blocked", response_model=BlockedPortsResponse)
def blocked_ports(
    chassis: Annotated[str | None, Query(description="Filter by chassis IP")] = None,
    server: Annotated[str | None, Query(description="Session Explorer server filter")] = None,
    tag: Annotated[str | None, Query(description="Session Explorer tag filter")] = None,
    refresh: Annotated[bool, Query(description="Trigger fresh poll before fetch")] = False,
) -> BlockedPortsResponse:
    """Blocked ports (owned, in session, transmitState=0, CP=False) with owner hog summary."""
    all_records = _fetch(chassis=chassis, server=server, tag=tag, refresh=refresh)
    blocked = [r for r in all_records if r.blocked is True]
    raw_summary = build_blocked_owner_summary(all_records)
    owner_summary = [
        OwnerSummaryEntry(owner=row["owner"], ports_hogged=int(row["ports_hogged"]))
        for row in raw_summary
    ]
    return BlockedPortsResponse(
        total_blocked=len(blocked),
        ports=[_to_blocked_entry(r) for r in blocked],
        owner_summary=owner_summary,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8890)
