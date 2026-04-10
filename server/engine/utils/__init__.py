"""
engine.utils — Utility sub-package.

Contains:
  * ``ConsoleLogger`` — ANSI-coloured terminal printer used by the engine
                        to display epochs, steps, agent turns, trades,
                        market fills, victories, and resource deltas.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
