"""IxPort MCP Server — StreamableHTTP transport on port 8887.

Exposes three read-only tools that proxy the IxPort FastAPI (port 8890):
  - ixport_get_blocked_ports  : ports that are owned + idle + in-session
  - ixport_get_owned_ports    : all owned ports with per-port blocked status
  - ixport_get_owner_summary  : ranked list of users hogging blocked ports
"""
from __future__ import annotations

import json
import os
from typing import Optional

import aiohttp
from mcp.server.fastmcp import FastMCP

IXPORT_API = os.getenv("IXPORT_API_URL", "http://localhost:8890")
CHARACTER_LIMIT = 25_000

mcp = FastMCP("ixport_mcp")


# ── Shared HTTP helper ────────────────────────────────────────────────

async def _get(path: str, params: dict) -> dict:
    """Call the IxPort FastAPI and return parsed JSON.

    Raises ValueError with an actionable message on HTTP errors.
    """
    # Drop None values and boolean False — FastAPI treats absent params as defaults
    filtered = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool) and not v:
            continue
        filtered[k] = str(v).lower() if isinstance(v, bool) else v

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{IXPORT_API}{path}", params=filtered) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise ValueError(
                    f"IxPort API returned {resp.status} for {path}. "
                    f"Details: {body[:200]}. "
                    f"Check that the IxPort service is running at {IXPORT_API}."
                )
            return await resp.json()


def _truncate(data: dict) -> str:
    """Serialize to JSON and truncate if oversized."""
    result = json.dumps(data, indent=2)
    if len(result) > CHARACTER_LIMIT:
        # Re-serialize with item count halved to fit
        ports = data.get("ports", [])
        half = max(1, len(ports) // 2)
        truncated = {**data, "ports": ports[:half], "truncated": True,
                     "truncation_note": (
                         f"Response trimmed from {len(ports)} to {half} ports. "
                         "Use chassis= filter to narrow results."
                     )}
        result = json.dumps(truncated, indent=2)
    return result


# ── Tools ─────────────────────────────────────────────────────────────

@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def ixport_get_blocked_ports(
    chassis: Optional[str] = None,
    server: Optional[str] = None,
    tag: Optional[str] = None,
    refresh: bool = False,
) -> str:
    """Get Ixia ports that are owned, reserved in an IxNetwork session, but idle (blocked).

    A port is blocked when: owner != 'free', it appears in an active IxNetwork session,
    chassis transmit_state=0 (idle), and CP (control plane) is False.

    Returns:
      - total_blocked: int — number of confirmed blocked ports
      - ports: list — each entry has chassis, port, owner, session_id, session_name, ixnet_server
      - owner_summary: list — [{owner, ports_hogged}] sorted by ports_hogged descending

    Args:
      chassis: Filter by chassis IP (e.g. "10.36.236.121"). Omit for all chassis.
      server:  Filter by IxNetwork server name.
      tag:     Filter by session tag.
      refresh: If True, force a fresh poll from Inventory Explorer and Session Explorer
               before returning. Adds ~5-10s latency but guarantees current data.

    Example: ixport_get_blocked_ports(chassis="10.36.236.121") → blocked ports on one chassis.
    Example: ixport_get_blocked_ports(refresh=True) → force fresh data then return blocked ports.
    """
    data = await _get(
        "/api/v1/ports/blocked",
        {"chassis": chassis, "server": server, "tag": tag, "refresh": refresh},
    )
    return _truncate(data)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def ixport_get_owned_ports(
    chassis: Optional[str] = None,
    server: Optional[str] = None,
    tag: Optional[str] = None,
    refresh: bool = False,
) -> str:
    """Get all Ixia ports that have a non-free owner (reserved or in active use).

    Each port entry includes:
      - chassis, port, owner
      - transmit_state: "0" (idle) or "1" (traffic active on chassis)
      - blocked: True (confirmed blocked) | False (in use) | null (owned but not in session)
      - cp, dp, utilization: control-plane / data-plane / utilization flags from IxNetwork session
      - in_session: whether the port appears in any IxNetwork session
      - session_id, session_name, ixnet_server: session context when in_session=true

    Args:
      chassis: Filter by chassis IP. Omit for fleet-wide view.
      server:  Filter by IxNetwork server name.
      tag:     Filter by session tag.
      refresh: If True, trigger fresh upstream poll before returning.

    Example: ixport_get_owned_ports() → all owned ports across all chassis.
    Example: ixport_get_owned_ports(chassis="10.36.236.121", refresh=True) → fresh data for one chassis.
    """
    data = await _get(
        "/api/v1/ports/owned",
        {"chassis": chassis, "server": server, "tag": tag, "refresh": refresh},
    )
    return _truncate(data)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def ixport_get_owner_summary(
    chassis: Optional[str] = None,
    server: Optional[str] = None,
    tag: Optional[str] = None,
    refresh: bool = False,
) -> str:
    """Get a ranked summary of which users are hogging the most blocked Ixia ports.

    Returns owner_summary sorted by ports_hogged descending — useful for triage:
    who to contact first to release unused port reservations.

    Returns:
      - total_blocked: int — fleet-wide blocked port count
      - owner_summary: list of {owner: str, ports_hogged: int}

    Args:
      chassis: Scope to a single chassis IP. Omit for fleet-wide summary.
      server:  Filter by IxNetwork server.
      tag:     Filter by session tag.
      refresh: If True, force fresh upstream data before summarizing.

    Example: ixport_get_owner_summary() → "User X owns 12 blocked ports, User Y owns 5..."
    """
    data = await _get(
        "/api/v1/ports/blocked",
        {"chassis": chassis, "server": server, "tag": tag, "refresh": refresh},
    )
    summary = {
        "total_blocked": data.get("total_blocked", 0),
        "owner_summary": data.get("owner_summary", []),
    }
    return json.dumps(summary, indent=2)


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8887)
