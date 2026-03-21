from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import threading
import asyncio
import yaml

os.environ["OPENAI_API_KEY"] = "NA" # Dummy for CrewAI
from models import ConfigLoader, FullConfigModel
from simulation import SimulationEngine

app = Flask(__name__)
app.config['SECRET_KEY'] = 'swarm-secret!'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Load configuration and initialize engine
print("Backend: Loading configuration...")
config = ConfigLoader.load('world_config.yaml')
print(f"Backend: Config loaded. Context: {config.get_context[:50]}...")
print("Backend: Initializing SimulationEngine...")
engine = SimulationEngine(config, socketio)
print("Backend: Initialization complete.")

def run_simulation():
    print("[THREAD] run_simulation thread started.")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print("[THREAD] asyncio loop created. Calling engine.run()...")
        loop.run_until_complete(engine.run())
    except Exception as e:
        print(f"[THREAD ERROR] {e}")
    print("[THREAD] run_simulation thread finished.")

@app.route('/api/simulation/start', methods=['POST'])
def start_simulation():
    print("[API] /api/simulation/start hit!")
    if not engine.running:
        thread = threading.Thread(target=run_simulation)
        thread.daemon = True
        thread.start()
        return jsonify({"status": "started"})
    return jsonify({"status": "already running"})

@app.route('/api/simulation/inject', methods=['POST'])
def inject_action():
    try:
        data = request.json
        from models import ActionModel
        action = ActionModel(**data)
        
        # We need to run this in the loop or use a thread-safe way to put in queue
        # Since action_queue is an asyncio.Queue, we should use loop.call_soon_threadsafe if possible
        # or just a simple list if we want to avoid complex threading/async sync.
        # For now, let's assume we can push to the queue if the loop is running.
        
        # Simplified: engine has a method to inject
        engine.inject_action(action)
        return jsonify({"status": "injected", "action": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    print("[DIAGNOSTIC] Health check hit!")
    return jsonify({"status": "ok", "message": "Swarm Intelligence Simulator API is running"})

@app.route('/api/simulation/status', methods=['GET'])
def get_sim_status():
    return jsonify({
        "running": engine.running,
        "tick": engine.tick_count,
        "thinking": list(engine.thinking_actors)
    })

@app.route('/api/agents/<aid>/history', methods=['GET'])
def get_agent_history(aid):
    if aid not in engine.agents:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({
        "agent_id": aid,
        "history": engine.agents[aid].history
    })

@app.route('/api/simulation/history', methods=['GET'])
def get_global_history():
    history = []
    for aid, agent in engine.agents.items():
        for event in agent.history:
            if event["type"] in ["broadcast_out", "action_intent", "public_msg", "thought"]:
                history.append({
                    "timestamp": event["timestamp"],
                    "sender": aid,
                    "type": "public" if event["type"] != "action_intent" else "system",
                    "content": event["data"].get("content") or f"Action: {event['data'].get('type')}"
                })
    return jsonify({"history": sorted(history, key=lambda x: x["timestamp"])})

@app.route('/api/config', methods=['GET'])
def get_config():
    try:
        if os.path.exists('world_config.yaml'):
            with open('world_config.yaml', 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({"config": content})
        return jsonify({"error": "Config not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/config', methods=['POST'])
def update_config():
    global config, engine
    try:
        data = request.json
        new_content = data.get('config')
        if not new_content:
            return jsonify({"error": "No config provided"}), 400
        
        # Validate YAML
        loaded = yaml.safe_load(new_content)
        validated = FullConfigModel(**loaded)
        
        # Save to file
        with open('world_config.yaml', 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        # Hot reload existing engine
        engine.update_config(validated)
        
        return jsonify({"status": "updated", "message": "Configuration hot-reloaded successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'data': 'Connected to Swarm Engine'})

@socketio.on('join')
def on_join(data):
    room = data['room']
    from flask_socketio import join_room
    join_room(room)
    print(f"Client joined room: {room}")
    emit('status', {'msg': f'Joined room {room}'})

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    from flask_socketio import leave_room
    leave_room(room)
    print(f"Client left room: {room}")

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', debug=False, port=5000, use_reloader=False)
