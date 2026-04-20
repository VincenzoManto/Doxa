"""
REST API and WebSocket server for DoxaEngine (engine.py)
- Exposes all engine features via HTTP endpoints
- Provides two WebSocket endpoints:
    1. /ws/agents: real-time agent actions, chat, and personal portfolios
    2. /ws/resources: real-time resource updates
"""
"""
REST API and WebSocket server for DoxaEngine (engine.py)
- Exposes all engine features via HTTP endpoints
- Provides two WebSocket endpoints:
    1. /ws/agents: real-time agent actions, chat, and personal portfolios
    2. /ws/resources: real-time resource updates

NOTE: To run with reload, use:
    uvicorn api:app --host 0.0.0.0 --port 5000 --reload
"""
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Depends, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional

from fastapi.responses import JSONResponse, Response
from engine.DoxaEngine import DoxaEngine, config_yaml

logger = logging.getLogger(__name__)
SERVER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SERVER_ROOT.parent
SCENARIOS_ROOT = (REPO_ROOT / "scenarios").resolve()
SECRET_FIELD_NAMES = {"api_key", "token", "secret", "password"}


def get_allowed_origins() -> List[str]:
    raw_origins = os.environ.get("DOXA_CORS_ORIGINS", "")
    if raw_origins.strip():
        return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    asyncio.create_task(socket_worker())
    yield
    # Shutdown (if needed)
    pass

app = FastAPI(lifespan=lifespan)

# --- Gestore Connessioni WebSocket ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        msg_str = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(msg_str)
            except Exception:
                logger.exception("Failed to broadcast websocket message")

manager = ConnectionManager()

# --- Coda asyncio per il bridge thread → loop async (zero latency) ---
event_queue: asyncio.Queue = asyncio.Queue()
_main_loop: asyncio.AbstractEventLoop | None = None

# --- Logger per l'Engine ---
class SocketLogger:
    """Invia i log alla coda asyncio invece di stamparli e basta"""
    def __init__(self):
        self.event_sink = None

    def _emit(self, payload):
        event = self.event_sink(payload) if self.event_sink else payload
        if _main_loop and not _main_loop.is_closed():
            _main_loop.call_soon_threadsafe(event_queue.put_nowait, event)

    def print_kill(self, agent_id, reason): self._emit({"type": "kill", "agent": agent_id, "reason": reason})
    def print_header(self, text): self._emit({"type": "header", "text": text})
    def print_epoch(self, n): self._emit({"type": "epoch", "epoch": n})
    def print_step(self, step): self._emit({"type": "step", "step": step})
    def print_turn(self, agent_id): self._emit({"type": "turn", "agent": agent_id})
    def print_think(self, agent_id, thought): self._emit({"type": "think", "agent": agent_id, "thought": thought})
    def print_action(self, agent_id, action, target, res):
        self._emit({"type": "action", "agent": agent_id, "action": action, "target": target, "result": res})
    def print_delta(self, before, after): self._emit({"type": "delta", "before": before, "after": after})
    def print_victory(self, text): self._emit({"type": "victory", "text": text})
    def print(self, text): self._emit({"type": "log", "text": text})
    def print_communication(self, sender, message, target = "PUBLIC"):
        self._emit({"type": "communication", "agent": sender, "text": message, "target": target})
    def print_trade(self, agent_id, target, give_res, give_qty, take_res, take_qty, result):
        self._emit({
            "type": "trade",
            "agent": agent_id,
            "target": target,
            "give": {"resource": give_res, "qty": give_qty},
            "take": {"resource": take_res, "qty": take_qty},
            "result": result,
        })
    def print_market_fill(self, buyer, seller, qty, resource, price, currency):
        self._emit({"type": "market_fill", "buyer": buyer, "seller": seller,
                    "qty": qty, "resource": resource, "price": price, "currency": currency})

    def print_setup(self, text: str):
        self._emit({"type": "setup", "text": text})

# Tipi di eventi che richiedono l'emissione di uno snapshot WS
_SNAPSHOT_TRIGGER_TYPES = {"step", "kill", "victory", "reset", "epoch", "manual_step", "config_updated", "config_loaded", "market_fill", "world_event"}

# --- Worker Asincrono ---
async def socket_worker():
    """Legge dalla coda asyncio e trasmette ai WebSocket连接"""
    while True:
        try:
            event = await event_queue.get()
            await manager.broadcast(event)
            # Dopo eventi chiave, emetti anche uno snapshot di stato completo
            if event.get("type") in _SNAPSHOT_TRIGGER_TYPES:
                snap = engine.make_ws_snapshot()
                if snap:
                    await manager.broadcast(snap)
        except Exception:
            logger.exception("Socket worker failed while processing an event")

socket_logger = SocketLogger()
engine = DoxaEngine(config_yaml, logger=socket_logger)
socket_logger.event_sink = engine.record_event


def publish_event(payload: Dict[str, Any]):
    event_queue.put(engine.record_event(payload))


def require_admin_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    expected_api_key = os.environ.get("DOXA_API_KEY")
    if expected_api_key and x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def sanitize_for_response(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SECRET_FIELD_NAMES:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = sanitize_for_response(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_response(item) for item in value]
    return value


def ensure_websocket_api_key(websocket: WebSocket) -> bool:
    expected_api_key = os.environ.get("DOXA_API_KEY")
    if not expected_api_key:
        return True

    provided_api_key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    return provided_api_key == expected_api_key


def resolve_scenario_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate.suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(status_code=400, detail="Scenario path must point to a YAML file")

    try:
        candidate.relative_to(SCENARIOS_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Scenario path must be inside the scenarios directory") from exc

    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Scenario file not found")

    return candidate


@app.post("/api/run")
def run_simulation(_auth: None = Depends(require_admin_api_key)):
    try:
        publish_event({"type": "setup", "text": "Registering agent tools and starting simulation…"})
        status = engine.start_run()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_event({"type": "status", "text": "Simulation started", **status})
    return status


@app.post("/api/pause")
def pause_simulation(_auth: None = Depends(require_admin_api_key)):
    try:
        status = engine.pause_run()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_event({"type": "status", "text": "Simulation paused", **status})
    return status


@app.post("/api/resume")
def resume_simulation(_auth: None = Depends(require_admin_api_key)):
    try:
        status = engine.resume_run()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_event({"type": "status", "text": "Simulation resumed", **status})
    return status


@app.post("/api/restart")
def restart_simulation(_auth: None = Depends(require_admin_api_key)):
    try:
        status = engine.restart_run()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_event({"type": "status", "text": "Simulation restarted", **status})
    return status


@app.get("/api/status")
def get_status(_auth: None = Depends(require_admin_api_key)):
    return engine.get_status()

# engine.env.reset(engine.raw_config['actors'])
# Endpoint REST: chatbot Q&A
@app.post("/api/chatbot")
def chatbot_query(payload: Dict[str, Any], _auth: None = Depends(require_admin_api_key)):
    query = payload.get("query")
    if not query:
        return JSONResponse(status_code=400, content={"error": "Missing query"})
    try:
        answer = engine.chatbot.answer(query)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    return {"answer": answer}

# --- REST API: Expose all engine features ---
@app.get("/api/export")
def export_data(format: str = Query(default="json"), _auth: None = Depends(require_admin_api_key)):
    try:
        return JSONResponse(content=engine.export_data(None, format))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/export.zip")
def export_zip(_auth: None = Depends(require_admin_api_key)):
    zip_bytes = engine.build_export_zip()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=doxa-export.zip"},
    )


@app.get("/api/events")
def get_events(
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _auth: None = Depends(require_admin_api_key),
):
    events, total = engine.get_events_page(limit, offset)
    return {"events": events, "total": total, "offset": offset, "limit": limit}


@app.get("/api/timeline/global")
def get_global_timeline(_auth: None = Depends(require_admin_api_key)):
    return {"timeline": engine.get_global_timeline()}


@app.get("/api/timeline/agent/{agent_id}")
def get_agent_timeline(agent_id: str, _auth: None = Depends(require_admin_api_key)):
    return {"timeline": engine.get_agent_timeline(agent_id)}


@app.get("/api/memory/{agent_id}")
def get_agent_memory(agent_id: str, limit: int = Query(default=80, ge=1, le=200), _auth: None = Depends(require_admin_api_key)):
    return engine.get_agent_memory_graph(agent_id, limit)


@app.get("/api/config")
def get_config(_auth: None = Depends(require_admin_api_key)):
    return sanitize_for_response(engine.get_config())


@app.post("/api/config/validate")
def validate_config(payload: Dict[str, Any] = Body(...), _auth: None = Depends(require_admin_api_key)):
    yaml_text = payload.get("yaml_text", "")
    try:
        return sanitize_for_response(engine.validate_yaml(yaml_text))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/config")
def update_config(payload: Dict[str, Any] = Body(...), _auth: None = Depends(require_admin_api_key)):
    yaml_text = payload.get("yaml_text", "")
    try:
        publish_event({"type": "setup", "text": "Applying configuration and initialising agents…"})
        config = engine.update_config_text(yaml_text)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    publish_event({"type": "config", "text": "Configuration updated"})
    return sanitize_for_response(config)


@app.post("/api/config/load")
def load_config(payload: Dict[str, Any] = Body(...), _auth: None = Depends(require_admin_api_key)):
    path = payload.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Missing path")
    resolved_path = resolve_scenario_path(path)
    try:
        publish_event({"type": "setup", "text": f"Loading scenario from {resolved_path}…"})
        config = engine.load_config_path(str(resolved_path))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    publish_event({"type": "config", "text": f"Configuration loaded from {resolved_path}"})
    return sanitize_for_response(config)

@app.post("/api/godmode")
async def godmode(payload: Dict[str, Any] = Body(...), _auth: None = Depends(require_admin_api_key)):
    action = payload.get("action")
    params = payload.get("params", {})
    result = engine.godmode(action, params)
    # Broadcast changes if relevant
    if action in ["inject_resource", "set_portfolio", "set_constraint"]:
        publish_event({"type": "godmode", "action": action, "params": params, "result": result})
    if action in ["send_message", "impersonate_action"]:
        publish_event({"type": "godmode", "action": action, "params": params, "result": result})
    return {"result": result}

@app.post("/api/step")
async def step_agent(payload: Dict[str, Any], _auth: None = Depends(require_admin_api_key)):
    agent_id: Optional[str] = payload.get("agent_id")
    try:
        status = engine.step_once(agent_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_event({"type": "manual_step", "agent": agent_id, "text": "Manual step executed"})
    return status

@app.post("/api/reset")
async def reset(_auth: None = Depends(require_admin_api_key)):
    status = engine.reset_simulation()
    publish_event({"type": "reset", "text": "Simulation reset", **status})
    return status

@app.get("/api/agents")
def get_agents(_auth: None = Depends(require_admin_api_key)):
    return {"agents": engine.list_agents()}

@app.get("/api/portfolios")
def get_portfolios(_auth: None = Depends(require_admin_api_key)):
    return engine.export_data({"portfolios": True}, format="dict")

@app.get("/api/trades")
def get_trades(_auth: None = Depends(require_admin_api_key)):
    return {"trades": engine.env.pending_trades}

@app.get("/api/resources")
def get_resources(_auth: None = Depends(require_admin_api_key)):
    return engine.export_data({"resources": True}, format="dict")

@app.get("/api/agent/{agent_id}")
def get_agent(agent_id: str, _auth: None = Depends(require_admin_api_key)):
    details = engine.get_agent_details(agent_id)
    if not details:
        return JSONResponse(status_code=404, content={"error": "Agent not found"})
    return details

# ── Market endpoints ─────────────────────────────────────────────────────────

@app.get("/api/markets")
def get_markets(_auth: None = Depends(require_admin_api_key)):
    return {"markets": engine.get_markets()}


@app.get("/api/markets/{resource}/orderbook")
def get_market_orderbook(resource: str, depth: int = Query(default=10, ge=1, le=100), _auth: None = Depends(require_admin_api_key)):
    book = engine.get_market_orderbook(resource, depth)
    if book is None:
        return JSONResponse(status_code=404, content={"error": f"No market for '{resource}'"})
    return book


@app.get("/api/markets/{resource}/price_history")
def get_market_price_history(resource: str, _auth: None = Depends(require_admin_api_key)):
    history = engine.get_market_price_history(resource)
    if history is None:
        return JSONResponse(status_code=404, content={"error": f"No market for '{resource}'"})
    return history


# ── Relations endpoint ───────────────────────────────────────────────────────

@app.get("/api/relations")
def get_relations(_auth: None = Depends(require_admin_api_key)):
    return {"relations": engine.get_relations()}


# ── Macro metrics endpoints ──────────────────────────────────────────────────

@app.get("/api/macro")
def get_macro_metrics(_auth: None = Depends(require_admin_api_key)):
    """Latest macro snapshot: Gini, HHI, price volatility, system panic."""
    return {"macro": engine.get_macro_metrics()}


@app.get("/api/macro/history")
def get_macro_history(_auth: None = Depends(require_admin_api_key)):
    """Full macro metrics history (up to 500 ticks)."""
    return {"history": engine.get_macro_history()}


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    if not ensure_websocket_api_key(websocket):
        await websocket.close(code=1008, reason="Invalid or missing API key")
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)