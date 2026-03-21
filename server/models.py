from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import yaml
import os
import time

class ActorModel(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    role: Optional[str] = None
    goal: Optional[str] = None
    backstory: Optional[str] = None
    persona: Optional[str] = None # Support hormuz.yaml
    platform: Optional[str] = None
    emotional_bias: Optional[str] = None
    portfolio: Dict[str, Any] = {} # support integer or descriptive
    influence: float = 1.0
    constraints: List[str] = []
    
    # Mapping for different YAML styles
    def get_description(self):
        return self.persona or self.description or ""

class RelationshipModel(BaseModel):
    source: str
    target: str
    trust: float
    description: Optional[str] = None

class ResourceModel(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    volatility: float = 0.0
    decay_rate: float = 0.0

class WorldConfigModel(BaseModel):
    context: str
    tick_interval: float
    process: str = "parallel" # parallel or sequential
    turn_order: List[str] = []

class GlobalPortfolioModel(BaseModel):
    id: str
    name: str
    resources: Dict[str, int]
    mining_cost: Dict[str, Any]

class RoomModel(BaseModel):
    id: str
    name: str
    members: List[str] = []

class AllianceModel(BaseModel):
    id: str
    name: str
    members: List[str] = []
    shared_resources: Dict[str, int] = {}

class LLMConfigModel(BaseModel):
    model: str = "qwen:0.5b"
    endpoint: str = "http://localhost:11434/api/chat"

class FullConfigModel(BaseModel):
    scenario_name: Optional[str] = None
    scenario_description: Optional[str] = None
    world: Optional[WorldConfigModel] = None
    llm: LLMConfigModel = Field(default_factory=LLMConfigModel)
    resources: List[ResourceModel] = []
    actors: List[ActorModel] = Field(default_factory=list)
    social_groups: List[ActorModel] = Field(default_factory=list, alias="social_groups")
    global_portfolios: List[GlobalPortfolioModel] = []
    rooms: List[RoomModel] = []
    alliances: List[AllianceModel] = []
    relationships: List[RelationshipModel] = []
    tags: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def all_actors(self) -> List[ActorModel]:
        return self.actors + self.social_groups

    @property
    def get_context(self) -> str:
        if self.world: return self.world.context
        return self.scenario_description or "Advanced Negotiation Scenario"

class ConfigLoader:
    @staticmethod
    def load(file_path: str) -> FullConfigModel:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            # Ensure pydantic can handle the data
            return FullConfigModel.model_validate(data)

    @staticmethod
    def save(file_path: str, config: FullConfigModel):
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False, sort_keys=False)

# Action Models (Internal handling)
class ActionModel(BaseModel):
    type: str  # TRADE, MESSAGE, MINE, OFFER, ACCEPT_OFFER, etc.
    sender: str
    target: Optional[str] = None
    resource: Optional[str] = None
    amount: Any = None
    exchange_resource: Optional[str] = None
    content: Optional[str] = None
    offer_id: Optional[str] = None
