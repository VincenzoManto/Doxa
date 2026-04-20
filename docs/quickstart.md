title: Quick Start

---
# Quick Start

## Install

# Quick Start

## Install

```bash
pip install doxa-ai
```

## Run a Scenario

You can run any scenario from the provided examples. For instance:

```bash
doxa run scenarios/hormuz.yaml
```

Replace `hormuz.yaml` with any other scenario file from the `scenarios/` folder as needed.

## Start the API Server

```bash
pip install doxa-ai
uvicorn api:app --host 0.0.0.0 --port 5000
```

## Security Configuration (optional)

The server runs in open mode by default. To restrict access, set environment variables before starting:

```bash
# Require an API key for every endpoint and the WebSocket
export DOXA_API_KEY="your-secret-key"

# Restrict CORS to specific deployed origins (comma-separated)
export DOXA_CORS_ORIGINS="https://my-app.example.com"

uvicorn api:app --host 0.0.0.0 --port 5000
```

Then pass the key in every request:

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:5000/api/status
```

Or via the WebSocket query param:

```
ws://localhost:5000/ws/events?api_key=your-secret-key
```

Without `DOXA_API_KEY` set, the server behaves as before with no access control — suitable for local research use.
