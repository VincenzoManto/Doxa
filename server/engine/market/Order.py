"""
market.Order
------------
Represents a single resting (or market) order inside a limit-order book.

Lifecycle
~~~~~~~~~
1. Created by ``MarketEngine.add_order()`` (limit) or
   ``MarketEngine.add_market_order()`` (market, TTL=1 tick).
2. Funds/inventory are *reserved* at creation time so the portfolio
   cannot over-sell or over-spend while the order rests.
3. Status transitions: ``open`` → ``partial`` → ``filled``
                       ``open`` → ``cancelled`` (manual or TTL expiry)
4. Expired orders are cleaned up by ``MarketEngine.expire_orders()``
   at the start of each tick; reserved amounts are refunded.
"""

# ──────────────────────────────────────────
# MARKET ENGINE — Order book + OTC
# ──────────────────────────────────────────

from attr import dataclass


@dataclass
class Order:
    """A single resting or market order inside a ``Market``'s bid/ask queue.

    Attributes:
        id:           Unique string identifier, e.g. ``"ORD_42"``.
        arrival_seq:  Monotonically increasing counter used for FIFO
                      tie-breaking when two orders share the same price.
        side:         ``"bid"`` (buy) or ``"ask"`` (sell).
        agent_id:     ID of the agent who placed this order.
        resource:     Name of the resource being traded (e.g. ``"gold"``).
        currency:     Currency in which price is denominated (e.g. ``"credits"``).
        quantity:     Total quantity requested when the order was placed.
        price:        Limit price (worst acceptable per-unit price).
        filled:       Cumulative quantity already matched and settled.
        status:       ``open`` | ``partial`` | ``filled`` | ``cancelled``.
        created_tick: Simulation tick at which this order was submitted.
        ttl:          Ticks-to-live; ``-1`` means the order never expires.
                      Market orders default to ``ttl=1`` (expire next tick).
        order_type:   ``"limit"`` (default) or ``"market"``.
    """
    id: str
    arrival_seq: int
    side: str           # "bid" (buy) | "ask" (sell)
    agent_id: str
    resource: str
    currency: str
    quantity: float
    price: float        # limit / worst-case price
    filled: float = 0.0
    status: str = "open"   # open | partial | filled | cancelled
    created_tick: int = 0
    ttl: int = -1            # ticks until expiry; -1 = never expires
    order_type: str = "limit"   # limit | market

    @property
    def remaining(self) -> float:
        """Unfilled quantity still resting in the book."""
        return self.quantity - self.filled

