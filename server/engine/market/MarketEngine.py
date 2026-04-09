from typing import Dict, List, Optional
from attr import dataclass, field
import threading
from market.Order import Order
from relations.RelationRecord import RelationRecord
from agents.AgentState import AgentState
from agents.AgentEconomics import AgentEconomics
from market.Market import Market

class MarketEngine:
    """Manages limit order books for configured markets."""

    def __init__(self, markets_cfg: List[Dict], shared_lock=None):
        self.markets: Dict[str, Market] = {}
        self._order_index: Dict[str, Order] = {}   # order_id → Order
        self._order_counter = 1
        self._lock = shared_lock or threading.RLock()
        for m in (markets_cfg or []):
            resource = m["resource"]
            self.markets[resource] = Market(
                resource=resource,
                currency=m.get("currency", "credits"),
                current_price=float(m.get("initial_price", 1.0)),
                config=m,
            )

    def _next_order_id(self) -> str:
        oid = f"ORD_{self._order_counter}"
        self._order_counter += 1
        return oid

    def _execution_price(self, market: Market, bid: Order, ask: Order) -> float:
        policy = market.config.get("execution_price_policy", "resting")
        if policy == "midpoint":
            return round((bid.price + ask.price) / 2.0, 8)
        if policy == "aggressive":
            aggressor = bid if bid.arrival_seq > ask.arrival_seq else ask
            return float(aggressor.price)
        resting = bid if bid.arrival_seq < ask.arrival_seq else ask
        return float(resting.price)

    def _reserve(self, agent_id: str, reserve_res: str, reserve_qty: float, portfolios: Dict) -> bool:
        port = portfolios.get(agent_id, {})
        if port.get(reserve_res, 0) < reserve_qty:
            return False
        port[reserve_res] = port.get(reserve_res, 0) - reserve_qty
        return True

    def _release(self, agent_id: str, res: str, qty: float, portfolios: Dict):
        port = portfolios.get(agent_id, {})
        port[res] = port.get(res, 0) + qty

    def add_order(self, agent_id: str, side: str, resource: str, quantity: float,
                  price: float, portfolios: Dict, tick: int = 0) -> str:
        with self._lock:
            market = self.markets.get(resource)
            if not market:
                return f"FAILED: No market for resource '{resource}'."
            if quantity <= 0 or price <= 0:
                return "FAILED: quantity and price must be positive."
            cfg = market.config
            min_price = cfg.get("min_price", 0)
            max_price = cfg.get("max_price", float("inf"))
            if not (min_price <= price <= max_price):
                return f"FAILED: price {price} outside allowed range [{min_price}, {max_price}]."
            currency = market.currency
            if side == "bid":
                total_cost = price * quantity
                if not self._reserve(agent_id, currency, total_cost, portfolios):
                    return f"FAILED: Insufficient {currency} to place bid (need {total_cost})."
            elif side == "ask":
                if not self._reserve(agent_id, resource, quantity, portfolios):
                    return f"FAILED: Insufficient {resource} to place ask."
            else:
                return "FAILED: side must be 'bid' or 'ask'."
            order = Order(
                id=self._next_order_id(),
                arrival_seq=self._order_counter - 1,
                side=side,
                agent_id=agent_id,
                resource=resource,
                currency=currency,
                quantity=quantity,
                price=price,
                created_tick=tick,
            )
            self._order_index[order.id] = order
            if side == "bid":
                market.bids.append(order)
            else:
                market.asks.append(order)
            market._sort()
            if cfg.get("clearing") == "on_order":
                self.clear_market(resource, portfolios, tick)
            return f"SUCCESS: {order.id} placed ({side} {quantity}×{resource} @ {price} {currency})."

    def cancel_order(self, order_id: str, agent_id: str, portfolios: Dict) -> str:
        with self._lock:
            order = self._order_index.get(order_id)
            if not order:
                return "FAILED: Order not found."
            if order.agent_id != agent_id:
                return "FAILED: Not your order."
            if order.status not in ("open", "partial"):
                return f"FAILED: Order status is '{order.status}', cannot cancel."
            order.status = "cancelled"
            market = self.markets.get(order.resource)
            if market:
                if order.side == "bid":
                    refund = order.price * order.remaining
                    self._release(agent_id, order.currency, refund, portfolios)
                else:
                    self._release(agent_id, order.resource, order.remaining, portfolios)
            return f"SUCCESS: Order {order_id} cancelled."

    def clear_market(self, resource: str, portfolios: Dict, tick: int) -> List[Dict]:
        """FIFO price-time or call-auction matching. Returns list of fill event dicts."""
        with self._lock:
            market = self.markets.get(resource)
            if not market:
                return []
            if market.config.get("clearing") == "call_auction":
                return self._call_auction_clear(resource, portfolios, tick)
            fills = []
            market._sort()
            impact_factor = float(market.config.get("impact_factor", 0.0))
            active_bids = [o for o in market.bids if o.status in ("open", "partial")]
            active_asks = [o for o in market.asks if o.status in ("open", "partial")]

            bi = ai = 0
            while bi < len(active_bids) and ai < len(active_asks):
                bid = active_bids[bi]
                ask = active_asks[ai]
                if bid.price < ask.price:
                    break
                fill_price = round(self._execution_price(market, bid, ask), 8)
                fill_qty = min(bid.remaining, ask.remaining)
                fill_cost = fill_price * fill_qty

                surplus_currency = max(0.0, (bid.price - fill_price) * fill_qty)
                self._release(bid.agent_id, market.resource, fill_qty, portfolios)
                self._release(ask.agent_id, market.currency, fill_cost, portfolios)
                if surplus_currency > 0:
                    self._release(bid.agent_id, market.currency, surplus_currency, portfolios)

                bid.filled += fill_qty
                ask.filled += fill_qty
                bid.status = "filled" if bid.remaining <= 1e-9 else "partial"
                ask.status = "filled" if ask.remaining <= 1e-9 else "partial"

                market.current_price = fill_price
                # Permanent price impact: large fills push price beyond fill_price
                if impact_factor > 0.0:
                    rem_bids = sum(o.remaining for o in active_bids[bi:] if o.status in ("open", "partial"))
                    rem_asks = sum(o.remaining for o in active_asks[ai:] if o.status in ("open", "partial"))
                    depth = rem_bids + rem_asks
                    frac = fill_qty / (depth + fill_qty) if (depth + fill_qty) > 0 else 0.0
                    direction = 1 if bid.arrival_seq > ask.arrival_seq else -1
                    market.current_price = round(fill_price * (1.0 + frac * impact_factor * direction), 8)
                    cfg = market.config
                    market.current_price = max(
                        float(cfg.get("min_price", 0)),
                        min(float(cfg.get("max_price", float("inf"))), market.current_price),
                    )
                market.price_history.append((tick, market.current_price))
                market.price_history = market.price_history[-2000:]

                fills.append({
                    "resource": resource,
                    "fill_price": fill_price,
                    "fill_qty": fill_qty,
                    "buyer": bid.agent_id,
                    "seller": ask.agent_id,
                    "bid_order": bid.id,
                    "ask_order": ask.id,
                    "tick": tick,
                    "execution_price_policy": market.config.get("execution_price_policy", "resting"),
                })

                if bid.status == "filled":
                    bi += 1
                if ask.status == "filled":
                    ai += 1

            return fills

    def get_price(self, resource: str) -> Optional[float]:
        with self._lock:
            m = self.markets.get(resource)
            return m.current_price if m else None

    def get_order_book(self, resource: str, depth: int = 10) -> Optional[Dict]:
        with self._lock:
            market = self.markets.get(resource)
            if not market:
                return None
            return {**market.top_of_book(depth), "resource": resource, "currency": market.currency}

    def get_open_orders_for(self, agent_id: str, resource: str = None) -> List[Order]:
        with self._lock:
            orders = [o for o in self._order_index.values()
                      if o.agent_id == agent_id and o.status in ("open", "partial")]
            if resource:
                orders = [o for o in orders if o.resource == resource]
            return list(orders)

    # ── New microstructure methods ────────────────────────────────────────────

    def expire_orders(self, tick: int, portfolios: Dict):
        """Cancel all limit/market orders that have exceeded their TTL and refund reserves."""
        with self._lock:
            for order in list(self._order_index.values()):
                if order.status not in ("open", "partial"):
                    continue
                if order.ttl < 0:
                    continue  # no expiry
                if tick - order.created_tick >= order.ttl:
                    order.status = "cancelled"
                    market = self.markets.get(order.resource)
                    if market:
                        if order.side == "bid":
                            self._release(order.agent_id, order.currency,
                                          order.price * order.remaining, portfolios)
                        else:
                            self._release(order.agent_id, order.resource,
                                          order.remaining, portfolios)

    def add_market_order(self, agent_id: str, side: str, resource: str,
                         quantity: float, portfolios: Dict, tick: int = 0) -> str:
        """Place an aggressive market order that sweeps available liquidity.
        Uses current_price ± market_order_slip as worst-case price.
        Order automatically expires the next tick if not fully matched."""
        with self._lock:
            market = self.markets.get(resource)
            if not market:
                return f"FAILED: No market for resource '{resource}'."
            if quantity <= 0:
                return "FAILED: quantity must be positive."
            slip = float(market.config.get("market_order_slip", 0.1))
            cfg = market.config
            if side == "bid":
                worst_price = market.current_price * (1.0 + slip)
                worst_price = min(worst_price, float(cfg.get("max_price", float("inf"))))
            else:
                worst_price = max(1e-8, market.current_price * (1.0 - slip))
                worst_price = max(worst_price, float(cfg.get("min_price", 1e-8)))
        # add_order acquires the lock itself (RLock allows re-entrance)
        result = self.add_order(agent_id, side, resource, quantity, worst_price, portfolios, tick)
        if result.startswith("SUCCESS"):
            order_id = result.split(":")[1].strip().split(" ")[0]
            with self._lock:
                if order_id in self._order_index:
                    self._order_index[order_id].order_type = "market"
                    self._order_index[order_id].ttl = 1   # expire next tick
            # Trigger immediate clearing (RLock re-entrance)
            self.clear_market(resource, portfolios, tick)
        return result

    def _call_auction_clear(self, resource: str, portfolios: Dict, tick: int) -> List[Dict]:
        """Uniform-price call auction: find the price that maximises transacted volume.
        Caller must hold self._lock (RLock re-entrance safe)."""
        market = self.markets.get(resource)
        if not market:
            return []
        active_bids = [o for o in market.bids if o.status in ("open", "partial")]
        active_asks = [o for o in market.asks if o.status in ("open", "partial")]
        if not active_bids or not active_asks:
            return []

        candidate_prices = sorted(
            set(o.price for o in active_bids) | set(o.price for o in active_asks)
        )
        best_price = None
        best_vol = 0.0
        best_imbalance = float("inf")
        for p in candidate_prices:
            demand = sum(o.remaining for o in active_bids if o.price >= p)
            supply = sum(o.remaining for o in active_asks if o.price <= p)
            vol = min(demand, supply)
            imbalance = abs(demand - supply)
            if vol > best_vol or (vol == best_vol and imbalance < best_imbalance):
                best_vol = vol
                best_price = p
                best_imbalance = imbalance

        if best_price is None or best_vol <= 0:
            return []

        eligible_bids = sorted(
            [o for o in active_bids if o.price >= best_price],
            key=lambda o: (-o.price, o.created_tick, o.arrival_seq),
        )
        eligible_asks = sorted(
            [o for o in active_asks if o.price <= best_price],
            key=lambda o: (o.price, o.created_tick, o.arrival_seq),
        )

        fills = []
        bi = ai = 0
        remaining = best_vol
        while bi < len(eligible_bids) and ai < len(eligible_asks) and remaining > 1e-9:
            bid = eligible_bids[bi]
            ask = eligible_asks[ai]
            fill_qty = min(bid.remaining, ask.remaining, remaining)
            fill_cost = best_price * fill_qty
            surplus = (bid.price - best_price) * fill_qty

            self._release(bid.agent_id, market.resource, fill_qty, portfolios)
            self._release(ask.agent_id, market.currency, fill_cost, portfolios)
            if surplus > 0:
                self._release(bid.agent_id, market.currency, surplus, portfolios)

            bid.filled += fill_qty
            ask.filled += fill_qty
            bid.status = "filled" if bid.remaining <= 1e-9 else "partial"
            ask.status = "filled" if ask.remaining <= 1e-9 else "partial"
            remaining -= fill_qty

            fills.append({
                "resource": resource,
                "fill_price": best_price,
                "fill_qty": fill_qty,
                "buyer": bid.agent_id,
                "seller": ask.agent_id,
                "bid_order": bid.id,
                "ask_order": ask.id,
                "tick": tick,
                "execution_price_policy": "call_auction",
            })
            if bid.status == "filled":
                bi += 1
            if ask.status == "filled":
                ai += 1

        if fills:
            market.current_price = best_price
            market.price_history.append((tick, best_price))
            market.price_history = market.price_history[-2000:]
        return fills

    def refresh_market_makers(self, portfolios: Dict, tick: int):
        """Cancel all synthetic MM orders and re-quote around mid-price with inventory skew."""
        for resource, market in self.markets.items():
            mm_cfg = market.config.get("market_maker")
            if not mm_cfg:
                continue
            mm_id = f"__mm_{resource}"
            spread = float(mm_cfg.get("spread", 0.04))
            depth = float(mm_cfg.get("depth", 10))
            inv_limit = float(mm_cfg.get("inventory_limit", 200))
            skew_factor = float(mm_cfg.get("inventory_skew", 0.5))

            # Cancel existing MM orders and refund reserves
            with self._lock:
                for order in list(self._order_index.values()):
                    if order.agent_id == mm_id and order.status in ("open", "partial"):
                        order.status = "cancelled"
                        if order.side == "bid":
                            self._release(mm_id, market.currency,
                                          order.price * order.remaining, portfolios)
                        else:
                            self._release(mm_id, market.resource, order.remaining, portfolios)
                mid = market.mid_price()
                port = portfolios.get(mm_id, {})
                inventory = port.get(resource, 0.0)

            # Inventory skew: long MM lowers ask; short MM raises bid
            inv_ratio = max(-1.0, min(1.0, inventory / inv_limit)) if inv_limit > 0 else 0.0
            skew = inv_ratio * skew_factor * spread
            cfg = market.config
            bid_price = round(mid * (1.0 - spread / 2.0 - skew), 8)
            ask_price = round(mid * (1.0 + spread / 2.0 - skew), 8)
            bid_price = max(float(cfg.get("min_price", 1e-8)), bid_price)
            ask_price = min(float(cfg.get("max_price", float("inf"))), ask_price)
            if bid_price >= ask_price:
                continue  # degenerate spread

            # Ensure MM portfolio has enough to back its orders
            bid_cost = bid_price * depth
            port = portfolios.setdefault(mm_id, {})
            if port.get(market.currency, 0.0) < bid_cost:
                port[market.currency] = bid_cost * 2
            if port.get(resource, 0.0) < depth:
                port[resource] = depth * 2

            self.add_order(mm_id, "bid", resource, depth, bid_price, portfolios, tick)
            self.add_order(mm_id, "ask", resource, depth, ask_price, portfolios, tick)

    def summary(self) -> Dict:
        with self._lock:
            result = {}
            for res, m in self.markets.items():
                active_bids = [o for o in m.bids if o.status in ("open", "partial")]
                active_asks = [o for o in m.asks if o.status in ("open", "partial")]
                result[res] = {
                    "resource": res,
                    "currency": m.currency,
                    "current_price": m.current_price,
                    "mid_price": m.mid_price(),
                    "bids_count": len(active_bids),
                    "asks_count": len(active_asks),
                    "bids_volume": sum(o.remaining for o in active_bids),
                    "asks_volume": sum(o.remaining for o in active_asks),
                    "execution_price_policy": m.config.get("execution_price_policy", "resting"),
                }
            return result
