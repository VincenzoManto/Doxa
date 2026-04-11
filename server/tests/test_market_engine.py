"""
test_market_engine.py
---------------------
Comprehensive unit tests for market.MarketEngine.

Coverage
~~~~~~~~
* Order reservation (bid/ask)         — insufficient-funds rejection
* Continuous (FIFO) clearing          — exact fill, partial fill, price policies
* Cancel + refund
* Expire + refund (TTL)
* Call-auction clearing               — volume-maximising uniform price
* Market orders                       — slippage pricing + immediate clear
* Per-market lock independence        — reads on different markets don't serialise
* Thread-safety stress                — concurrent bids/asks from many threads
"""

import threading
import time
from market.MarketEngine import MarketEngine  # type: ignore[import]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_engine(resources=None, clearing="continuous", extra_cfg=None):
    """Return a MarketEngine with one market per resource name.

    Args:
        resources: list of resource names (default: ["gold"])
        clearing:  "continuous", "on_order", or "call_auction"
        extra_cfg: dict of extra per-market config items (e.g. execution_price_policy)
    """
    resources = resources or ["gold"]
    cfg = {}
    if extra_cfg:
        cfg.update(extra_cfg)
    markets_cfg = [
        {
            "resource": r,
            "currency": "credits",
            "initial_price": 10.0,
            "min_price": 1.0,
            "max_price": 1000.0,
            "clearing": clearing,
            **cfg,
        }
        for r in resources
    ]
    return MarketEngine(markets_cfg)


def _portfolios(specs):
    """Build a shared portfolios dict from a list of (agent_id, dict) pairs."""
    return {agent_id: dict(holdings) for agent_id, holdings in specs}


# ──────────────────────────────────────────────────────────────────────────────
# 1. Order submission — reservation
# ──────────────────────────────────────────────────────────────────────────────

class TestOrderReservation:

    def test_bid_reserves_credits(self):
        engine = _make_engine()
        portfolios = _portfolios([("alice", {"credits": 100, "gold": 0})])

        result = engine.add_order("alice", "bid", "gold", qty := 5, price := 10.0, portfolios)

        assert result.startswith("SUCCESS")
        # reserved = price * qty = 50
        assert portfolios["alice"]["credits"] == pytest_approx(50.0, rel=1e-6)

    def test_ask_reserves_resource(self):
        engine = _make_engine()
        portfolios = _portfolios([("bob", {"credits": 0, "gold": 20})])

        result = engine.add_order("bob", "ask", "gold", 8, 10.0, portfolios)

        assert result.startswith("SUCCESS")
        assert portfolios["bob"]["gold"] == pytest_approx(12.0, rel=1e-6)

    def test_bid_insufficient_credits_rejected(self):
        engine = _make_engine()
        portfolios = _portfolios([("poor", {"credits": 10, "gold": 0})])

        result = engine.add_order("poor", "bid", "gold", 10, 10.0, portfolios)

        assert result.startswith("FAILED")
        assert portfolios["poor"]["credits"] == pytest_approx(10.0)  # no change

    def test_ask_insufficient_resource_rejected(self):
        engine = _make_engine()
        portfolios = _portfolios([("broke", {"credits": 1000, "gold": 2})])

        result = engine.add_order("broke", "ask", "gold", 5, 10.0, portfolios)

        assert result.startswith("FAILED")
        assert portfolios["broke"]["gold"] == pytest_approx(2.0)

    def test_no_market_rejected(self):
        engine = _make_engine(resources=["gold"])
        portfolios = _portfolios([("x", {"credits": 500})])

        result = engine.add_order("x", "bid", "corn", 1, 5.0, portfolios)

        assert result.startswith("FAILED")
        assert "No market" in result

    def test_price_out_of_bounds_rejected(self):
        engine = _make_engine()
        portfolios = _portfolios([("x", {"credits": 50000})])

        result = engine.add_order("x", "bid", "gold", 1, 2000.0, portfolios)

        assert result.startswith("FAILED")
        assert "range" in result.lower()

    def test_invalid_side_rejected(self):
        engine = _make_engine()
        portfolios = _portfolios([("x", {"credits": 100})])

        result = engine.add_order("x", "bork", "gold", 1, 10.0, portfolios)

        assert result.startswith("FAILED")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Continuous (FIFO) clearing
# ──────────────────────────────────────────────────────────────────────────────

class TestContinuousClearing:

    def _setup_cross(self, bid_price=12.0, ask_price=10.0, qty=5):
        """Return (engine, portfolios) with a crossing bid+ask ready to match."""
        engine = _make_engine()
        portfolios = _portfolios([
            ("buyer",  {"credits": 200, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("buyer",  "bid", "gold", qty, bid_price, portfolios)
        engine.add_order("seller", "ask", "gold", qty, ask_price, portfolios)
        return engine, portfolios

    def test_exact_fill(self):
        engine, portfolios = self._setup_cross(bid_price=12.0, ask_price=10.0, qty=5)

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert len(fills) == 1
        f = fills[0]
        assert f["fill_qty"] == pytest_approx(5.0)
        assert f["buyer"] == "buyer"
        assert f["seller"] == "seller"
        # Buyer receives gold
        assert portfolios["buyer"]["gold"] == pytest_approx(5.0)
        # Seller receives credits at fill_price * qty
        fill_price = f["fill_price"]
        assert portfolios["seller"]["credits"] == pytest_approx(fill_price * 5.0)
        # Buyer gets surplus from overpaying back
        expected_surplus = (12.0 - fill_price) * 5.0
        assert portfolios["buyer"]["credits"] == pytest_approx(200 - 12.0 * 5 + expected_surplus)

    def test_partial_fill(self):
        engine = _make_engine()
        portfolios = _portfolios([
            ("buyer",  {"credits": 200, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("buyer",  "bid", "gold", 10, 12.0, portfolios)
        engine.add_order("seller", "ask", "gold",  3, 10.0, portfolios)

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert len(fills) == 1
        assert fills[0]["fill_qty"] == pytest_approx(3.0)
        assert portfolios["buyer"]["gold"] == pytest_approx(3.0)

    def test_no_match_when_bid_below_ask(self):
        engine = _make_engine()
        portfolios = _portfolios([
            ("buyer",  {"credits": 200, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("buyer",  "bid", "gold", 5,  8.0, portfolios)
        engine.add_order("seller", "ask", "gold", 5, 12.0, portfolios)

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert fills == []
        assert portfolios["buyer"]["gold"] == 0  # nothing traded

    def test_price_policy_resting(self):
        engine = _make_engine(extra_cfg={"execution_price_policy": "resting"})
        portfolios = _portfolios([
            ("buyer",  {"credits": 300, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 10}),
        ])
        engine.add_order("seller", "ask", "gold", 5, 10.0, portfolios)  # resting
        engine.add_order("buyer",  "bid", "gold", 5, 15.0, portfolios)  # aggressor

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert len(fills) == 1
        # Resting is the ask (arrived first), so fill_price should be ask price
        assert fills[0]["fill_price"] == pytest_approx(10.0)

    def test_price_policy_midpoint(self):
        engine = _make_engine(extra_cfg={"execution_price_policy": "midpoint"})
        portfolios = _portfolios([
            ("buyer",  {"credits": 300, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 10}),
        ])
        engine.add_order("seller", "ask", "gold", 5, 10.0, portfolios)
        engine.add_order("buyer",  "bid", "gold", 5, 14.0, portfolios)

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert len(fills) == 1
        assert fills[0]["fill_price"] == pytest_approx(12.0)

    def test_price_policy_aggressive(self):
        engine = _make_engine(extra_cfg={"execution_price_policy": "aggressive"})
        portfolios = _portfolios([
            ("buyer",  {"credits": 300, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 10}),
        ])
        engine.add_order("seller", "ask", "gold", 5, 10.0, portfolios)  # resting
        engine.add_order("buyer",  "bid", "gold", 5, 14.0, portfolios)  # aggressor

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert len(fills) == 1
        # Aggressor (bid) sets the price
        assert fills[0]["fill_price"] == pytest_approx(14.0)

    def test_on_order_clearing_fires_immediately(self):
        """With clearing='on_order', submission alone should trigger matching."""
        engine = _make_engine(clearing="on_order")
        portfolios = _portfolios([
            ("buyer",  {"credits": 200, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("seller", "ask", "gold", 5, 10.0, portfolios)

        # Placing the bid with clearing=on_order triggers clear immediately
        engine.add_order("buyer", "bid", "gold", 5, 12.0, portfolios)

        # Gold should be delivered without calling clear_market explicitly
        assert portfolios["buyer"]["gold"] == pytest_approx(5.0)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Cancel + refund
# ──────────────────────────────────────────────────────────────────────────────

class TestCancel:

    def test_cancel_bid_refunds_credits(self):
        engine = _make_engine()
        portfolios = _portfolios([("alice", {"credits": 100, "gold": 0})])
        result = engine.add_order("alice", "bid", "gold", 5, 10.0, portfolios)
        order_id = result.split(":")[1].strip().split(" ")[0]

        engine.cancel_order(order_id, "alice", portfolios)

        # All credits returned
        assert portfolios["alice"]["credits"] == pytest_approx(100.0)

    def test_cancel_ask_refunds_resource(self):
        engine = _make_engine()
        portfolios = _portfolios([("bob", {"credits": 0, "gold": 10})])
        result = engine.add_order("bob", "ask", "gold", 7, 10.0, portfolios)
        order_id = result.split(":")[1].strip().split(" ")[0]

        engine.cancel_order(order_id, "bob", portfolios)

        assert portfolios["bob"]["gold"] == pytest_approx(10.0)

    def test_cancel_wrong_owner_rejected(self):
        engine = _make_engine()
        portfolios = _portfolios([
            ("alice", {"credits": 100, "gold": 0}),
            ("eve",   {"credits": 100, "gold": 0}),
        ])
        result = engine.add_order("alice", "bid", "gold", 5, 10.0, portfolios)
        order_id = result.split(":")[1].strip().split(" ")[0]

        cancel_result = engine.cancel_order(order_id, "eve", portfolios)

        assert cancel_result.startswith("FAILED")

    def test_cancel_filled_order_rejected(self):
        engine = _make_engine(clearing="on_order")
        portfolios = _portfolios([
            ("buyer",  {"credits": 200, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 10}),
        ])
        r1 = engine.add_order("seller", "ask", "gold", 5, 10.0, portfolios)
        r2 = engine.add_order("buyer",  "bid", "gold", 5, 12.0, portfolios)
        ask_id = r1.split(":")[1].strip().split(" ")[0]

        cancel_result = engine.cancel_order(ask_id, "seller", portfolios)

        # Already filled; cancel should fail
        assert cancel_result.startswith("FAILED")


# ──────────────────────────────────────────────────────────────────────────────
# 4. TTL expiry
# ──────────────────────────────────────────────────────────────────────────────

class TestExpiry:

    def _place_limit_with_ttl(self, engine, portfolios, ttl=2):
        """Add a limit order and manually set its TTL for expiry testing."""
        result = engine.add_order("alice", "bid", "gold", 5, 10.0, portfolios, tick=0)
        order_id = result.split(":")[1].strip().split(" ")[0]
        with engine._lock:
            engine._order_index[order_id].ttl = ttl
        return order_id

    def test_order_not_expired_before_ttl(self):
        engine = _make_engine()
        portfolios = _portfolios([("alice", {"credits": 100, "gold": 0})])
        order_id = self._place_limit_with_ttl(engine, portfolios, ttl=3)

        engine.expire_orders(tick=2, portfolios=portfolios)

        # Under TTL: credits still reserved
        assert portfolios["alice"]["credits"] == pytest_approx(50.0)

    def test_order_expired_at_ttl_refunds(self):
        engine = _make_engine()
        portfolios = _portfolios([("alice", {"credits": 100, "gold": 0})])
        order_id = self._place_limit_with_ttl(engine, portfolios, ttl=2)

        engine.expire_orders(tick=2, portfolios=portfolios)

        # TTL reached: credits returned
        assert portfolios["alice"]["credits"] == pytest_approx(100.0)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Call-auction clearing
# ──────────────────────────────────────────────────────────────────────────────

class TestCallAuction:

    def test_call_auction_matches_at_clearing_price(self):
        engine = _make_engine(clearing="call_auction")
        portfolios = _portfolios([
            ("buyer1", {"credits": 500, "gold": 0}),
            ("buyer2", {"credits": 500, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("buyer1", "bid", "gold", 5, 12.0, portfolios)
        engine.add_order("buyer2", "bid", "gold", 5, 11.0, portfolios)
        engine.add_order("seller", "ask", "gold", 8, 10.0, portfolios)

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert len(fills) > 0
        total_qty = sum(f["fill_qty"] for f in fills)
        assert total_qty == pytest_approx(8.0, rel=1e-6)
        # All fills at the same uniform price
        assert all(f["fill_price"] == fills[0]["fill_price"] for f in fills)

    def test_call_auction_no_overlap_no_fill(self):
        engine = _make_engine(clearing="call_auction")
        portfolios = _portfolios([
            ("buyer",  {"credits": 200, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 10}),
        ])
        engine.add_order("buyer",  "bid", "gold", 5,  8.0, portfolios)
        engine.add_order("seller", "ask", "gold", 5, 12.0, portfolios)

        fills = engine.clear_market("gold", portfolios, tick=1)

        assert fills == []


# ──────────────────────────────────────────────────────────────────────────────
# 6. Market orders
# ──────────────────────────────────────────────────────────────────────────────

class TestMarketOrders:

    def test_market_buy_sweeps_liquidity(self):
        engine = _make_engine()
        portfolios = _portfolios([
            ("buyer",  {"credits": 500, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("seller", "ask", "gold", 5, 10.0, portfolios)

        result = engine.add_market_order("buyer", "bid", "gold", 5, portfolios, tick=1)

        assert result.startswith("SUCCESS")
        assert portfolios["buyer"]["gold"] == pytest_approx(5.0)

    def test_market_sell_sweeps_demand(self):
        engine = _make_engine()
        portfolios = _portfolios([
            ("buyer",  {"credits": 500, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 20}),
        ])
        engine.add_order("buyer", "bid", "gold", 5, 10.0, portfolios)

        result = engine.add_market_order("seller", "ask", "gold", 5, portfolios, tick=1)

        assert result.startswith("SUCCESS")
        assert portfolios["seller"]["credits"] > 0


# ──────────────────────────────────────────────────────────────────────────────
# 7. get_price / get_order_book
# ──────────────────────────────────────────────────────────────────────────────

class TestReadPaths:

    def test_get_price_returns_initial_price(self):
        engine = _make_engine()
        assert engine.get_price("gold") == pytest_approx(10.0)

    def test_get_price_updates_after_fill(self):
        engine = _make_engine(clearing="on_order")
        portfolios = _portfolios([
            ("buyer",  {"credits": 300, "gold": 0}),
            ("seller", {"credits": 0,   "gold": 10}),
        ])
        engine.add_order("seller", "ask", "gold", 5, 8.0, portfolios)
        engine.add_order("buyer",  "bid", "gold", 5, 12.0, portfolios)

        p = engine.get_price("gold")
        # fill price is 8.0 (resting ask) by default policy
        assert p == pytest_approx(8.0)

    def test_get_price_unknown_resource_is_none(self):
        engine = _make_engine()
        assert engine.get_price("corn") is None

    def test_get_order_book_structure(self):
        engine = _make_engine()
        portfolios = _portfolios([("alice", {"credits": 200, "gold": 10})])
        engine.add_order("alice", "bid", "gold", 5, 9.0, portfolios)
        engine.add_order("alice", "ask", "gold", 3, 11.0, portfolios)

        book = engine.get_order_book("gold", depth=5)

        assert book is not None
        assert "bids" in book and "asks" in book
        assert book["resource"] == "gold"
        assert len(book["bids"]) > 0
        assert len(book["asks"]) > 0

    def test_get_order_book_unknown_resource_is_none(self):
        engine = _make_engine()
        assert engine.get_order_book("corn") is None

    def test_per_market_lock_reads_different_resources(self):
        """Reads on different markets should not share the same RLock instance."""
        engine = _make_engine(resources=["gold", "corn"])
        assert engine._market_locks["gold"] is not engine._market_locks["corn"]


# ──────────────────────────────────────────────────────────────────────────────
# 8. Thread-safety stress test
# ──────────────────────────────────────────────────────────────────────────────

class TestThreadSafety:

    def test_concurrent_bids_and_asks_no_exception(self):
        """Many threads placing orders simultaneously must not corrupt state."""
        n_agents = 8
        n_orders_each = 10
        engine = _make_engine(clearing="continuous")

        portfolios = {
            f"buyer_{i}":  {"credits": 5000, "gold": 0}
            for i in range(n_agents)
        }
        portfolios.update({
            f"seller_{i}": {"credits": 0, "gold": 5000}
            for i in range(n_agents)
        })

        errors = []

        def place_and_clear(i):
            try:
                for j in range(n_orders_each):
                    price = 10.0 + (i % 3)
                    engine.add_order(f"buyer_{i}",  "bid", "gold", 1, price + 2, portfolios)
                    engine.add_order(f"seller_{i}", "ask", "gold", 1, price,     portfolios)
                    engine.clear_market("gold", portfolios, tick=j)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=place_and_clear, args=(i,)) for i in range(n_agents)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Thread safety violations: {errors}"

    def test_concurrent_price_reads_with_writes(self):
        """Price reads and order writes from separate threads must not raise."""
        engine = _make_engine(clearing="continuous")
        portfolios = {f"a{i}": {"credits": 5000, "gold": 5000} for i in range(4)}
        stop_flag = threading.Event()
        read_errors = []
        write_errors = []

        def writer():
            for k in range(50):
                try:
                    engine.add_order(f"a{k % 4}", "bid", "gold", 1, 10.0, portfolios, tick=k)
                    engine.clear_market("gold", portfolios, tick=k)
                except Exception as e:
                    write_errors.append(e)

        def reader():
            while not stop_flag.is_set():
                try:
                    engine.get_price("gold")
                except Exception as e:
                    read_errors.append(e)
                    stop_flag.set()

        r = threading.Thread(target=reader, daemon=True)
        w = threading.Thread(target=writer)
        r.start()
        w.start()
        w.join(timeout=5)
        stop_flag.set()
        r.join(timeout=1)

        assert read_errors == [], f"Read errors under concurrent writes: {read_errors}"
        assert write_errors == [], f"Write errors: {write_errors}"


# ──────────────────────────────────────────────────────────────────────────────
# Compatibility shim — makes `pytest_approx` available as a bare name
# ──────────────────────────────────────────────────────────────────────────────

try:
    from pytest import approx as pytest_approx  # type: ignore[import]
except ImportError:
    # Fallback for environments where pytest isn't installed yet
    def pytest_approx(value, rel=1e-6, abs=None):  # type: ignore[override]
        return value
