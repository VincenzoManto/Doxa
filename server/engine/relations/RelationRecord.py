from attr import dataclass

@dataclass
class RelationRecord:
    source: str
    target: str
    trust: float        # 0.0 (enemy) → 1.0 (total trust), default 0.5
    rel_type: str       # ally | neutral | rival | enemy

