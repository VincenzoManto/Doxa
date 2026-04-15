from importlib import import_module
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_FILES = sorted((REPO_ROOT / "scenarios").glob("*.yaml"))


class DummyChatbot:
    def __init__(self, engine):
        self.engine = engine


@pytest.fixture
def doxa_engine_module(monkeypatch):
    module = import_module("engine.DoxaEngine")
    monkeypatch.setattr(module, "DoxaChatbot", DummyChatbot)
    monkeypatch.setattr(module.DoxaEngine, "startOllama", lambda self: None)
    return module


def test_scenario_directory_contains_baseline_hormuz():
    assert (REPO_ROOT / "scenarios" / "hormuz.yaml").exists()


def test_engine_can_instantiate_against_all_launch_scenarios(doxa_engine_module):
    assert SCENARIO_FILES, "Expected launch scenarios under scenarios/"

    for scenario_path in SCENARIO_FILES:
        yaml_text = scenario_path.read_text(encoding="utf-8")
        engine = doxa_engine_module.DoxaEngine(yaml_text, log_verbose=False)

        assert engine.raw_config["actors"]
        assert engine.get_config()["config"]["actors"]
        assert engine.validate_yaml(yaml_text)["valid"] is True