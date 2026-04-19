
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

## Option C: Pip with backend CLI only

The Doxa backend is available as a Python package on PyPI: [doxa-ai](https://pypi.org/project/doxa-ai/)

Install and use the CLI:

```bash
pip install doxa-ai
doxa run --help
```

## Run Tests

```bash
cd server
pytest tests -v
```

## First Simulation

The repository ships with `scenarios/hormuz.yaml` as the baseline scenario.

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
- `scenarios/hormuz.yaml` — reference scenario
- `scenarios/` — additional launch scenarios
- `CONFIG_YAML_REFERENCE.md` — YAML schema reference
- `PAPER.md` — formal whitepaper