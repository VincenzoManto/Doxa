
# ──────────────────────────────────────────
# MARKET ENGINE — Order book + OTC
# ──────────────────────────────────────────

from attr import dataclass


@dataclass
class Order:
    id: str
    arrival_seq: int
    side: str           # "bid" | "ask"
    agent_id: str
    resource: str
    currency: str
    quantity: float
    price: float        # limit price
    filled: float = 0.0
    status: str = "open"   # open | filled | partial | cancelled
    created_tick: int = 0
    ttl: int = -1            # ticks until expiry; -1 = never
    order_type: str = "limit"   # limit | market

    @property
    def remaining(self) -> float:
        return self.quantity - self.filled

