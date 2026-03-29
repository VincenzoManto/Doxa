"""
REST API and WebSocket server for DoxaEngineV26 (engine.py)
- Exposes all engine features via HTTP endpoints
- Provides two WebSocket endpoints:
    1. /ws/agents: real-time agent actions, chat, and personal portfolios
    2. /ws/resources: real-time resource updates
"""
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, List
from engine import DoxaEngineV26, config_yaml

app = FastAPI()

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Engine instance ---
engine = DoxaEngineV26(config_yaml)
engine.env.reset(engine.raw_config['actors'])

# --- WebSocket manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

agents_manager = ConnectionManager()
resources_manager = ConnectionManager()

# --- Utility: broadcast hooks ---
def broadcast_agent_event(event: Dict[str, Any]):
    asyncio.create_task(agents_manager.broadcast(json.dumps(event)))
def broadcast_resource_event(event: Dict[str, Any]):
    asyncio.create_task(resources_manager.broadcast(json.dumps(event)))

# --- REST API: Expose all engine features ---
@app.get("/api/export")
def export_data(query: Dict[str, Any] = None, format: str = "json"):
    return JSONResponse(content=engine.export_data(query, format))

@app.post("/api/godmode")
def godmode(payload: Dict[str, Any]):
    action = payload.get("action")
    params = payload.get("params", {})
    result = engine.godmode(action, params)
    # Broadcast changes if relevant
    if action in ["inject_resource", "set_portfolio", "set_constraint"]:
        broadcast_resource_event({"type": action, "params": params})
    if action in ["send_message", "impersonate_action"]:
        broadcast_agent_event({"type": action, "params": params})
    return {"result": result}

@app.post("/api/step")
def step_agent(payload: Dict[str, Any]):
    agent_id = payload.get("agent_id")
    engine._step_agent(agent_id)
    # Broadcast agent and resource updates
    broadcast_agent_event({"type": "step", "agent_id": agent_id})
    broadcast_resource_event({"type": "step", "agent_id": agent_id})
    return {"result": "stepped"}

@app.post("/api/reset")
def reset():
    engine.env.reset(engine.raw_config['actors'])
    broadcast_agent_event({"type": "reset"})
    broadcast_resource_event({"type": "reset"})
    return {"result": "reset"}

@app.get("/api/agents")
def get_agents():
    return {"agents": list(engine.env.agents.keys())}

@app.get("/api/portfolios")
def get_portfolios():
    return {"portfolios": engine.env.portfolios}

@app.get("/api/trades")
def get_trades():
    return {"trades": engine.env.pending_trades}

@app.get("/api/agent/{agent_id}")
def get_agent(agent_id: str):
    agent = engine.env.agents.get(agent_id)
    if not agent:
        return JSONResponse(status_code=404, content={"error": "Agent not found"})
    return {"agent": agent_id, "portfolio": engine.env.portfolios.get(agent_id, {})}

# --- WebSocket: Real-time agent actions, chat, portfolios ---
@app.websocket("/ws/agents")
async def ws_agents(websocket: WebSocket):
    await agents_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        agents_manager.disconnect(websocket)

# --- WebSocket: Real-time resources ---
@app.websocket("/ws/resources")
async def ws_resources(websocket: WebSocket):
    await resources_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        resources_manager.disconnect(websocket)

# --- Startup: Optionally run engine or background tasks ---
# (Add background tasks if needed for continuous simulation)

# --- Main ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
