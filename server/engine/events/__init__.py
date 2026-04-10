"""
engine.events — World-event sub-package.

Contains:
  * ``WorldEventEffect``    — dataclass describing *what* an event does
                              (resource delta/rate, market price change,
                               trust delta, contagion).
  * ``WorldEventDef``       — full event definition including trigger,
                              duration, type (shock | trend | conditional)
                              and runtime state (triggered flag, remaining ticks).
  * ``WorldEventScheduler`` — evaluates trigger conditions each tick and
                              applies matching event effects to portfolios,
                              markets, and the relation graph.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
