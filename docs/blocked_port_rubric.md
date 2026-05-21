# Blocked / hogged port rubric (end user)

Every joined port row shows the same calculated columns:

`chassis | port | owner | session | transmitState | cp | dp | utilization | blocked`

**DP** and **utilization** are always listed next to **transmitState**, even when `blocked` is decided only from chassis + CP (or marked N/A). Use them to see the full Session Explorer picture, not only the blocked conclusion.

## Field sources

| Column | Source | Notes |
|--------|--------|--------|
| `owner` | Inventory Explorer | Empty or `Free` = unowned |
| `transmitState` | Inventory Explorer | `0` = idle on chassis, `1` = active transmit |
| `session` | Session Explorer | IxNetwork server/session, or **N/A** |
| `cp` | Session Explorer | Control plane active |
| `dp` | Session Explorer | Data plane active |
| `utilization` | Session Explorer | Utilized flag |
| `blocked` | **Derived** in this tool | See tables below |

When the port is **not** in any IxNetwork session: `session`, `cp`, `dp`, and `utilization` are **N/A**.

## Unowned / `Free` ports (available)

Empty or `Free` owner: port is **available** — `blocked` is **False** (not hogging). `cp`, `dp`, and `utilization` remain **N/A** when the port is not in any session.

| blocked (display) | Influx |
|-------------------|--------|
| **False** | `0` |

## Rubric (owned ports only)

### Port in an IxNetwork session

`blocked` uses **owner**, **transmitState**, and **cp** only. **dp** and **utilization** are shown for context.

| transmitState | CP | DP | Utilization | blocked | Meaning |
|---------------|-----|-----|-------------|---------|---------|
| `0` | `False` | (shown) | (shown) | **True** | Blocked hog — reserved, no CP traffic |
| `0` | `True` | (shown) | (shown) | **False** | Control plane in use |
| `1` | (shown) | (shown) | (shown) | **False** | Chassis transmit active — not blocked |

Typical in-use row: `transmitState=1` with `dp=True` and/or `utilization=True` (values still listed even though `blocked=False`).

### Port owned on chassis but not in any session

| transmitState | CP | DP | Utilization | blocked | Meaning |
|---------------|-----|-----|-------------|---------|---------|
| `1` | N/A | N/A | N/A | **False** | Active chassis transmit (e.g. Windows client) |
| `0` | N/A | N/A | N/A | **N/A** | Cannot conclude without session CP |
| other | N/A | N/A | N/A | **N/A** | Unknown |

## Display vs Influx

| Display | Influx `blocked` / `is_hogging` |
|---------|----------------------------------|
| `True` | `1` |
| `False` | `0` |
| `N/A` | `-1` |

Influx also stores `cp`, `dp`, and `utilization` with the same `1` / `0` / `-1` encoding.

## One-line blocked hog definition

**Owned** + **in session** + **`transmitState = 0`** + **`CP = False`** → **blocked = True**.
