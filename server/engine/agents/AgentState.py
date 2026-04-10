"""
agents.AgentState
-----------------
Defines ``AgentState``, the canonical read-only snapshot of a single
agent's economic state in the simulation world.  It is intentionally slim
(portfolio + constraints + config + liveness flag) so it can be safely
passed around, deep-copied, and serialised without carrying heavy
references to AutoGen objects.
"""
from attr import dataclass
from typing import Dict

# ==========================================
# 0. WORLD STATE — formal world representation
# ==========================================

@dataclass
class AgentState:
    """Frozen snapshot of one agent's in-world state.

    Attributes:
        agent_id:    Unique string identifier of the agent.
        portfolio:   Mapping of resource name → current quantity (float).
        constraints: Per-resource bound mappings, e.g.
                     ``{"credits": {"min": 0}, "panic": {"min": 0, "max": 1}}``.
        config:      Raw YAML actor config dict (persona, operations, etc.).
        alive:       ``False`` once the agent has been eliminated by a
                     kill condition; dead agents are removed from the active
                     ``env.agents`` dict but their state is preserved here.
    """
    agent_id: str
    portfolio: Dict[str, float]
    constraints: Dict[str, Dict]
    config: Dict
    alive: bool = True

    def get(self, resource: str, default: float = 0.0) -> float:
        """Convenience accessor — returns the agent's current quantity of
        *resource*, or *default* if the resource is absent from the portfolio."""
        return self.portfolio.get(resource, default)
