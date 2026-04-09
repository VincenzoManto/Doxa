from typing import Dict, List, Optional
from attr import dataclass, field
from RelationRecord import RelationRecord
class RelationGraph:
    """Directional (asymmetric) trust matrix between agents."""

    _NEUTRAL_TRUST = 0.5

    def __init__(self):
        # key: (source, target)
        self._matrix: Dict[tuple, RelationRecord] = {}

    def init_from_yaml(self, relations_cfg: List[Dict], agent_ids: List[str]):
        """Populate from YAML global_rules.relations list, then fill missing pairs."""
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
        rec = self._matrix.get((source, target))
        return rec.trust if rec else self._NEUTRAL_TRUST

    def get_rel_type(self, source: str, target: str) -> str:
        rec = self._matrix.get((source, target))
        return rec.rel_type if rec else "neutral"

    def update_trust(self, source: str, target: str, delta: float):
        key = (source, target)
        if key not in self._matrix:
            self._matrix[key] = RelationRecord(source, target, self._NEUTRAL_TRUST, "neutral")
        rec = self._matrix[key]
        rec.trust = max(0.0, min(1.0, rec.trust + delta))
        # Update rel_type based on trust level
        if rec.trust >= 0.75:
            rec.rel_type = "ally"
        elif rec.trust <= 0.25:
            rec.rel_type = "enemy"
        elif rec.trust <= 0.4:
            rec.rel_type = "rival"
        else:
            rec.rel_type = "neutral"

    def decay_all(self, rate: float):
        """Decay all trust values toward 0.5 by rate."""
        for rec in self._matrix.values():
            if rec.trust > self._NEUTRAL_TRUST:
                rec.trust = max(self._NEUTRAL_TRUST, rec.trust - rate)
            elif rec.trust < self._NEUTRAL_TRUST:
                rec.trust = min(self._NEUTRAL_TRUST, rec.trust + rate)

    def get_relations_for(self, agent_id: str) -> List[RelationRecord]:
        return [r for (src, _tgt), r in self._matrix.items() if src == agent_id]

    def to_list(self) -> List[Dict]:
        return [
            {"source": r.source, "target": r.target, "trust": round(r.trust, 4), "type": r.rel_type}
            for r in self._matrix.values()
        ]

