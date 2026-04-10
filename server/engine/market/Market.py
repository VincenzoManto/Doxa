"""
market.Market
-------------
Holds the full state of a single tradable instrument inside the LOB.
Each ``Market`` instance is owned exclusively by ``MarketEngine`` and
should not be mutated from outside that class.

Data layout
~~~~~~~~~~~
* ``bids``  — buy-side orders, sorted *descending* by price then
              ascending by (created_tick, arrival_seq) for FIFO.
* ``asks``  — sell-side orders, sorted *ascending* by price then
              ascending by (created_tick, arrival_seq).
* ``price_history`` — list of ``(tick, price)`` tuples capped at 2 000
              entries; used by ``MacroTracker`` for volatility stats and
              by the API for the price-history chart.
"""
from typing import Dict, List, Optional
from attr import dataclass, field
from market.Order import Order

@dataclass
class Market:
    """Single-instrument limit-order book state.

    Attributes:
        resource:      Name of the resource being traded (e.g. ``"gold"``).
        currency:      Currency denomination (e.g. ``"credits"``).
        current_price: Last-fill price; used as reference for market orders
                       and the ``price \u00d7 multiplier`` world-event effect.
        config:        Raw YAML market config dict (price bounds, clearing mode,
                       market_maker settings, etc.).
        bids:          Active buy orders sorted desc by price (best bid first).
        asks:          Active sell orders sorted asc by price (best ask first).
        price_history: Rolling list of ``(tick, price)`` fill records.
    """
    resource: str
    currency: str
    current_price: float
    config: Dict = field(factory=dict)
    bids: List[Order] = field(factory=list)    # sorted descending by price
    asks: List[Order] = field(factory=list)    # sorted ascending by price
    price_history: List[tuple] = field(factory=list)  # (tick, price)

    def _sort(self):
        """Re-sort both sides after inserting a new order.

        Tie-breaking follows FIFO price-time priority:
        bids → (price DESC, created_tick ASC, arrival_seq ASC)
        asks → (price ASC,  created_tick ASC, arrival_seq ASC)
        """
        self.bids.sort(key=lambda o: (-o.price, o.created_tick, o.arrival_seq))
        self.asks.sort(key=lambda o: (o.price, o.created_tick, o.arrival_seq))

    def best_bid(self) -> Optional[float]:
        """Return the highest resting bid price, or ``None`` if the book is empty."""
        for o in self.bids:
            if o.status in ("open", "partial"):
                return o.price
        return None

    def best_ask(self) -> Optional[float]:
        """Return the lowest resting ask price, or ``None`` if the book is empty."""
        for o in self.asks:
            if o.status in ("open", "partial"):
                return o.price
        return None

    def mid_price(self) -> float:
        """Return (best_bid + best_ask) / 2, or ``current_price`` if one side is empty."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        return self.current_price

    def top_of_book(self, depth: int = 10) -> Dict:
        """Return aggregated bid/ask ladders up to *depth* price levels.

        Orders at the same price are merged into a single quantity entry.

        Returns::

            {
                "bids": [{"price": float, "qty": float}, ...],  # up to depth levels
                "asks": [{"price": float, "qty": float}, ...],
                "mid_price": float,
                "last_price": float,   # last fill price (current_price)
            }
        """
        bids_agg: Dict[float, float] = {}
        for o in self.bids:
            if o.status in ("open", "partial"):
                bids_agg[o.price] = bids_agg.get(o.price, 0) + o.remaining
        asks_agg: Dict[float, float] = {}
        for o in self.asks:
            if o.status in ("open", "partial"):
                asks_agg[o.price] = asks_agg.get(o.price, 0) + o.remaining
        sorted_bids = sorted(bids_agg.items(), key=lambda x: -x[0])[:depth]
        sorted_asks = sorted(asks_agg.items(), key=lambda x: x[0])[:depth]
        return {
            "bids": [{"price": p, "qty": q} for p, q in sorted_bids],
            "asks": [{"price": p, "qty": q} for p, q in sorted_asks],
            "mid_price": self.mid_price(),
            "last_price": self.current_price,
        }
