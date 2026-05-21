# Progress 3 — Ix Port Utilization Plotter

**Date:** 2026-05-20  
**Status:** Polling pipeline + **InfluxDB writes** + **Grafana blocked trend** wired; ready for scheduled snapshots.  
**Prior:** See [Progress2.md](Progress2.md) for blocked-port logic and in-memory join. See [Progress1.md](Progress1.md) for initial collector design.

---

## Goal

Poll all chassis configured in **Ixia Inventory Explorer**, join each port with **IxNetwork Session Explorer** CP/DP/utilization, compute **blocked** for owned ports, and store **every port** (not only blocked) in a time-series database so users can:

1. Pick a **chassis** and **port**
2. See **blocked** trend over time
3. See **who blocked** the port (owner) on the same view when `blocked=1`

Start with this single derived metric; add more fields later without changing the overall stack.

---

## Recommendation: InfluxDB 2 + Grafana (not a custom plotter)

Use the **existing** repo stack rather than building a custom UI for v1.

| Approach | Verdict |
|----------|---------|
| **InfluxDB 2 + Grafana** | **Yes** — already provisioned (`grafana/`, `influxdb/setup.sh`, `docker-compose.yml`) |
| **Custom plotter** | Defer — only if Grafana cannot cover workflows (approvals, ticketing, multi-tenant RBAC) |
| **SQLite for time series** | **No** — Progress 1 described SQLite modules that are not in the repo; use Influx as source of truth |

### Why InfluxDB fits

| Need | How Influx handles it |
|------|------------------------|
| Periodic poll (snapshot) | One point per port per poll |
| Store **all** ports | Tags `chassis_id`, `port_id`; numeric fields for flags |
| Blocked trend | Field `blocked` (0/1) over time |
| Who blocked | Tag `owner` on owned ports (owner changes → new series; good for history) |
| More metrics later | Add fields without schema migration |

### Why not SQLite for metrics

SQLite is useful for config or a local cache, not for time-range queries and Grafana integration. Optional SQLite later only for chassis allowlists or poller state — not for the blocked trend.

---

## Blocked-port logic (unchanged)

See [Progress2.md](Progress2.md). Summary:

- **Blocked check** applies only to **owned** ports (`owner` non-empty and not `Free`).
- **All ports** are written to Influx each poll (`blocked=0` for unowned ports).

Implementation: `collector/port_blocked.py` (`is_port_owned()`, `compute_blocked()`).

---

## Data model (InfluxDB)

```
bucket:       port_metrics
measurement:  port_utilization
```

### Tags

| Tag | Example | Notes |
|-----|---------|-------|
| `chassis_id` | `10.36.236.121` | Inventory chassis IP |
| `port_id` | `6.3` | Normalized `card.port` |
| `owner` | `IxNetwork/ixnetworkweb/admin-3-1111627` | Only when port is **owned** (not empty / not `Free`) |

### Fields (primary)

| Field | Type | Source / meaning |
|-------|------|------------------|
| `blocked` | int 0/1 | Derived — Progress 2 logic |
| `cp` | int 0/1 | Session `cp_active` |
| `dp` | int 0/1 | Session `dp_active` |
| `utilization` | int 0/1 | Session `utilized` |
| `transmit_idle` | int 0/1 | `1` when `transmitState == "0"` |
| `is_owned` | int 0/1 | `is_port_owned(owner)` |
| `owner_name` | string | Owner string (empty when unowned) |

### Legacy field aliases (existing Grafana JSON)

Written alongside primary fields so older dashboards keep working:

| Legacy field | Maps to |
|--------------|---------|
| `is_hogging` | `blocked` |
| `control_plane_active` | `cp` |
| `data_plane_active` | `dp` |
| `is_utilized` | `utilization` |

---

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────────┐
│ Ixia Inventory Explorer │     │ IxNetwork Session Explorer│
│ GET /api/ports          │     │ GET /sessions/            │
└───────────┬─────────────┘     └────────────┬─────────────┘
            │                                │
            └────────────┬───────────────────┘
                         ▼
              scripts/poll_port_metrics.py
              fetch_true_port_utilization_sync()
              join_port_utilization() + compute_blocked()
                         │
                         ▼
              collector/influx_writer.py
              write_port_snapshots()  — ALL ports
                         │
                         ▼
              InfluxDB (bucket: port_metrics)
                         │
                         ▼
              Grafana — Port History dashboard
              (chassis + port variables, blocked trend, owner table)
```

Join key and join semantics are unchanged from Progress 2: inventory-driven LEFT JOIN on `(chassis_ip, port)`.

---

## New / updated modules

### `collector/influx_writer.py` *(new)*

- `influx_settings_from_env()` — `INFLUXDB_URL`, `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`
- `record_to_point()` — maps `TruePortUtilRecord` → Influx `Point`
- `write_port_snapshots()` — synchronous write of all joined rows

### `scripts/poll_port_metrics.py` *(new)*

- Fetches both APIs, joins, writes to Influx
- `--once` — single poll and exit
- Default — `APScheduler` interval loop (default **300s**)
- `--dry-run` — fetch + log blocked summary; no Influx write
- Loads `.env` from project root via `python-dotenv`

### `docker-compose.yml` *(new)*

Local stack:

| Service | Port | Notes |
|---------|------|-------|
| InfluxDB 2.7 | 8086 | Init org `ixport`, bucket `port_metrics`, dev token in compose env |
| Grafana 11.4 | 3000 | Provisioning from `grafana/provisioning/`, dashboards from `grafana/dashboards/` |

### `.env.example` *(new)*

Template for `INVENTORY_EXPLORER_URL`, `SESSION_EXPLORER_URL`, `INFLUXDB_*`.

### `collector/__init__.py`

- Re-exports `write_port_snapshots`

### `grafana/dashboards/port_history.json` *(updated)*

Panels:

1. **Blocked trend** — `blocked` field, 0/1 bar chart
2. **Who blocked this port** — table of `owner` tag when `blocked=1`
3. **CP / DP / utilization** — supporting context on same chassis/port

### `tests/test_influx_writer.py` *(new)*

- Point mapping: tags, `blocked`, legacy `is_hogging`, no `owner` tag for `Free`

---

## Usage

### Prerequisites

```bash
cd /Users/ashwin.joshi/IxPortUtilizationPlotter
python3 -m venv .venv
.venv/bin/pip install -r collector/requirements.txt

cp .env.example .env
# Edit .env: API URLs, INFLUXDB_TOKEN
```

### Local Influx + Grafana

```bash
docker compose up -d
# Influx: http://localhost:8086
# Grafana: http://localhost:3000 (admin / password from compose)
```

Use the init token from `docker-compose.yml` (`DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`) as `INFLUXDB_TOKEN` in `.env`.

### Poll once (dry run)

```bash
export INVENTORY_EXPLORER_URL=http://ixnse.ashai.online:3001
export SESSION_EXPLORER_URL=http://ixnse.ashai.online:8080

.venv/bin/python scripts/poll_port_metrics.py --once --dry-run -v
```

### Poll once (write to Influx)

```bash
.venv/bin/python scripts/poll_port_metrics.py --once -v
```

### Scheduled poller (default 5 min)

```bash
.venv/bin/python scripts/poll_port_metrics.py
# Or: --interval 120 for 2 minutes
```

### CLI options (`poll_port_metrics.py`)

| Flag | Effect |
|------|--------|
| `--once` | Single poll, then exit |
| `--interval SECONDS` | Poll interval when scheduling (default: 300) |
| `--inventory-url`, `--session-url` | Override API base URLs |
| `--server`, `--tag` | Session Explorer filters |
| `--dry-run` | No Influx write |
| `-v` | Debug logging |

### End-user view (Grafana)

1. Open dashboard **Port History** (`uid: port-history`)
2. Select `chassis_id` and `port_id` variables
3. **Blocked trend** — when the port was hogging (owned, idle transmit, no CP)
4. **Who blocked** — owner from tag when `blocked=1`
5. **CP / DP / utilization** — whether session stats show real use

Other dashboards (unchanged naming, legacy fields still written):

- `port_heatmap.json` — chassis-wide state timeline
- `owner_leaderboard.json` — hogging count by `owner` (queries `is_hogging`)

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INVENTORY_EXPLORER_URL` | `http://ixnse.ashai.online:3001` | Inventory API |
| `SESSION_EXPLORER_URL` | `http://localhost:8080` | Session API — **set in prod** |
| `INFLUXDB_URL` | `http://localhost:8086` | Influx write target |
| `INFLUXDB_TOKEN` | *(required)* | Influx API token |
| `INFLUXDB_ORG` | `ixport` | Influx org |
| `INFLUXDB_BUCKET` | `port_metrics` | Influx bucket |

---

## Tests

```bash
.venv/bin/python3.14 -m pytest tests/ -q
```

| File | Coverage |
|------|----------|
| `tests/test_port_blocked.py` | Blocked logic (Progress 2) |
| `tests/test_influx_writer.py` | Influx point tags/fields |

---

## Dependencies

`collector/requirements.txt` (now used by poller):

- `aiohttp>=3.9` — Session Explorer
- `influxdb-client>=1.40` — Influx writes
- `APScheduler>=3.10` — Scheduled polling
- `python-dotenv>=1.0` — `.env` loading

---

## Known gaps / next steps

1. **Production deploy** — Run `poll_port_metrics.py` under systemd/cron/K8s; set `SESSION_EXPLORER_URL` (not `localhost`).
2. **Grafana datasource in compose** — Confirm `INFLUXDB_TOKEN` / org / bucket env match provisioning (`grafana/provisioning/datasources/influxdb.yml`).
3. **Alerts** — Grafana alert when `blocked=1` longer than N minutes on critical ports.
4. **Legacy field cleanup** — Drop `is_hogging` aliases once all dashboards query `blocked`.
5. **Heatmap / leaderboard** — Add “blocked now” stat panel; align Flux queries to `blocked` naming.
6. **Chassis allowlist** — Optional filter if Inventory returns more chassis than you want to bill/monitor.
7. **Retention policy** — Define Influx retention (e.g. 90d raw, downsample for yearly trends).

---

## File map (Progress 3 additions)

```
collector/
  influx_writer.py          ← Influx point mapping + write

scripts/
  poll_port_metrics.py      ← scheduled / one-shot poller

tests/
  test_influx_writer.py

grafana/dashboards/
  port_history.json         ← blocked trend + owner table (updated)

docker-compose.yml          ← local Influx + Grafana
.env.example

Progress1.md
Progress2.md
Progress3.md
```

---

## Design decisions (summary)

| Question | Decision |
|----------|----------|
| Time-series DB? | **InfluxDB 2** (`port_metrics` bucket) |
| Visualization? | **Grafana** (extend existing dashboards) |
| Custom plotter? | **No** for v1 |
| What to store each poll? | **All** inventory ports + joined session flags + `blocked` + `owner` tag when owned |
| Blocked evaluation scope? | **Owned ports only**; unowned still stored with `blocked=0` |
| Poll interval default? | **300 seconds** (configurable) |
