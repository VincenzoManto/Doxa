"""
REST API and WebSocket server for DoxaEngineV26 (engine.py)
- Exposes all engine features via HTTP endpoints
- Provides two WebSocket endpoints:
    1. /ws/agents: real-time agent actions, chat, and personal portfolios
    2. /ws/resources: real-time resource updates
"""
"""
REST API and WebSocket server for DoxaEngineV26 (engine.py)
- Exposes all engine features via HTTP endpoints
- Provides two WebSocket endpoints:
    1. /ws/agents: real-time agent actions, chat, and personal portfolios
    2. /ws/resources: real-time resource updates

NOTE: To run with reload, use:
    uvicorn api:app --host 0.0.0.0 --port 5000 --reload
"""
import asyncio
import json
import threading
import queue
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any

from fastapi.responses import JSONResponse
from engine import DoxaEngineV26, config_yaml

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            except:
                pass

manager = ConnectionManager()

# --- Coda per i messaggi dall'Engine ---
# Usiamo una coda thread-safe per passare dati dal thread dell'Engine al loop di FastAPI
event_queue = queue.Queue()

# --- Logger per l'Engine ---
class SocketLogger:
    """Invia i log alla coda invece di stamparli e basta"""
    def print_kill(self, agent_id, reason): event_queue.put({"type": "kill", "agent": agent_id, "reason": reason})
    def print_header(self, text): event_queue.put({"type": "header", "text": text})
    def print_epoch(self, n): event_queue.put({"type": "epoch", "epoch": n})
    def print_step(self, step): event_queue.put({"type": "step", "step": step})
    def print_turn(self, agent_id): event_queue.put({"type": "turn", "agent": agent_id})
    def print_think(self, agent_id, thought): event_queue.put({"type": "think", "agent": agent_id, "thought": thought})
    def print_action(self, agent_id, action, target, res):
        event_queue.put({"type": "action", "agent": agent_id, "action": action, "target": target, "result": res})
    def print_delta(self, before, after): event_queue.put({"type": "delta", "before": before, "after": after})
    def print_victory(self, text): event_queue.put({"type": "victory", "text": text})
    def print(self, text): event_queue.put({"type": "log", "text": text})
    def print_communication(self, sender, message, target = "PUBLIC"):
        event_queue.put({"type": "communication", "agent": sender, "text": message, "target": target})

# --- Worker Asincrono ---
async def socket_worker():
    """Controlla la coda e trasmette ai WebSocket"""
    while True:
        try:
            # Esegue il polling della coda senza bloccare il loop asincrono
            if not event_queue.empty():
                event = event_queue.get_nowait()
                await manager.broadcast(event)
        except Exception as e:
            pass
        await asyncio.sleep(0.1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(socket_worker())

# --- Engine Instance ---
engine = DoxaEngineV26(config_yaml, logger=SocketLogger())  # Passiamo il SocketLogger all'engine


@app.post("/api/run")
def run_simulation():
    def run_engine():
        try:
            engine.run()
        except Exception as e:
            print(f"[ENGINE RUN ERROR] {e}")
    t = threading.Thread(target=run_engine, daemon=True)
    t.start()
    return {"result": "simulation started"}

# engine.env.reset(engine.raw_config['actors'])
# Endpoint REST: chatbot Q&A
@app.post("/api/chatbot")
def chatbot_query(payload: Dict[str, Any]):
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
def export_data(query: Dict[str, Any] = None, format: str = "json"):
    return JSONResponse(content=engine.export_data(query, format))

@app.post("/api/godmode")
async def godmode(payload: Dict[str, Any] = Body(...)):
    action = payload.get("action")
    params = payload.get("params", {})
    result = engine.godmode(action, params)
    # Broadcast changes if relevant
    if action in ["inject_resource", "set_portfolio", "set_constraint"]:
        event_queue.put({"type": "godmode", "action": action, "params": params, "result": result})
    if action in ["send_message", "impersonate_action"]:
        event_queue.put({"type": "godmode", "action": action, "params": params, "result": result})
    return {"result": result}

@app.post("/api/step")
async def step_agent(payload: Dict[str, Any]):
    agent_id = payload.get("agent_id")
    engine._step_agent(agent_id)
    # Broadcast agent and resource updates
    event_queue.put({"type": "step", "agent_id": agent_id})
    return {"result": "stepped"}

@app.post("/api/reset")
async def reset():
    engine.env.reset(engine.raw_config['actors'])
    engine.run()
    event_queue.put({"type": "reset"})
    return {"result": "reset"}

@app.get("/api/agents")
def get_agents():
    return {"agents": list(engine.env.agents.keys())}

@app.get("/api/portfolios")
def get_portfolios():
    return engine.export_data({"portfolios": True}, format="dict")

@app.get("/api/trades")
def get_trades():
    return {"trades": engine.env.pending_trades}

@app.get("/api/resources")
def get_resources():
    return engine.export_data({"resources": True}, format="dict")

@app.get("/api/agent/{agent_id}")
def get_agent(agent_id: str):
    agent = engine.env.agents.get(agent_id)
    if not agent:
        return JSONResponse(status_code=404, content={"error": "Agent not found"})
    return {"agent": agent_id, "portfolio": engine.env.portfolios.get(agent_id, {})}

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)