"""
engine — Doxa Simulation Engine root package.

Adds the engine directory to ``sys.path`` so that sub-modules
(agents, events, market, relations, utils) can be imported with
simple top-level names, e.g. ``from market.MarketEngine import MarketEngine``.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
