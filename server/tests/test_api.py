from fastapi.testclient import TestClient

import api


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
        return {"valid": True, "config": {"raw": yaml_text}}

    def load_config_path(self, path):
        self.loaded_paths.append(path)
        return {"source": {"kind": "path", "value": path}}

    def update_config_text(self, yaml_text):
        if yaml_text == "busy":
            raise RuntimeError("engine busy")
        return {"source": {"kind": "text", "value": "api"}}


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
    assert load_response.status_code == 200
    assert stub.loaded_paths == ["scenarios/hormuz.yaml"]


def test_update_config_returns_conflict_on_runtime_error(monkeypatch):
    client, _stub = _make_client(monkeypatch)

    response = client.put("/api/config", json={"yaml_text": "busy"})

    assert response.status_code == 409
    assert response.json()["detail"] == "engine busy"