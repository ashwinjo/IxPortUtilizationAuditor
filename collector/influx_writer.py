"""Write joined port snapshots to InfluxDB (all inventory ports each poll)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from .port_blocked import is_port_owned
from .true_port_utilization import TruePortUtilRecord


def influx_settings_from_env() -> dict[str, str]:
    """Read Influx connection settings from environment."""
    return {
        "url": os.environ.get("INFLUXDB_URL", "http://localhost:8086"),
        "token": os.environ.get("INFLUXDB_TOKEN", ""),
        "org": os.environ.get("INFLUXDB_ORG", "ixport"),
        "bucket": os.environ.get("INFLUXDB_BUCKET", "port_metrics"),
    }


def record_to_point(record: TruePortUtilRecord, *, ts: datetime | None = None) -> Point:
    """
    One Influx point per port (all ports, not only blocked).

    Tags: chassis_id, port_id, owner (when non-empty).
    Fields: blocked, cp, dp, utilization, transmit_idle, is_owned.
    Legacy aliases (is_hogging, control_plane_active, ...) for older dashboards.
    """
    when = ts or datetime.now(timezone.utc)
    owner = (record.owner or "").strip()

    point = (
        Point("port_utilization")
        .tag("chassis_id", record.chassis)
        .tag("port_id", record.port)
        .time(when, WritePrecision.NS)
        .field("blocked", int(record.blocked))
        .field("cp", int(record.cp))
        .field("dp", int(record.dp))
        .field("utilization", int(record.utilization))
        .field("is_owned", int(is_port_owned(record.owner)))
        .field("transmit_idle", int(record.transmit_state == "0"))
        # Legacy field names used by existing Grafana JSON
        .field("is_hogging", int(record.blocked))
        .field("control_plane_active", int(record.cp))
        .field("data_plane_active", int(record.dp))
        .field("is_utilized", int(record.utilization))
    )

    if is_port_owned(record.owner):
        point = point.tag("owner", owner).field("owner_name", owner)
    else:
        point = point.field("owner_name", "")

    return point


def write_port_snapshots(
    records: list[TruePortUtilRecord],
    *,
    url: str | None = None,
    token: str | None = None,
    org: str | None = None,
    bucket: str | None = None,
    ts: datetime | None = None,
) -> int:
    """Write all port rows to InfluxDB. Returns number of points written."""
    cfg = influx_settings_from_env()
    url = url or cfg["url"]
    token = token if token is not None else cfg["token"]
    org = org or cfg["org"]
    bucket = bucket or cfg["bucket"]

    if not token:
        raise ValueError(
            "INFLUXDB_TOKEN is required (set in environment or pass token=)"
        )
    if not records:
        return 0

    when = ts or datetime.now(timezone.utc)
    points = [record_to_point(r, ts=when) for r in records]

    with InfluxDBClient(url=url, token=token, org=org) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=bucket, org=org, record=points)

    return len(points)
