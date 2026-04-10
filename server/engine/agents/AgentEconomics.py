"""
agents.AgentEconomics
---------------------
Encapsulates formal micro-economic preferences for an individual agent.
Parsed from the optional ``actor.economics`` block in the YAML config.
All fields fall back to sensible, risk-neutral defaults so existing
configs that omit the block continue to work without changes.

Supported utility functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``linear``  — utility = total positive wealth (default, risk-neutral).
* ``crra``    — Constant Relative Risk Aversion:
                :math:`U(W) = W^{1-\\gamma} / (1-\\gamma)` (or ln W at \u03b3=1).
* ``cara``    — Constant Absolute Risk Aversion:
                :math:`U(W) = -e^{-\\alpha W} / \\alpha`.
"""
from typing import Dict, List, Optional
from attr import dataclass, field
# ==========================================
# AGENT ECONOMICS — Utility, Risk, Expectations
# ==========================================

@dataclass
class AgentEconomics:
    """Formal economic preferences for one agent, parsed from ``actor.economics`` in YAML.
    All fields are optional; defaults produce neutral / linear behaviour."""
    utility_fn: str = "linear"             # Utility form: "linear" | "crra" | "cara"
    risk_aversion: float = 0.0             # \u03b3 (CRRA) or \u03b1 (CARA); 0 = risk-neutral
    discount_factor: float = 0.95          # Intertemporal patience \u03b2 \u2208 (0, 1]
    liquidity_floor: Dict[str, float] = field(factory=dict)  # Minimum holdings per resource
    price_expectation_window: int = 5      # Rolling window length for EWA price estimate
    learning_rate: float = 0.1             # EWA \u03bb: weight on the newest price observation

    @classmethod
    def from_config(cls, cfg: Optional[Dict]) -> "AgentEconomics":
        if not cfg:
            return cls()
        return cls(
            utility_fn=cfg.get("utility", "linear"),
            risk_aversion=float(cfg.get("risk_aversion", 0.0)),
            discount_factor=float(cfg.get("discount_factor", 0.95)),
            liquidity_floor={k: float(v) for k, v in cfg.get("liquidity_floor", {}).items()},
            price_expectation_window=int(cfg.get("price_expectation_window", 5)),
            learning_rate=float(cfg.get("learning_rate", 0.1)),
        )

    def compute_utility(self, portfolio: Dict[str, float]) -> float:
        """Scalar utility of current portfolio wealth (sum of positive resources)."""
        wealth = sum(max(0.0, v) for v in portfolio.values() if isinstance(v, (int, float)))
        if wealth <= 1e-9:
            return -1e9
        if self.utility_fn == "crra":
            import math
            gamma = max(1e-4, self.risk_aversion)
            if abs(gamma - 1.0) < 1e-6:
                return math.log(wealth)
            return (wealth ** (1.0 - gamma)) / (1.0 - gamma)
        if self.utility_fn == "cara":
            import math
            alpha = max(1e-6, self.risk_aversion)
            return -math.exp(-alpha * wealth) / alpha
        return wealth  # linear

    def risk_label(self) -> str:
        if self.risk_aversion >= 0.7:
            return "CONSERVATIVE"
        if self.risk_aversion >= 0.3:
            return "MODERATE"
        return "AGGRESSIVE"

    def liquidity_advisory(self, portfolio: Dict[str, float]) -> List[str]:
        """Returns list of resources currently below declared liquidity floor."""
        return [
            f"{res} below floor {floor} (have {portfolio.get(res, 0.0):.2f})"
            for res, floor in self.liquidity_floor.items()
            if portfolio.get(res, 0.0) < floor
        ]
