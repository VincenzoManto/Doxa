"""
engine.agents — Agent sub-package.

Contains:
  * ``AgentState``     — lightweight dataclass holding a single agent's
                         portfolio, constraints, config, and alive flag.
  * ``AgentEconomics`` — utility-function & risk preferences (CRRA/CARA/linear)
                         parsed from ``actor.economics`` in the YAML config.
  * ``DoxaAgent``      — the AutoGen ``ConversableAgent`` subclass that wraps
                         an LLM (OpenAI / Google / Grok / Ollama) and exposes
                         all game tools (trade, LOB, RAG memory, messaging…).

Path is inserted so that sibling packages (market, relations, utils) are
accessible without a fully-qualified ``engine.`` prefix inside sub-modules.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
