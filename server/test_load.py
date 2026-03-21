from models import ConfigLoader, FullConfigModel
import yaml

try:
    print("Attempting to load world_config.yaml...")
    config = ConfigLoader.load('world_config.yaml')
    print("SUCCESS: Configuration loaded and validated.")
    print(f"Scenario: {config.scenario_name}")
    print(f"Number of actors: {len(config.all_actors)}")
except Exception as e:
    print(f"FAILURE: {str(e)}")
