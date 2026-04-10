"""
MacroTracker
------------
Computes and records aggregate economic metrics at every simulation tick.

Metrics captured
~~~~~~~~~~~~~~~~
* **Per-resource distribution** \u2014 total, mean, Gini coefficient, and
  Herfindahl-Hirschman Index (HHI) across all agent portfolios.
* **Market price volatility** \u2014 rolling standard deviation over the last
  30 price-history entries for each configured market.
* **System panic** \u2014 mean ``panic`` resource value across all agents
  (a proxy for collective distress).

History is capped at the 500 most recent snapshots to bound memory use.
"""
from typing import Any, Dict, List, Optional
from market.MarketEngine import MarketEngine

# ==========================================
# MACRO TRACKER — Aggregate economic metrics
# ==========================================

class MacroTracker:
    """Computes and records aggregate economic metrics at each simulation tick.

    Lifetime usage:
        1. ``reset()`` is called at the start of every epoch.
        2. ``compute(portfolios, market_engine, tick)`` is called once per step,
           after agent turns and market clearing.
        3. ``latest()`` / ``history`` are exposed via the API.
    """

    def __init__(self):
        self.history: List[Dict] = []  # Rolling list of per-tick snapshots (max 500)

    def reset(self):
        """Clear history at the start of a new epoch."""
        self.history = []

    def compute(self, portfolios: Dict[str, Dict],
                market_engine: Optional["MarketEngine"], tick: int) -> Dict:
        """Compute a macro snapshot for *tick* and append it to ``history``.

        Args:
            portfolios:    Current ``{agent_id: {resource: qty}}`` mapping.
            market_engine: Live ``MarketEngine`` instance, or ``None`` if LOB is
                           not configured.
            tick:          Current simulation tick index.

        Returns:
            The newly computed snapshot dict with keys ``tick``, ``resources``,
            ``market_stats``, and ``system_panic``.
        """
        snap: Dict[str, Any] = {"tick": tick}

        # ── 1. Per-resource distribution statistics ──────────────────────────
        # Collect the set of all resource names present across any portfolio.
        all_resources: set = set()
        for port in portfolios.values():
            all_resources.update(k for k, v in port.items() if isinstance(v, (int, float)))

        resource_stats: Dict[str, Any] = {}
        for res in sorted(all_resources):
            # Clamp to 0 so negative-balance edge cases don’t distort Gini/HHI.
            vals = [max(0.0, p.get(res, 0.0)) for p in portfolios.values()]
            total = sum(vals)
            resource_stats[res] = {
                "total": round(total, 6),
                "mean": round(total / len(vals), 6) if vals else 0.0,
                "gini": round(self._gini(vals), 4),   # 0=equal, 1=monopoly
                "hhi": round(self._hhi(vals), 4),     # 0=dispersed, 1=monopoly
            }
        snap["resources"] = resource_stats

        # ── 2. Market price volatility ────────────────────────────────────────
        market_stats: Dict[str, Any] = {}
        if market_engine:
            for res, m in market_engine.markets.items():
                # Use last 30 price ticks for a short-run volatility estimate.
                recent = [p for _, p in m.price_history[-30:]]
                if len(recent) >= 2:
                    mean_p = sum(recent) / len(recent)
                    # Population standard deviation (not sample, since we have
                    # the full recent window, not a sample from a larger series).
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

        # ── 3. System-wide panic (mean across agents that hold a panic resource) ──
        panic_vals = [
            p.get("panic", 0.0)
            for p in portfolios.values()
            if "panic" in p and isinstance(p["panic"], (int, float))
        ]
        snap["system_panic"] = round(sum(panic_vals) / len(panic_vals), 4) if panic_vals else 0.0

        # Cap history to the last 500 snapshots to bound memory growth.
        self.history.append(snap)
        self.history = self.history[-500:]
        return snap

    def latest(self) -> Optional[Dict]:
        """Return the most recent snapshot, or ``None`` if history is empty."""
        return self.history[-1] if self.history else None

    @staticmethod
    def _gini(values: List[float]) -> float:
        """Gini coefficient in [0, 1].  0 = perfect equality, 1 = one agent holds everything.

        Uses the standard sorted-array formula:
        G = \u03a3 (2i - n - 1) * x_i  /  (n * \u03a3 x_i)
        where the x_i are sorted in ascending order and i is 1-based.
        """
        xs = sorted(values)
        n = len(xs)
        if n == 0 or sum(xs) == 0:
            return 0.0
        total = sum(xs)
        gini_sum = sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs))
        return gini_sum / (n * total)

    @staticmethod
    def _hhi(values: List[float]) -> float:
        """Herfindahl-Hirschman Index in [0, 1].  1 = complete monopoly.

        Computed as the sum of squared market-share fractions:
        HHI = \u03a3 (v_i / total)\u00b2
        """
        total = sum(values)
        if total == 0:
            return 0.0
        return sum((v / total) ** 2 for v in values)
