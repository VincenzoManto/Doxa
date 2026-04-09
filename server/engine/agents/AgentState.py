from attr import dataclass
from typing import Dict

# ==========================================
# 0. WORLD STATE — formal world representation
# ==========================================

@dataclass
class AgentState:
    """Formal state record for one agent in the world."""
    agent_id: str
    portfolio: Dict[str, float]
    constraints: Dict[str, Dict]
    config: Dict
    alive: bool = True

    def get(self, resource: str, default: float = 0.0) -> float:
        return self.portfolio.get(resource, default)
