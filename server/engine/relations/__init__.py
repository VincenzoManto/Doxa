"""
engine.relations — Agent-relation / trust-graph sub-package.

Contains:
  * ``RelationRecord`` — dataclass for a single directed trust edge
                         (source → target, float trust in [0,1], rel_type label).
  * ``RelationGraph``  — directional, asymmetric trust matrix; supports
                         bulk initialisation from YAML, per-edge updates,
                         trust decay toward neutral (0.5), and auto
                         reclassification of ally / neutral / rival / enemy.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
