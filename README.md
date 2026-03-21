# Swarm Intelligence Simulator

A MiroFish-inspired Swarm Intelligence Simulator powered by Ollama (`qwen:0.5b`) and Python Asyncio.

## Architecture
- **Backend**: Flask + Flask-SocketIO (WebSockets)
- **Frontend**: React + Vite + Tailwind CSS
- **AI Model**: Ollama `qwen:0.5b` (Stateless agent logic)
- **Parallelism**: Python `asyncio.gather` for real-time agent thinking.

## Setup

### Backend
1. Install [Ollama](https://ollama.ai/) and pull the model: `ollama pull qwen:0.5b`
2. Navigate to `/server`
3. Install dependencies: `pip install -r requirements.txt`
4. Run the server: `python app.py`

### Frontend
1. Navigate to `/client`
2. Install dependencies: `npm install`
3. Run the development server: `npm run dev`

## Features
- XML-tag based agent output parsing (robust for small models).
- Resource trading mechanics with portfolio constraints.
- Real-time dashboard with charts and chat logs.
- User impersonation for manual intervention.
