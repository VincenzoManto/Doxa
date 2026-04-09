from typing import Dict, List, Optional
from attr import dataclass, field
from market.Order import Order
@dataclass
class Market:
    resource: str
    currency: str
    current_price: float
    config: Dict = field(factory=dict)
    bids: List[Order] = field(factory=list)    # sorted desc by price
    asks: List[Order] = field(factory=list)    # sorted asc by price
    price_history: List[tuple] = field(factory=list)  # (tick, price)

    def _sort(self):
        self.bids.sort(key=lambda o: (-o.price, o.created_tick, o.arrival_seq))
        self.asks.sort(key=lambda o: (o.price, o.created_tick, o.arrival_seq))

    def best_bid(self) -> Optional[float]:
        for o in self.bids:
            if o.status in ("open", "partial"):
                return o.price
        return None

    def best_ask(self) -> Optional[float]:
        for o in self.asks:
            if o.status in ("open", "partial"):
                return o.price
        return None

    def mid_price(self) -> float:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        return self.current_price

    def top_of_book(self, depth: int = 10) -> Dict:
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
