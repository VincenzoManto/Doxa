# Quick Start

This guide gets Doxa running locally or with Docker in a few minutes.

## Prerequisites

- Python 3.10+
- Node.js 20+
- Docker Desktop (optional, recommended for first run)
- At least one supported LLM provider key if your scenario uses hosted models

## Environment Setup

1. Copy `.env.example` to `.env`.
2. Populate the variables you need:
   - `OPENAI_API_KEY` for OpenAI models
   - `GOOGLE_API_KEY` for Gemini models
   - `GROK_API_KEY` for Grok models
3. Leave unused providers blank.

## Option A: Docker

Run everything with containers:

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5000`

To stop:

```bash
docker compose down
```

## Option B: Local Development

### Backend

```bash
cd server
pip install -r requirements-dev.txt
uvicorn api:app --host 0.0.0.0 --port 5000 --reload
```

### Frontend

```bash
cd client
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `http://localhost:5000`.

## Run Tests

```bash
cd server
pytest tests -v
```

## First Simulation

The repository ships with `hormuz.yaml` as the baseline scenario.

1. Start the backend.
2. Open the client.
3. Load the scenario through the UI or use the API endpoints exposed by `api.py`.

Additional examples are available in `scenarios/`:

- `info-diffusion.yaml`
- `financial-market.yaml`
- `resource-scarcity.yaml`
- `policy-stress.yaml`
- `ai-negotiation.yaml`

## Project Layout

- `server/` — FastAPI API and simulation engine
- `client/` — React/Vite frontend
- `hormuz.yaml` — reference scenario
- `scenarios/` — additional launch scenarios
- `CONFIG_YAML_REFERENCE.md` — YAML schema reference
- `PAPER.md` — formal whitepaper