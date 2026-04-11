"""
conftest.py
-----------
Pytest configuration for the server test suite.

Adds ``server/`` and ``server/engine/`` to ``sys.path`` so that:
  * ``import engine`` works (triggers engine/__init__.py which itself
    inserts ``engine/`` so sub-packages like ``market``, ``agents`` etc.
    can be imported with their short names).
  * Explicit ``from market.MarketEngine import MarketEngine`` style
    imports used inside engine sub-modules also resolve correctly.
"""
import sys
import os

_server_dir = os.path.dirname(os.path.dirname(__file__))   # …/server/
_engine_dir = os.path.join(_server_dir, "engine")          # …/server/engine/

for _p in (_server_dir, _engine_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)
