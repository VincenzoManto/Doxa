from typing import Any, Dict, List, Optional
from market.MarketEngine import MarketEngine

# ==========================================
# MACRO TRACKER — Aggregate economic metrics
# ==========================================

class MacroTracker:
    """Computes and records aggregate economic metrics at each simulation tick."""

    def __init__(self):
        self.history: List[Dict] = []

    def reset(self):
        self.history = []

    def compute(self, portfolios: Dict[str, Dict],
                market_engine: Optional["MarketEngine"], tick: int) -> Dict:
        snap: Dict[str, Any] = {"tick": tick}

        # Per-resource distribution stats (Gini, HHI, totals)
        all_resources: set = set()
        for port in portfolios.values():
            all_resources.update(k for k, v in port.items() if isinstance(v, (int, float)))

        resource_stats: Dict[str, Any] = {}
        for res in sorted(all_resources):
            vals = [max(0.0, p.get(res, 0.0)) for p in portfolios.values()]
            total = sum(vals)
            resource_stats[res] = {
                "total": round(total, 6),
                "mean": round(total / len(vals), 6) if vals else 0.0,
                "gini": round(self._gini(vals), 4),
                "hhi": round(self._hhi(vals), 4),
            }
        snap["resources"] = resource_stats

        # Market price volatility
        market_stats: Dict[str, Any] = {}
        if market_engine:
            for res, m in market_engine.markets.items():
                recent = [p for _, p in m.price_history[-30:]]
                if len(recent) >= 2:
                    mean_p = sum(recent) / len(recent)
                    std = (sum((p - mean_p) ** 2 for p in recent) / len(recent)) ** 0.5
                else:
                    std = 0.0
                market_stats[res] = {
                    "last_price": m.current_price,
                    "volatility": round(std, 6),
                    "min_recent": round(min(recent), 6) if recent else m.current_price,
                    "max_recent": round(max(recent), 6) if recent else m.current_price,
                }
        snap["market_stats"] = market_stats

        # System-wide panic average
        panic_vals = [
            p.get("panic", 0.0)
            for p in portfolios.values()
            if "panic" in p and isinstance(p["panic"], (int, float))
        ]
        snap["system_panic"] = round(sum(panic_vals) / len(panic_vals), 4) if panic_vals else 0.0

        self.history.append(snap)
        self.history = self.history[-500:]
        return snap

    def latest(self) -> Optional[Dict]:
        return self.history[-1] if self.history else None

    @staticmethod
    def _gini(values: List[float]) -> float:
        """Gini coefficient in [0, 1]. 0 = perfect equality."""
        xs = sorted(values)
        n = len(xs)
        if n == 0 or sum(xs) == 0:
            return 0.0
        total = sum(xs)
        gini_sum = sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs))
        return gini_sum / (n * total)

    @staticmethod
    def _hhi(values: List[float]) -> float:
        """Herfindahl-Hirschman Index in [0, 1]. 1 = monopoly."""
        total = sum(values)
        if total == 0:
            return 0.0
        return sum((v / total) ** 2 for v in values)
