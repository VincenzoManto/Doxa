"""
engine.market — Limit-order-book sub-package.

Contains:
  * ``Order``        — immutable(ish) dataclass representing one resting or
                       market order (bid/ask, quantity, price, TTL, status).
  * ``Market``       — single-instrument state: sorted bid/ask queues,
                       current price, price history, and top-of-book aggregation.
  * ``MarketEngine`` — multi-instrument LOB engine with FIFO price-time
                       matching, call-auction clearing, market-order slippage,
                       order expiry, market-maker quoting, and price impact.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
