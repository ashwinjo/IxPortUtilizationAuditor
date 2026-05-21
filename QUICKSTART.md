# Quickstart

Fresh clone → blocked-port watch in a few minutes. Assumes you already have **Ixia Inventory Explorer** and **IxNetwork Session Explorer** running and reachable on your network.

## 1. Prerequisites


| Requirement       | Notes                                                                |
| ----------------- | -------------------------------------------------------------------- |
| **Python 3.11+**  | `python3 --version`                                                  |
| **git**           | To clone the repo                                                    |
| **Explorer URLs** | Base URLs for inventory + session APIs (no API keys in this project) |
| **Docker**        | Optional — only if you want InfluxDB history                         |


## 2. Clone and install

```bash
git clone <your-repo-url> IxPortUtilizationAuditor
cd IxPortUtilizationAuditor

```

> On Debian/Ubuntu systems, you need to install the python3-venv package using the following command.
> apt install python3.10-venv

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your Explorer base URLs:

```bash
INVENTORY_EXPLORER_URL=http://<inventory-host>:<port>
SESSION_EXPLORER_URL=http://<session-host>:<port>
```

Defaults for poll timing are usually fine (`REFRESH_SETTLE_SECONDS=3`). You can skip all `INFLUXDB_*` variables unless you use the optional metrics poller (step 6).

## 4. Smoke test (CLI)

From the repo root, with the venv active:

```bash
.venv/bin/python scripts/sync_true_port_utilization.py --blocked
```

You should see:

1. A log line about refreshing inventory/session (unless you pass `--no-refresh`)
2. A **main table** of blocked ports
3. An **owner report** for blocked ports

If this fails, check Explorer URLs, firewall, and that both services are up. Use `--no-refresh` for a faster read of cached data:

```bash
.venv/bin/python scripts/sync_true_port_utilization.py --blocked --no-refresh
```

## 5. Run the HTML dashboard (recommended)

Keep a browser tab open; it refreshes every **5 minutes**:

```bash
.venv/bin/python scripts/port_watch_dashboard.py
```

Open `http://<your-host>:8765` (listens on all interfaces; `http://127.0.0.1:8765` works on the same machine)


| Section         | Same as CLI |
| --------------- | ----------- |
| Blocked ports   | `--blocked` |
| All owned ports | `--all`     |


**Useful flags:**

```bash
# Faster snapshots (no on-demand poll to explorers)
.venv/bin/python scripts/port_watch_dashboard.py --no-refresh

# Localhost only
.venv/bin/python scripts/port_watch_dashboard.py --host 127.0.0.1
```

Leave the terminal running while you use the dashboard. Press `Ctrl+C` to stop.

## 6. Optional: InfluxDB time series

Skip this if you only need live CLI/HTML views.

```bash
docker compose up -d
```

Set in `.env` (token must match `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` in `docker-compose.yml`):

```bash
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=<token-from-docker-compose>
INFLUXDB_ORG=ixport
INFLUXDB_BUCKET=port_metrics
```

Write snapshots every 5 minutes:

```bash
.venv/bin/python scripts/poll_port_metrics.py
```

One-shot test:

```bash
.venv/bin/python scripts/poll_port_metrics.py --once
```

## 7. Cheat sheet


| Goal                        | Command                                                            |
| --------------------------- | ------------------------------------------------------------------ |
| Blocked ports in terminal   | `.venv/bin/python scripts/sync_true_port_utilization.py --blocked` |
| All owned ports in terminal | `.venv/bin/python scripts/sync_true_port_utilization.py --all`     |
| Browser watch (5m refresh)  | `.venv/bin/python scripts/port_watch_dashboard.py`                 |
| One chassis                 | add `--chassis 10.x.x.x`                                           |
| Session filter              | add `--server <name>` or `--tag <tag>`                             |
| Blocked rules reference     | [docs/blocked_port_rubric.md](docs/blocked_port_rubric.md)         |
| Full docs                   | [README.md](README.md)                                             |


## 8. Run tests (optional)

```bash
.venv/bin/python -m pytest -q
```

## Troubleshooting


| Symptom                     | Things to try                                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Connection / timeout errors | Confirm `INVENTORY_EXPLORER_URL` and `SESSION_EXPLORER_URL` in `.env`; curl both bases from the same machine |
| Empty blocked table         | Lab may have no blocked ports; try `--all` to see owned ports                                                |
| Slow first load             | Normal — default run triggers both Explorer polls; use `--no-refresh` for cache-only                         |
| Dashboard shows old data    | Click **Refresh now** or wait for the 5m cycle; server caches snapshots for 5m too                           |


