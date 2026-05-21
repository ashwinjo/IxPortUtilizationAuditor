# Progress 2 — Ix Port Utilization Plotter

**Date:** 2026-05-20  
**Status:** In-memory join + **blocked-port detection** working; CLI prints full port table and blocked-owner summary.  
**Prior:** See [Progress1.md](Progress1.md) for initial collector design and first live API verification.

---

## Goal

Build a unified port utilization view by combining:

1. **Ixia Inventory Explorer** — physical port inventory (owner, `transmitState`)
2. **IxNetwork Session Explorer** — session-assigned ports (CP, DP, utilization)

**Primary metric (Progress 2):** Identify **blocked** ports — owned but not carrying traffic — and report **who owns** them.

---

## Blocked-port logic

Ports are evaluated in order. If the port has **no owner** (empty owner or `owner == "Free"`, case-insensitive), evaluation stops and `blocked = False`.

| Case | Owner | transmitState | CP | Conclusion | blocked |
|------|-------|---------------|-----|------------|---------|
| — | empty / `Free` | (any) | (any) | Unowned — skip further checks | `False` |
| 1 | ≠ Free | `0` | `False` | Reserved, no traffic (blocked) | `True` |
| 2 | ≠ Free | `0` | `True` | In use — control plane (CP) traffic | `False` |
| 3 | ≠ Free | `1` | (any) | In use — data plane (DP) traffic | `False` |

Implementation: `collector/port_blocked.py` (`is_port_owned()`, `compute_blocked()`).

**transmitState normalization** (`collector/ports_client.py` → `normalize_transmit_state()`):

- Active → `"1"`: `1`, `true`, `True`, `YES`, `Yes`, `Active`, `Transmitting`
- Idle → `"0"`: `0`, `false`, `False`, `NO`, `No`, `Idle`, `idle`
- Other raw API values are passed through unchanged; unknown values do not match case 1–3 and yield `blocked = False`

---

## Output schema

### Main table (all ports)

| Column | Type | Source |
|--------|------|--------|
| `chassis` | string | Inventory `chassisIp` |
| `port` | string | Inventory `cardNumber.portNumber` (e.g. `6.3`) |
| `transmitState` | string | Inventory `transmitState` (normalized to `"0"` / `"1"` where possible) |
| `cp` | bool | Session `cp_active` |
| `dp` | bool | Session `dp_active` |
| `utilization` | bool | Session `utilized` |
| `blocked` | bool | Derived — see blocked-port logic above |

`owner` is kept on each `TruePortUtilRecord` but not shown in the main table; it appears in the **blocked ports summary**.

### Blocked ports summary

| Column | Purpose |
|--------|---------|
| `chassis`, `port` | Location |
| `owner` | **Who holds the blocked port** |
| `transmitState`, `cp`, `dp`, `utilization` | Context for triage |

Ports with no matching session row default to `cp=False`, `dp=False`, `utilization=False` (LEFT JOIN semantics).

---

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────────┐
│ Ixia Inventory Explorer │     │ IxNetwork Session Explorer│
│ GET /api/ports          │     │ GET /sessions/            │
│ :3001 (default)         │     │ :8080 (default)           │
└───────────┬─────────────┘     └────────────┬─────────────┘
            │                                │
            ▼                                ▼
     collector/ports_client.py    collector/session_ports_client.py
            │                                │
            └────────────┬───────────────────┘
                         ▼
              collector/true_port_utilization.py
              join_port_utilization()  — in-memory LEFT JOIN
                         │
                         ▼
              collector/port_blocked.py
              compute_blocked() per row
                         │
                         ▼
              scripts/sync_true_port_utilization.py
              (CLI table + blocked-owner report)
```

Join key: `(chassis_ip, port)` via `collector/join_keys.py` — port labels normalized (`6/3` → `6.3`).

**Note:** Progress 1 described SQLite persistence (`ports_db.py`, `session_ports_db.py`, `true_port_utilization_db.py`). Those modules are **not** in the repo at Progress 2; the active path is **fetch both APIs → join in memory → print**.

---

## Collector modules

### `collector/ports_client.py`

- Fetches `GET /api/ports` from Inventory Explorer.
- `PortRecord`: `chassis_ip`, `port`, `owner`, `transmit_state`, `traffic_running`.
- `normalize_transmit_state()` maps API values to `"0"` / `"1"` for blocked logic and display.
- `traffic_running` property: `transmit_state == "1"` (backward compatible).
- Default base URL: `http://ixnse.ashai.online:3001` (env: `INVENTORY_EXPLORER_URL`).

### `collector/session_ports_client.py`

- Fetches `GET /sessions/` from Session Explorer (async via `aiohttp`).
- `SessionPortRecord`: `chassis_ip`, `port`, `cp`, `dp`, `utilization`.
- Default base URL: `http://localhost:8080` (env: `SESSION_EXPLORER_URL`).
- Port label: `fully_qualified_port_name` `6/3` → `6.3` via `join_keys.normalize_port_label()`.

### `collector/join_keys.py`

- `normalize_chassis_ip()`, `normalize_port_label()`, `inventory_join_key()`, `session_join_key()`.

### `collector/port_blocked.py` *(new in Progress 2)*

- `is_port_owned(owner)` — false for empty or `Free`.
- `compute_blocked(owner, transmit_state, cp)` — implements cases 1–3.

### `collector/true_port_utilization.py`

- `TruePortUtilRecord`: full joined row including `owner`, `transmit_state`, `blocked`.
- `join_port_utilization()` — LEFT JOIN inventory + session, then `compute_blocked()` per row.
- `fetch_true_port_utilization_sync()` / `_async()` — concurrent API fetch + join.
- `format_true_util_table()` — main display columns.
- `format_blocked_ports_report()` — blocked rows with owner.
- `traffic_running` property on record: alias for `transmit_state == "1"`.

### `collector/__init__.py`

- Re-exports clients, join helpers, `compute_blocked`, `is_port_owned`, formatters.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/list_session_ports.py` | Session ports only (fetch, CSV) |
| `scripts/sync_true_port_utilization.py` | **End-to-end:** fetch both APIs, join, print table + blocked report |

### End-to-end usage

```bash
cd /Users/ashwin.joshi/IxPortUtilizationPlotter
python3 -m venv .venv
.venv/bin/pip install -r collector/requirements.txt

export INVENTORY_EXPLORER_URL=http://ixnse.ashai.online:3001
export SESSION_EXPLORER_URL=http://ixnse.ashai.online:8080

.venv/bin/python scripts/sync_true_port_utilization.py
```

### CLI options

| Flag | Effect |
|------|--------|
| `--inventory-url`, `--session-url` | Override API base URLs |
| `--server`, `--tag` | Filter Session Explorer |
| `--chassis` | Filter output by chassis IP |
| `--limit N` | Print at most N rows in main table |
| `--sample` | Print one joined record as JSON + detail |
| `--blocked-only` | Main table shows only `blocked=True` rows |

Output sections:

1. **Main table** — `chassis | port | transmitState | cp | dp | utilization | blocked`
2. **Blocked ports (owner)** — all blocked ports in scope (respects `--chassis`; not affected by `--blocked-only` filter on the summary)

---

## Tests

`tests/test_port_blocked.py` — unit tests for:

- No owner / `Free` → not blocked
- Case 1: owned, `transmitState=0`, `cp=False` → blocked
- Case 2: owned, `transmitState=0`, `cp=True` → not blocked
- Case 3: owned, `transmitState=1` → not blocked

Run (with venv + deps installed):

```bash
.venv/bin/python -m pytest tests/test_port_blocked.py -q
```

---

## Verified live run (Progress 1 baseline)

Against `ixnse.ashai.online` (from Progress 1):

| Step | Count |
|------|-------|
| Inventory ports | 47 |
| Session ports | 6 |
| Joined rows | 47 |

**Example joined session ports** (inventory chassis `10.36.236.121`):

| chassis | port | owner | transmitState | cp | dp | utilization | blocked* |
|---------|------|-------|---------------|-----|-----|-------------|----------|
| 10.36.236.121 | 6.3 | IxNetwork/ixnetworkweb/admin-3-1111627 | 0 | True | False | True | False (Case 2) |
| 10.36.236.121 | 6.4 | IxNetwork/ixnetworkweb/admin-3-1111627 | 0 | True | False | True | False (Case 2) |

\*Blocked column computed by Progress 2 logic: owned + `transmitState=0` + `cp=True` → not blocked.

**Note:** Session Explorer on `localhost:8080` fails in this environment; use `http://ixnse.ashai.online:8080`.

---

## Dependencies

`collector/requirements.txt`:

- `aiohttp>=3.9` — Session Explorer client
- `influxdb-client`, `APScheduler`, `python-dotenv` — planned / future pipeline

---

## Related repo assets

- OpenAPI: `docs/IxiaInventoryExplorer_openapi.json`, `docs/IxNetworkSessionExplorer_openapi.json`
- Grafana: `grafana/dashboards/` (port heatmap, history, owner leaderboard)
- InfluxDB: `grafana/provisioning/datasources/influxdb.yml`, `influxdb/setup.sh`
- Vision: `documents/vision_prd.md`

---

## Open questions (from design review)

1. **Unowned ports** — Currently: empty owner or `Free` (case-insensitive). Should values like `N/A` also skip blocked evaluation?
2. **Unknown transmitState** — Non-`0`/`1` values after normalization are treated as not blocked. Should they default to `"0"` for owned ports?

---

## Known gaps / next steps

1. **SQLite persistence** — Described in Progress 1 but not present; re-add if historical storage / `--db-only` re-join is needed.
2. **InfluxDB / Grafana** — Dashboards exist; no continuous write of `blocked` + `owner` metrics yet.
3. **Poller / scheduler** — No periodic collector loop; manual CLI run only.
4. **Default Session Explorer URL** — Still `localhost:8080`; set `SESSION_EXPLORER_URL` or `--session-url` in production.
5. **Chassis coverage** — Join is inventory-driven (LEFT JOIN); session-only chassis rows are dropped.
6. **Grafana blocked view** — Panel or alert on `blocked=True` with owner label.

---

## File map (current)

```
collector/
  __init__.py
  join_keys.py
  port_blocked.py          ← blocked detection (Progress 2)
  ports_client.py
  session_ports_client.py
  true_port_utilization.py
  requirements.txt

scripts/
  list_session_ports.py
  sync_true_port_utilization.py

tests/
  test_port_blocked.py

docs/
  IxiaInventoryExplorer_openapi.json
  IxNetworkSessionExplorer_openapi.json

grafana/
  dashboards/
  provisioning/

Progress1.md
Progress2.md
```
