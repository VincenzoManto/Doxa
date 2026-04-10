"""
relations.RelationRecord
------------------------
Lightweight directed-edge dataclass for the agent-trust graph.
Each ``RelationRecord`` represents a *one-way* view: how much
``source`` trusts ``target``.  A fully bidirectional relationship
requires two records (one in each direction).

The ``rel_type`` label is derived automatically from the ``trust``
value when ``RelationGraph.update_trust()`` modifies the record:

  \u2265 0.75  →  ally
  \u2264 0.25  →  enemy
  \u2264 0.40  →  rival
  else    →  neutral
"""
from attr import dataclass

@dataclass
class RelationRecord:
    """Directed edge in the inter-agent trust graph.

    Attributes:
        source:   ID of the trusting agent.
        target:   ID of the trusted (or distrusted) agent.
        trust:    Float in [0.0, 1.0].  0.5 = perfectly neutral baseline.
        rel_type: Human-readable label: ``ally`` | ``neutral`` | ``rival`` | ``enemy``.
    """
    source: str
    target: str
    trust: float        # 0.0 (enemy) → 1.0 (total trust), default 0.5
    rel_type: str       # ally | neutral | rival | enemy

