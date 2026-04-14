from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_FILES = [
    REPO_ROOT / "hormuz.yaml",
    *sorted((REPO_ROOT / "scenarios").glob("*.yaml")),
]


def test_scenario_files_exist():
    assert SCENARIO_FILES, "Expected at least one scenario YAML file"
    for scenario_path in SCENARIO_FILES:
        assert scenario_path.exists(), f"Missing scenario file: {scenario_path}"


def test_scenario_files_are_valid_yaml():
    for scenario_path in SCENARIO_FILES:
        with scenario_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        assert isinstance(data, dict), f"Scenario must load as a mapping: {scenario_path.name}"
        assert "global_rules" in data, f"Missing global_rules in {scenario_path.name}"
        assert "actors" in data, f"Missing actors in {scenario_path.name}"
        assert isinstance(data["actors"], list) and data["actors"], f"actors must be a non-empty list in {scenario_path.name}"


def test_scenario_actor_ids_are_unique_per_file():
    for scenario_path in SCENARIO_FILES:
        with scenario_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        actor_ids = [actor["id"] for actor in data["actors"]]
        assert len(actor_ids) == len(set(actor_ids)), f"Duplicate actor ids in {scenario_path.name}"