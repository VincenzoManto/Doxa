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


def test_claude_provider_configures_anthropic_api_type(monkeypatch):
    from autogen.oai.client import OpenAIWrapper
    
    # Mock the OpenAIWrapper to avoid needing anthropic package
    original_init = OpenAIWrapper.__init__
    def mock_init(self, **kwargs):
        # Just set the config without actually initializing
        self._config_list = kwargs.get("config_list", [])
        self._clients = []
    
    monkeypatch.setattr(OpenAIWrapper, "__init__", mock_init)
    
    monkeypatch.setenv("CLAUDE_URL", "https://api.claude.example/v1")
    yaml_text = """
global_rules:
  epochs: 1
  steps: 1
actors:
  - id: claude_agent
    provider: claude
    model_name: claude-3.5-std
    initial_portfolio:
      credits: 10
      panic: 0.0
"""
    module = import_module("engine.DoxaEngine")
    monkeypatch.setattr(module, "DoxaChatbot", DummyChatbot)
    monkeypatch.setattr(module.DoxaEngine, "startOllama", lambda self: None)
    engine = module.DoxaEngine(yaml_text, log_verbose=False)
    engine.env.reset(engine.raw_config["actors"])

    config_entry = engine.env.agents["claude_agent"].llm_config["config_list"][0]
    assert config_entry["api_type"] == "anthropic"
    assert str(config_entry["base_url"]) == "https://api.claude.example/v1"


def test_ollama_url_skips_local_ollama_start(monkeypatch):
    module = import_module("engine.DoxaEngine")
    called = {"start": False}
    def start_ollama(self):
        called["start"] = True
    monkeypatch.setattr(module, "DoxaChatbot", DummyChatbot)
    monkeypatch.setattr(module.DoxaEngine, "startOllama", start_ollama)
    monkeypatch.setenv("OLLAMA_URL", "http://custom-ollama.local/v1")
    yaml_text = """
global_rules:
  epochs: 1
  steps: 1
actors:
  - id: local_ollama_agent
    provider: ollama
    initial_portfolio:
      credits: 10
      panic: 0.0
"""
    engine = module.DoxaEngine(yaml_text, log_verbose=False)

    assert called["start"] is False
    engine.env.reset(engine.raw_config["actors"])
    config_entry = engine.env.agents["local_ollama_agent"].llm_config["config_list"][0]
    assert str(config_entry["base_url"]) == "http://custom-ollama.local/v1"
