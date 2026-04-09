from attr import dataclass
from typing import Any, Optional
@dataclass
class WorldEventEffect:
    targets: Any            # "all" | list[str]
    resource: Optional[str] = None
    delta: Optional[float] = None      # one-time resource change
    rate: Optional[float] = None       # per-step resource change (trend)
    market: Optional[str] = None
    price_multiplier: Optional[float] = None
    price_set: Optional[float] = None
    trust_source: Optional[str] = None
    trust_delta: Optional[float] = None
    contagion_rate: float = 0.0   # fraction of delta propagated to trusted neighbors


@dataclass
class WorldEventDef:
    name: str
    event_type: str                    # shock | trend | conditional
    effect: WorldEventEffect
    trigger_tick: Optional[int] = None
    duration: int = 1                  # steps active (trend)
    condition_resource: Optional[str] = None
    condition_operator: Optional[str] = None  # lt | gt | le | ge | eq
    condition_threshold: Optional[float] = None
    condition_scope: str = "any_agent"   # any_agent | all_agents
    # runtime state (reset on each run)
    triggered: bool = False
    remaining: int = 0
