# API Reference

The Doxa backend runs on **port 5000**. All REST paths are prefixed with `/api/`.
A WebSocket endpoint at `/ws/events` delivers a real-time event stream.

!!! info "Interactive docs"
    FastAPI auto-generates interactive Swagger UI at
    [`http://localhost:5000/docs`](http://localhost:5000/docs) when the server is running.

---

## Security

### API Key Authentication

By default (local / development mode) all endpoints are open.  
To enable authentication, set the `DOXA_API_KEY` environment variable before starting the server:

```bash
export DOXA_API_KEY="your-secret-key"
uvicorn api:app --host 0.0.0.0 --port 5000
```

Once set, **every** endpoint — both read and write — requires the header:

```
X-API-Key: your-secret-key
```

Requests without a valid key receive `401 Unauthorized`.

The WebSocket endpoint also requires the key, either as a header or a query parameter:

```
# header (preferred)
X-API-Key: your-secret-key

# query param (use when headers are unavailable, e.g. browser WebSocket)
ws://localhost:5000/ws/events?api_key=your-secret-key
```

### Secret Redaction

The endpoints that return configuration data (`/api/config`, `/api/config/validate`, `PUT /api/config`, `POST /api/config/load`) automatically redact fields named `api_key`, `token`, `secret`, or `password` from their responses, replacing the value with `***REDACTED***`.

### CORS

By default, the server allows requests from the following local origins only:

```
http://localhost:3000   http://127.0.0.1:3000
http://localhost:4173   http://127.0.0.1:4173
http://localhost:5000   http://127.0.0.1:5000
http://localhost:5173   http://127.0.0.1:5173
```

To allow additional origins (e.g. a deployed frontend), set `DOXA_CORS_ORIGINS` as a comma-separated list:

```bash
export DOXA_CORS_ORIGINS="https://my-app.example.com,https://admin.example.com"
```

### Scenario Path Restriction

The `POST /api/config/load` endpoint accepts **only** `.yaml` or `.yml` files located inside the `scenarios/` directory at the repository root. Absolute paths, paths that escape `scenarios/`, and non-YAML extensions are rejected with `400 Bad Request`.

---

## Simulation Control

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-post">POST</span> | `/api/run` | Start the simulation. Returns `409` if already running. |
| <span class="http-post">POST</span> | `/api/pause` | Pause a running simulation. Returns `409` if not running. |
| <span class="http-post">POST</span> | `/api/resume` | Resume a paused simulation. |
| <span class="http-post">POST</span> | `/api/restart` | Restart from the beginning of the loaded scenario. |
| <span class="http-post">POST</span> | `/api/reset` | Reset simulation state without reloading config. |
| <span class="http-post">POST</span> | `/api/step` | Execute one agent step. Body: `{ "agent_id": "player" }` for a specific agent, or omit to step all agents. Returns `409` if simulation is in an incompatible state. |
| <span class="http-get">GET</span>   | `/api/status` | Return current simulation status (phase, epoch, tick, agent count). |

---

## Configuration

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span>   | `/api/config` | Return the active, parsed YAML config. |
| <span class="http-put">PUT</span>   | `/api/config` | Hot-reload config. Body: `{ "yaml_text": "..." }`. Returns `409` if the simulation is currently running, `400` on parse error. |
| <span class="http-post">POST</span> | `/api/config/validate` | Validate raw YAML without applying it. Body: `{ "yaml_text": "..." }`. Returns `{ "valid": true }` or `{ "valid": false, "error": "..." }`. |
| <span class="http-post">POST</span> | `/api/config/load` | Load a scenario from a path relative to the repository root. Body: `{ "path": "scenarios/hormuz.yaml" }`. The path must resolve to a `.yaml`/`.yml` file inside `scenarios/`. Returns `400` for invalid paths, `409` if running. |

---

## Agents & Portfolios

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span> | `/api/agents` | List all active agent IDs. |
| <span class="http-get">GET</span> | `/api/agent/{agent_id}` | Full details for one agent — portfolio, constraints, status. Returns `404` if not found. |
| <span class="http-get">GET</span> | `/api/portfolios` | All agent portfolios as a flat object. |
| <span class="http-get">GET</span> | `/api/resources` | Resource snapshot across all agents. |
| <span class="http-get">GET</span> | `/api/trades` | Current pending trade list. |

---

## Markets

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span> | `/api/markets` | List all active markets with current prices and metadata. |
| <span class="http-get">GET</span> | `/api/markets/{resource}/orderbook` | Live order book for a resource. Query param: `depth` (default `10`, max `100`). Returns `404` if no market exists for the resource. |
| <span class="http-get">GET</span> | `/api/markets/{resource}/price_history` | Full price history for a resource market. Returns `404` if not found. |

---

## Relations & Social Graph

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span> | `/api/relations` | Full trust graph — every directed agent-to-agent relation record, including label and trust score. |

---

## Macro Metrics

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span> | `/api/macro` | Latest macro snapshot: Gini coefficient, HHI, price volatility, system panic average. |
| <span class="http-get">GET</span> | `/api/macro/history` | Full macro metrics history (up to 500 ticks). |

---

## Events & Timelines

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span> | `/api/events` | Paginated simulation event log. Query params: `limit` (default `500`, max `5000`), `offset` (default `0`). Response: `{ "events": [...], "total": N, "offset": N, "limit": N }`. |
| <span class="http-get">GET</span> | `/api/timeline/global` | Global simulation timeline (one entry per tick). |
| <span class="http-get">GET</span> | `/api/timeline/agent/{agent_id}` | Per-agent timeline of decisions, trades, and resource changes. |

---

## Memory & Export

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-get">GET</span> | `/api/memory/{agent_id}` | RAG memory graph for one agent. Query param: `limit` (default `80`, max `200`). |
| <span class="http-get">GET</span> | `/api/export` | Export full simulation data as JSON. Query param: `format` (default `json`). |
| <span class="http-get">GET</span> | `/api/export.zip` | Download a complete export ZIP archive (`doxa-export.zip`). |

---

## Chatbot

| Method | Path | Description |
|--------|------|-------------|
| <span class="http-post">POST</span> | `/api/chatbot` | Query the simulation assistant. Body: `{ "query": "Who has the most gold?" }`. Response: `{ "answer": "..." }`. Returns `400` if query is missing, `500` on internal error. |

---

## God Mode

<span class="http-post">POST</span> `/api/godmode`

Run privileged out-of-band actions on a live or paused simulation.
Body: `{ "action": "<action>", "params": { ... } }`.

| Action | Description | Required params |
|--------|-------------|-----------------|
| `inject_resource` | Add or subtract resources from an agent's portfolio. | `agent_id`, `resource`, `delta` |
| `set_portfolio` | Overwrite an agent's entire portfolio. | `agent_id`, `portfolio` (object) |
| `set_constraint` | Update an agent's constraint bounds at runtime. | `agent_id`, `resource`, `min`, `max` |
| `send_message` | Inject a message into an agent's conversation context. | `agent_id`, `message` |
| `impersonate_action` | Execute a tool call as if a specific agent made it. | `agent_id`, `action`, `params` |

Actions `inject_resource`, `set_portfolio`, `set_constraint`, `send_message`, and
`impersonate_action` all broadcast a `godmode` event over the WebSocket stream.

---

## WebSocket

<span class="http-ws">WS</span> `/ws/events`

Connect to receive a real-time stream of simulation events as JSON objects.
Send any text frame to keep the connection alive (the server echoes nothing back).

### Event envelope

```json
{
  "type": "resource_update",
  "agent_id": "player",
  "resource": "gold",
  "new_value": 12.0,
  "tick": 4,
  "epoch": 1
}
```

### Common event types

| `type` | Fired when |
|--------|-----------|
| `status` | Simulation state changes (run / pause / resume / restart). |
| `resource_update` | An agent's portfolio changes. |
| `trade` | A trade executes (OTC or LOB fill). |
| `market_update` | A market price or order book changes. |
| `relation_update` | Trust between two agents changes. |
| `world_event` | A world event fires. |
| `agent_turn` | An agent completes its turn. |
| `kill` | An agent is eliminated by a kill condition. |
| `victory` | A victory condition is met. |
| `config` | The active configuration changes. |
| `godmode` | A god-mode action is applied. |
| `reset` | Simulation is reset. |
| `manual_step` | A manual `/api/step` executes. |

### Example: Python client

```python
import asyncio, json, websockets

async def stream():
    async with websockets.connect("ws://localhost:5000/ws/events") as ws:
        async for msg in ws:
            event = json.loads(msg)
            print(event["type"], event)

asyncio.run(stream())
```
