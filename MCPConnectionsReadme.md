# IxPort MCP Server — Connection Guide

The MCP server runs on port **8887** (StreamableHTTP transport) and starts automatically with `./start.sh`.

MCP endpoint: `http://localhost:8887/mcp`

---

## Claude Code (recommended)

Native StreamableHTTP support — no proxy needed.

**Via CLI:**
```bash
claude mcp add --transport http ixport http://localhost:8887/mcp
```

**Via `settings.json`:**
```json
{
  "mcpServers": {
    "ixport": {
      "url": "http://localhost:8887/mcp"
    }
  }
}
```

---

## Claude Desktop / stdio-only clients

Claude Desktop only speaks stdio. Use `mcp-remote` as a local proxy bridge.

**`claude_desktop_config.json`:**
```json
{
  "mcpServers": {
    "ixport": {
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "http://localhost:8887/mcp"]
    }
  }
}
```

No install needed — `npx` fetches `mcp-remote` on first run.

---

## Other clients (Cursor, Windsurf, etc.)

Use `mcp-remote` if the client is stdio-only:
```json
{
  "mcpServers": {
    "ixport": {
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "http://localhost:8887/mcp"]
    }
  }
}
```

Use `url` directly if the client supports StreamableHTTP natively.

---

## When to use which

| Client | Method |
|--------|--------|
| Claude Code | `url` field (native StreamableHTTP) |
| Claude Desktop | `mcp-remote` (stdio bridge) |
| Cursor / Windsurf | `mcp-remote` (stdio-only) |
| Custom app (MCP SDK) | `url` directly |

---

## Available Tools

| Tool | Description |
|------|-------------|
| `ixport_get_blocked_ports` | Ports that are owned + in-session + idle. Returns port list and per-owner hog count. |
| `ixport_get_owned_ports` | All owned ports with per-port `blocked` status, session info, CP/DP flags. |
| `ixport_get_owner_summary` | Ranked list of users hogging the most blocked ports — use for triage. |

All tools accept optional filters: `chassis` (IP), `server` (IxNetwork server name), `tag` (session tag), `refresh` (bool — force fresh poll).

---

## Verify server is running

```bash
docker compose ps          # ixport-mcp should show "Up"
curl http://localhost:8887/mcp   # should return MCP protocol response
```
