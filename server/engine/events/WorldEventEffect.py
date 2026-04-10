"""
events.WorldEventEffect
-----------------------
Data classes that describe *what* a world event does and its full
definition (trigger, type, duration, effect, runtime state).

Two classes are defined here:

* ``WorldEventEffect`` — the effect payload (what happens when the event fires).
* ``WorldEventDef``    — the complete event specification, including trigger
                         logic and mutable runtime state (triggered flag,
                         remaining tick counter for trends).

These classes are populated by ``WorldEventScheduler._parse_world_event()``
and are not meant to be constructed directly by user code.
"""
from attr import dataclass
from typing import Any, Optional

@dataclass
class WorldEventEffect:
    """Describes the effect applied to the simulation when a world event fires.

    Attributes:
        targets:          ``"all"`` or a list of specific agent IDs.
        resource:         Resource to modify in agent portfolios (optional).
        delta:            One-time additive change to *resource*
                          (used by ``shock`` and ``conditional`` events).
        rate:             Per-step additive change to *resource*
                          (used by ``trend`` events; applied once per active tick).
        market:           Market resource name to apply a price effect on.
        price_multiplier: Multiplies ``market.current_price`` by this factor.
        price_set:        Sets ``market.current_price`` to an exact value.
        trust_source:     Agent ID that is the *source* of a trust update;
                          all *targets* receive a trust update toward this agent.
        trust_delta:      Trust change applied to each target → trust_source edge.
        contagion_rate:   Fraction of *delta* / *rate* propagated to each
                          trusted neighbour of a target (cascade / contagion).
    """
    targets: Any            # "all" | list[str] | single agent id
    resource: Optional[str] = None
    delta: Optional[float] = None      # one-time resource change (shock / conditional)
    rate: Optional[float] = None       # per-step resource change (trend)
    market: Optional[str] = None
    price_multiplier: Optional[float] = None
    price_set: Optional[float] = None
    trust_source: Optional[str] = None
    trust_delta: Optional[float] = None
    contagion_rate: float = 0.0   # fraction of delta propagated to trusted neighbours


@dataclass
class WorldEventDef:
    """Complete specification for one world event, including runtime tracking state.

    Attributes:
        name:               Unique identifier (used in API event records).
        event_type:         ``shock`` | ``trend`` | ``conditional``.
        effect:             The ``WorldEventEffect`` payload.
        trigger_tick:       Simulation tick at which a tick-based trigger fires;
                            ``None`` for condition-based events.
        duration:           Number of consecutive ticks a ``trend`` stays active
                            (default: 1).
        condition_resource: Resource name checked for conditional triggers.
        condition_operator: Comparison operator: ``lt`` | ``gt`` | ``le`` | ``ge`` | ``eq``.
        condition_threshold:Numeric threshold for the condition.
        condition_scope:    ``any_agent`` (fires if *any* agent meets condition)
                            or ``all_agents`` (all must meet it).
        triggered:          Runtime flag — set ``True`` once the event has fired
                            (prevents re-triggering for shocks / conditionals).
        remaining:          Runtime counter — ticks left for an active trend.
    """
    name: str
    event_type: str                    # shock | trend | conditional
    effect: WorldEventEffect
    trigger_tick: Optional[int] = None
    duration: int = 1                  # active steps (trend)
    condition_resource: Optional[str] = None
    condition_operator: Optional[str] = None  # lt | gt | le | ge | eq
    condition_threshold: Optional[float] = None
    condition_scope: str = "any_agent"   # any_agent | all_agents
    # ---- runtime state (reset on each epoch) ----
    triggered: bool = False            # True once the event has fired at least once
    remaining: int = 0                 # Trend ticks still to execute
