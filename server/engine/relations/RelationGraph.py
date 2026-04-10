"""
relations.RelationGraph
-----------------------
Directional (asymmetric) trust matrix between simulation agents.

Architecture
~~~~~~~~~~~~
* Internally stored as a dict keyed by ``(source, target)`` string tuples;
  each value is a ``RelationRecord``.
* Pairs not explicitly declared in YAML are lazily treated as neutral (0.5)
  by ``get_trust()`` / ``get_rel_type()`` without allocating a record.
* Trust values are clamped to ``[0, 1]`` on every update.
* The ``rel_type`` label is automatically reclassified after every
  ``update_trust()`` call based on fixed thresholds:

    \u2265 0.75  →  ``ally``
    \u2264 0.25  →  ``enemy``
    \u2264 0.40  →  ``rival``
    else    →  ``neutral``

Thread-safety
~~~~~~~~~~~~~
``RelationGraph`` itself is *not* internally locked; callers that modify it
concurrently must hold the ``SimulationEnvironment._lock`` themselves.
"""
from typing import Dict, List, Optional
from attr import dataclass, field
from RelationRecord import RelationRecord

class RelationGraph:
    """Directional (asymmetric) trust matrix between agents."""

    _NEUTRAL_TRUST = 0.5  # Default trust for any undeclared pair

    def __init__(self):
        # Internal storage: (source_id, target_id) → RelationRecord
        self._matrix: Dict[tuple, RelationRecord] = {}

    def init_from_yaml(self, relations_cfg: List[Dict], agent_ids: List[str]):
        """Populate the graph from ``global_rules.relations`` YAML list.

        Explicitly declared pairs are loaded with their configured trust and
        type.  All other pair combinations remain absent (lazy neutral).

        Args:
            relations_cfg: List of relation dicts, each with keys
                           ``source``, ``target``, ``trust``, ``type``.
            agent_ids:     Full list of active agent IDs (used for validation
                           at the call site; not used directly here).
        """
        self._matrix = {}
        # Load explicit relations
        for r in (relations_cfg or []):
            src = r.get("source", "")
            tgt = r.get("target", "")
            if src and tgt:
                self._matrix[(src, tgt)] = RelationRecord(
                    source=src,
                    target=tgt,
                    trust=float(r.get("trust", self._NEUTRAL_TRUST)),
                    rel_type=r.get("type", "neutral"),
                )
        # Fill symmetric neutral for all other pairs (lazy)

    def get_trust(self, source: str, target: str) -> float:
        """Return the trust level of *source* toward *target* (default: 0.5)."""
        rec = self._matrix.get((source, target))
        return rec.trust if rec else self._NEUTRAL_TRUST

    def get_rel_type(self, source: str, target: str) -> str:
        """Return the relation type label from *source*’s perspective (default: ``neutral``)."""
        rec = self._matrix.get((source, target))
        return rec.rel_type if rec else "neutral"

    def update_trust(self, source: str, target: str, delta: float):
        """Adjust trust of *source* toward *target* by *delta*, clamped to [0, 1].

        Automatically creates a neutral record if the pair does not exist yet,
        then reclassifies ``rel_type`` based on the new trust value.
        """
        key = (source, target)
        if key not in self._matrix:
            self._matrix[key] = RelationRecord(source, target, self._NEUTRAL_TRUST, "neutral")
        rec = self._matrix[key]
        rec.trust = max(0.0, min(1.0, rec.trust + delta))
        # Reclassify label based on updated trust level
        if rec.trust >= 0.75:
            rec.rel_type = "ally"
        elif rec.trust <= 0.25:
            rec.rel_type = "enemy"
        elif rec.trust <= 0.4:
            rec.rel_type = "rival"
        else:
            rec.rel_type = "neutral"

    def decay_all(self, rate: float):
        """Decay all trust values toward 0.5 (neutral) by *rate* per call.

        Values above 0.5 are decreased by *rate* (floored at 0.5).
        Values below 0.5 are increased by *rate* (capped at 0.5).
        """
        for rec in self._matrix.values():
            if rec.trust > self._NEUTRAL_TRUST:
                rec.trust = max(self._NEUTRAL_TRUST, rec.trust - rate)
            elif rec.trust < self._NEUTRAL_TRUST:
                rec.trust = min(self._NEUTRAL_TRUST, rec.trust + rate)

    def get_relations_for(self, agent_id: str) -> List[RelationRecord]:
        """Return all outgoing relation records *from* *agent_id*."""
        return [r for (src, _tgt), r in self._matrix.items() if src == agent_id]

    def to_list(self) -> List[Dict]:
        """Serialise the entire graph to a JSON-safe list of dicts.

        Each entry has keys: ``source``, ``target``, ``trust`` (rounded to 4 dp),
        ``type``.
        """
        return [
            {"source": r.source, "target": r.target, "trust": round(r.trust, 4), "type": r.rel_type}
            for r in self._matrix.values()
        ]

