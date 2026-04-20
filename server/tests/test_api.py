from pathlib import Path

from fastapi.testclient import TestClient

import api


def test_get_allowed_origins_defaults_to_local_dev(monkeypatch):
    monkeypatch.delenv("DOXA_CORS_ORIGINS", raising=False)

    origins = api.get_allowed_origins()

    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:3000" in origins


def test_get_allowed_origins_reads_env(monkeypatch):
    monkeypatch.setenv("DOXA_CORS_ORIGINS", "https://example.com, https://admin.example.com ")

    origins = api.get_allowed_origins()

    assert origins == ["https://example.com", "https://admin.example.com"]


class StubEngine:
    def __init__(self):
        self.env = type("Env", (), {"pending_trades": {}})()
        self.loaded_paths = []

    def record_event(self, payload):
        return payload

    def make_ws_snapshot(self):
        return None

    def get_status(self):
        return {"state": "idle", "epoch": 0, "step": 0}

    def get_markets(self):
        return {"gold": {"resource": "gold", "price": 10.0}}

    def get_market_orderbook(self, resource, depth):
        if resource != "gold":
            return None
        return {"resource": resource, "depth": depth, "bids": [], "asks": []}

    def get_market_price_history(self, resource):
        return {"resource": resource, "history": [10.0]} if resource == "gold" else None

    def get_relations(self):
        return [{"source": "alice", "target": "bob", "trust": 0.6, "type": "neutral"}]

    def validate_yaml(self, yaml_text):
        if not yaml_text.strip():
            raise ValueError("empty config")
        return {"valid": True, "config": {"raw": yaml_text, "api_key": "top-secret"}}

    def load_config_path(self, path):
        self.loaded_paths.append(path)
        return {"source": {"kind": "path", "value": path}}

    def update_config_text(self, yaml_text):
        if yaml_text == "busy":
            raise RuntimeError("engine busy")
        return {"source": {"kind": "text", "value": "api"}, "config": {"api_key": "hidden"}}

    def get_config(self):
        return {"config": {"provider": "openai", "api_key": "should-not-leak"}, "yaml_text": "actors: []"}

    def godmode(self, action, params):
        return f"ok:{action}"

    def step_once(self, agent_id=None):
        return {"state": "paused", "agent": agent_id}

    def reset_simulation(self):
        return {"state": "idle"}


def _make_client(monkeypatch):
    stub = StubEngine()
    monkeypatch.setattr(api, "engine", stub)
    monkeypatch.setattr(api, "publish_event", lambda payload: payload)
    client = TestClient(api.app)
    return client, stub


def test_status_markets_and_relations_endpoints(monkeypatch):
    client, _stub = _make_client(monkeypatch)

    assert client.get("/api/status").json()["state"] == "idle"
    assert "gold" in client.get("/api/markets").json()["markets"]
    assert client.get("/api/relations").json()["relations"][0]["source"] == "alice"


def test_market_orderbook_returns_404_for_unknown_market(monkeypatch):
    client, _stub = _make_client(monkeypatch)

    response = client.get("/api/markets/corn/orderbook")

    assert response.status_code == 404
    assert response.json()["error"] == "No market for 'corn'"


def test_validate_and_load_config_endpoints(monkeypatch):
    client, stub = _make_client(monkeypatch)

    validate_response = client.post("/api/config/validate", json={"yaml_text": "actors: []"})
    load_response = client.post("/api/config/load", json={"path": "scenarios/hormuz.yaml"})

    assert validate_response.status_code == 200
    assert validate_response.json()["valid"] is True
    assert validate_response.json()["config"]["api_key"] == "***REDACTED***"
    assert load_response.status_code == 200
    expected_path = str((Path(api.__file__).resolve().parent.parent / "scenarios" / "hormuz.yaml").resolve())
    assert stub.loaded_paths == [expected_path]


def test_update_config_returns_conflict_on_runtime_error(monkeypatch):
    client, _stub = _make_client(monkeypatch)

    response = client.put("/api/config", json={"yaml_text": "busy"})

    assert response.status_code == 409
    assert response.json()["detail"] == "engine busy"


def test_get_config_is_redacted(monkeypatch):
    client, _stub = _make_client(monkeypatch)

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["config"]["api_key"] == "***REDACTED***"


def test_load_config_rejects_paths_outside_scenarios(monkeypatch):
    client, stub = _make_client(monkeypatch)

    response = client.post("/api/config/load", json={"path": "README.md"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Scenario path must point to a YAML file"
    assert stub.loaded_paths == []


def test_sensitive_endpoints_require_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    response = client.post("/api/godmode", json={"action": "inject_resource", "params": {}})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_sensitive_endpoints_accept_valid_api_key(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    response = client.post(
        "/api/godmode",
        headers={"X-API-Key": "secret"},
        json={"action": "inject_resource", "params": {}},
    )

    assert response.status_code == 200
    assert response.json()["result"] == "ok:inject_resource"


def test_sensitive_endpoints_still_work_without_api_key_configuration(monkeypatch):
    monkeypatch.delenv("DOXA_API_KEY", raising=False)
    client, _stub = _make_client(monkeypatch)

    response = client.post("/api/godmode", json={"action": "inject_resource", "params": {}})

    assert response.status_code == 200
    assert response.json()["result"] == "ok:inject_resource"


def test_read_endpoints_require_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    response = client.get("/api/status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_read_endpoints_accept_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    response = client.get("/api/status", headers={"X-API-Key": "secret"})

    assert response.status_code == 200
    assert response.json()["state"] == "idle"


def test_config_endpoint_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    response = client.get("/api/config")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_websocket_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    try:
        with client.websocket_connect("/ws/events"):
            assert False, "WebSocket connection should require an API key"
    except Exception as exc:
        assert "1008" in str(exc)


def test_websocket_accepts_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DOXA_API_KEY", "secret")
    client, _stub = _make_client(monkeypatch)

    with client.websocket_connect("/ws/events?api_key=secret") as websocket:
        websocket.send_text("ping")