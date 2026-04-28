"""
DoxaEngine
----------
Top-level orchestrator for a Doxa multi-agent economic simulation.

Lifecycle
~~~~~~~~~
1. **Construction** \u2014 ``DoxaEngine(yaml_str)`` parses and validates the YAML
   config, creates a ``SimulationEnvironment``, and attaches a
   ``DoxaChatbot``.
2. **Start** \u2014 ``start_run()`` launches a background ``threading.Thread``
   that calls ``run()``.
3. **Run loop** \u2014 ``run()`` iterates epochs \u00d7 steps:
   a. ``env.reset()`` re-initialises agents / portfolios for each epoch.
   b. Per step: maintenance \u2192 agent turns \u2192 market clearing \u2192 world
      events \u2192 price-expectation update \u2192 macro snapshot.
4. **Control** \u2014 ``pause_run()`` / ``resume_run()`` / ``restart_run()`` /
   ``stop_current_run()`` manage the run-thread lifecycle.
5. **Manual stepping** \u2014 ``step_once()`` advances one agent turn while
   paused (used by the frontend *step* button).

Key internal methods
~~~~~~~~~~~~~~~~~~~~
* ``_step_agent(a_id)``          \u2014 generates one LLM reply and dispatches
                                   tool-calls or custom operations.
* ``_run_market_clearing()``     \u2014 expires stale orders, re-quotes market
                                   makers, then runs per_step / call_auction
                                   matching for all markets.
* ``_run_world_events()``        \u2014 ticks ``WorldEventScheduler`` and records
                                   any fired events.
* ``_update_price_expectations`` \u2014 runs EWA update for all agents / markets.
* ``_run_macro_step()``          \u2014 records a ``MacroTracker`` snapshot.
* ``_apply_maintenance()``       \u2014 deducts per-step maintenance costs and
                                   checks kill conditions.
* ``check_victory_conditions()`` \u2014 checks victory conditions per agent.

Data export
~~~~~~~~~~~
* ``export_data(query, format)`` \u2014 flexible data extractor supporting
  agents, portfolios, trades, markets, relations, and history.
* ``build_export_zip()``         \u2014 produces a ZIP archive with config,
  events, timeline, and per-agent CSV files.

Config management
~~~~~~~~~~~~~~~~~
* ``_set_config(yaml_text)`` / ``update_config_text()`` / ``load_config_path()``
  handle runtime YAML updates with full validation.
* ``_validate_config_dict()`` is the comprehensive structural\u00a0validator;
  it checks all constraint blocks, operation dicts, market bounds, event
  definitions, and relation references before any state is mutated.
"""
import yaml
import json
import random
import csv
import io
import threading
import time
import uuid
import zipfile
from copy import deepcopy
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from engine.DoxaChatbot import DoxaChatbot
from engine.SimulationEnvironment import SimulationEnvironment

class DoxaEngine:
    """Top-level simulation orchestrator.  One instance manages one YAML config."""

    def __init__(self, yaml_str, log_verbose=True, rag_limit=200, logger=None):
        """Initialise the engine from a raw YAML string.

        Parses and validates *yaml_str*, builds the ``SimulationEnvironment``,
        and attaches a ``DoxaChatbot``.  If any actor declares
        ``provider: ollama``, a background thread is started to warm up the
        local Ollama server.

        Args:
            yaml_str:    YAML configuration string (the full simulation spec).
            log_verbose: Enable ANSI-coloured console output.
            rag_limit:   Maximum RAG memory entries per agent before eviction.
            logger:      Optional pre-built logger; overrides *log_verbose*.
        """
        self.log_verbose = log_verbose
        self.rag_limit = rag_limit
        self.logger = logger
        self._state_lock = threading.RLock()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event = threading.Event()
        self._run_thread = None
        self.state = "idle"
        self.last_error = None
        self.current_epoch = 0
        self.current_step = 0
        self.run_sequence = 0
        self.run_id = None
        self.event_history = []
        self.resource_history = []
        self._manual_agent_index = 0
        self.config_source = {"kind": "embedded", "value": "config_yaml"}
        self.config_text = ""
        self._set_config(yaml_str, source_kind="embedded", source_value="config_yaml")
        self.chatbot = DoxaChatbot(self)

    def _expanded_agent_ids_from_config(self, config: dict) -> List[str]:
        expanded_ids = []
        for actor in config.get("actors", []):
            replicas = actor.get("replicas", 1)
            actor_id = actor.get("id")
            if not actor_id:
                continue
            if replicas > 1:
                expanded_ids.extend([f"{actor_id}_{index + 1}" for index in range(replicas)])
            expanded_ids.append(actor_id)
        return expanded_ids

    def _collect_declared_resources(self, config: dict) -> set:
        resources = set()
        global_rules = config.get("global_rules", {})
        for resource in global_rules.get("constraints", {}).keys():
            resources.add(resource)
        for operation in global_rules.get("operations", {}).values():
            resources.update(operation.get("input", {}).keys())
            resources.update(operation.get("output", {}).keys())
            resources.update(operation.get("target_impact", {}).keys())
        for actor in config.get("actors", []):
            resources.update(actor.get("initial_portfolio", {}).keys())
            resources.update(actor.get("constraints", {}).keys())
            for operation in actor.get("operations", {}).values():
                resources.update(operation.get("input", {}).keys())
                resources.update(operation.get("output", {}).keys())
                resources.update(operation.get("target_impact", {}).keys())
        return resources

    def _validate_constraint_block(self, block: dict, context: str):
        if not isinstance(block, dict):
            raise ValueError(f"{context} must be a mapping.")
        for resource_name, bounds in block.items():
            if not isinstance(bounds, dict):
                raise ValueError(f"{context}.{resource_name} must be a mapping.")
            min_value = bounds.get("min", float("-inf"))
            max_value = bounds.get("max", float("inf"))
            if not isinstance(min_value, (int, float)) or not isinstance(max_value, (int, float)):
                raise ValueError(f"{context}.{resource_name} min/max must be numeric.")
            if min_value > max_value:
                raise ValueError(f"{context}.{resource_name} has inconsistent bounds: min > max.")

    def _validate_operation_block(self, block: dict, context: str):
        if not isinstance(block, dict):
            raise ValueError(f"{context} must be a mapping.")
        for op_name, op_def in block.items():
            if not isinstance(op_def, dict):
                raise ValueError(f"{context}.{op_name} must be a mapping.")
            # Allow optional success_probability field
            if "success_probability" in op_def:
                prob = op_def["success_probability"]
                if not isinstance(prob, (int, float)):
                    raise ValueError(f"{context}.{op_name}.success_probability must be numeric.")
                if not (0.0 <= float(prob) <= 1.0):
                    raise ValueError(f"{context}.{op_name}.success_probability must be between 0 and 1.")
            for key in ("input", "output", "target_impact"):
                resource_map = op_def.get(key, {})
                if resource_map is None:
                    continue
                if not isinstance(resource_map, dict):
                    raise ValueError(f"{context}.{op_name}.{key} must be a mapping.")
                for resource_name, amount in resource_map.items():
                    if not isinstance(amount, (int, float)):
                        raise ValueError(f"{context}.{op_name}.{key}.{resource_name} must be numeric.")

    def _validate_condition_block(
        self,
        condition: dict,
        known_resources: set,
        context: str,
        *,
        require_operator: bool = True,
        default_operator: Optional[str] = None,
    ):
        if not isinstance(condition, dict):
            raise ValueError(f"{context} condition must be a mapping.")
        resource_name = condition.get("resource")
        operator = condition.get("operator", default_operator)
        threshold = condition.get("threshold")
        if resource_name not in known_resources:
            raise ValueError(f"{context} references unknown resource '{resource_name}'.")
        if require_operator and operator not in {"lt", "gt", "le", "ge", "eq"}:
            raise ValueError(f"{context} has unsupported operator '{operator}'.")
        if not isinstance(threshold, (int, float)):
            raise ValueError(f"{context} threshold must be numeric.")

    def _resource_can_grow(self, config: dict, resource_name: str) -> bool:
        global_rules = config.get("global_rules", {})
        for operation in global_rules.get("operations", {}).values():
            if operation.get("output", {}).get(resource_name, 0) > 0:
                return True
        for actor in config.get("actors", []):
            for operation in actor.get("operations", {}).values():
                if operation.get("output", {}).get(resource_name, 0) > 0:
                    return True
        for event in config.get("world_events", []):
            effect = event.get("effect", {})
            if effect.get("resource") == resource_name and ((effect.get("delta") or 0) > 0 or (effect.get("rate") or 0) > 0):
                return True
        return False

    def _validate_config_dict(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError("YAML root must be a mapping.")
        if "actors" not in config or not isinstance(config["actors"], list) or not config["actors"]:
            raise ValueError("Config must define a non-empty 'actors' list.")
        if "global_rules" not in config or not isinstance(config["global_rules"], dict):
            raise ValueError("Config must define 'global_rules' as a mapping.")
        global_rules = config["global_rules"]
        known_agent_ids = set(self._expanded_agent_ids_from_config(config))
        actor_base_ids = set()
        for actor in config["actors"]:
            if not isinstance(actor, dict):
                raise ValueError("Each actor must be a mapping.")
            if not actor.get("id"):
                raise ValueError("Each actor must define an 'id'.")
            if "initial_portfolio" not in actor or not isinstance(actor["initial_portfolio"], dict):
                raise ValueError(f"Actor '{actor.get('id', '<unknown>')}' must define 'initial_portfolio'.")
            if actor["id"] in actor_base_ids:
                raise ValueError(f"Duplicate actor id '{actor['id']}'.")
            actor_base_ids.add(actor["id"])
            if actor.get("trading_mode", "otc") not in {"otc", "lob", "both"}:
                raise ValueError(f"Actor '{actor['id']}' has invalid trading_mode '{actor.get('trading_mode')}'.")
            temperature = actor.get("temperature")
            if temperature is not None:
                if not isinstance(temperature, (int, float)) or not (0 <= float(temperature) <= 2):
                    raise ValueError(f"Actor '{actor['id']}'.temperature must be numeric and in [0, 2].")
            irrationality = actor.get("irrationality")
            if irrationality is not None:
                if not isinstance(irrationality, (int, float)) or not (0 <= float(irrationality) <= 1):
                    raise ValueError(f"Actor '{actor['id']}'.irrationality must be numeric and in [0, 1].")
            econ_cfg = actor.get("economics")
            if econ_cfg is not None:
                if not isinstance(econ_cfg, dict):
                    raise ValueError(f"Actor '{actor['id']}'.economics must be a mapping.")
                if econ_cfg.get("utility", "linear") not in {"linear", "crra", "cara"}:
                    raise ValueError(f"Actor '{actor['id']}'.economics.utility must be linear | crra | cara.")
                _ra = econ_cfg.get("risk_aversion", 0.0)
                if not isinstance(_ra, (int, float)) or _ra < 0:
                    raise ValueError(f"Actor '{actor['id']}'.economics.risk_aversion must be >= 0.")
                _df = econ_cfg.get("discount_factor", 0.95)
                if not isinstance(_df, (int, float)) or not (0 < _df <= 1):
                    raise ValueError(f"Actor '{actor['id']}'.economics.discount_factor must be in (0, 1].")
            self._validate_constraint_block(actor.get("constraints", {}), f"actors.{actor['id']}.constraints")
            self._validate_operation_block(actor.get("operations", {}), f"actors.{actor['id']}.operations")

        known_resources = self._collect_declared_resources(config)
        self._validate_constraint_block(global_rules.get("constraints", {}), "global_rules.constraints")
        self._validate_operation_block(global_rules.get("operations", {}), "global_rules.operations")

        for condition in global_rules.get("kill_conditions", []):
            self._validate_condition_block(
                condition,
                known_resources,
                "global_rules.kill_conditions",
                require_operator=False,
                default_operator="le",
            )
        for condition in global_rules.get("victory_conditions", []):
            self._validate_condition_block(
                condition,
                known_resources,
                "global_rules.victory_conditions",
                require_operator=False,
                default_operator="ge",
            )

        for relation in global_rules.get("relations", []):
            if not isinstance(relation, dict):
                raise ValueError("global_rules.relations entries must be mappings.")
            if relation.get("source") not in known_agent_ids or relation.get("target") not in known_agent_ids:
                raise ValueError(f"Relation references unknown agent(s): {relation}")
            trust = relation.get("trust", 0.5)
            if not isinstance(trust, (int, float)) or trust < 0 or trust > 1:
                raise ValueError(f"Relation trust must be in [0, 1]: {relation}")

        seen_markets = set()
        for market in global_rules.get("markets", []):
            if not isinstance(market, dict):
                raise ValueError("global_rules.markets entries must be mappings.")
            resource_name = market.get("resource")
            currency_name = market.get("currency")
            if not resource_name or not currency_name:
                raise ValueError(f"Market must define resource and currency: {market}")
            if resource_name in seen_markets:
                raise ValueError(f"Duplicate market resource '{resource_name}'.")
            seen_markets.add(resource_name)
            if resource_name not in known_resources or currency_name not in known_resources:
                raise ValueError(f"Market '{resource_name}/{currency_name}' references undeclared resources.")
            initial_price = market.get("initial_price", 1.0)
            min_price = market.get("min_price", 0)
            max_price = market.get("max_price", float("inf"))
            if not all(isinstance(value, (int, float)) for value in (initial_price, min_price, max_price)):
                raise ValueError(f"Market '{resource_name}' price bounds must be numeric.")
            if min_price > max_price or not (min_price <= initial_price <= max_price):
                raise ValueError(f"Market '{resource_name}' has inconsistent price bounds.")
            if market.get("clearing", "per_step") not in {"per_step", "on_order", "call_auction"}:
                raise ValueError(f"Market '{resource_name}' has invalid clearing mode '{market.get('clearing')}'.")
            if market.get("execution_price_policy", "resting") not in {"resting", "midpoint", "aggressive"}:
                raise ValueError(f"Market '{resource_name}' has invalid execution_price_policy '{market.get('execution_price_policy')}'.")
            for _nk in ("impact_factor", "market_order_slip"):
                _v = market.get(_nk)
                if _v is not None and (not isinstance(_v, (int, float)) or float(_v) < 0):
                    raise ValueError(f"Market '{resource_name}'.{_nk} must be a non-negative number.")
            mm_cfg = market.get("market_maker")
            if mm_cfg is not None:
                if not isinstance(mm_cfg, dict):
                    raise ValueError(f"Market '{resource_name}'.market_maker must be a mapping.")
                for _mk in ("spread", "depth", "inventory_limit", "inventory_skew"):
                    _v = mm_cfg.get(_mk)
                    if _v is not None and (not isinstance(_v, (int, float)) or float(_v) < 0):
                        raise ValueError(f"Market '{resource_name}'.market_maker.{_mk} must be a non-negative number.")

        for event in config.get("world_events", []):
            if not isinstance(event, dict) or not event.get("name"):
                raise ValueError("world_events entries must be mappings with a name.")
            event_type = event.get("type", "shock")
            if event_type not in {"shock", "trend", "conditional"}:
                raise ValueError(f"World event '{event.get('name')}' has unsupported type '{event_type}'.")
            if event_type == "trend" and (not isinstance(event.get("duration", 1), int) or event.get("duration", 1) <= 0):
                raise ValueError(f"World event '{event.get('name')}' must have duration > 0.")
            trigger = event.get("trigger", {})
            if "condition" in trigger:
                self._validate_condition_block(trigger["condition"], known_resources, f"world_events.{event['name']}")
            effect = event.get("effect", {})
            targets = effect.get("targets", "all")
            if isinstance(targets, list) and any(target not in known_agent_ids for target in targets):
                raise ValueError(f"World event '{event['name']}' targets unknown agent(s): {targets}")
            if isinstance(targets, str) and targets != "all" and targets not in known_agent_ids:
                raise ValueError(f"World event '{event['name']}' targets unknown agent '{targets}'.")
            if effect.get("resource") and effect["resource"] not in known_resources:
                raise ValueError(f"World event '{event['name']}' references unknown resource '{effect['resource']}'.")
            if effect.get("market") and effect["market"] not in seen_markets:
                raise ValueError(f"World event '{event['name']}' references unknown market '{effect['market']}'.")
            if effect.get("trust_source") and effect["trust_source"] not in known_agent_ids:
                raise ValueError(f"World event '{event['name']}' references unknown trust_source '{effect['trust_source']}'.")

        initial_totals = {}
        initial_individual_max = {}
        for actor in config["actors"]:
            replicas = actor.get("replicas", 1)
            for resource_name, amount in actor["initial_portfolio"].items():
                initial_totals[resource_name] = initial_totals.get(resource_name, 0) + (amount * replicas)
                initial_individual_max[resource_name] = max(initial_individual_max.get(resource_name, float("-inf")), amount)
        all_victory_conditions = list(global_rules.get("victory_conditions", []))
        for actor in config["actors"]:
            all_victory_conditions.extend(actor.get("victory_conditions", []))
        for condition in all_victory_conditions:
            resource_name = condition.get("resource")
            threshold = condition.get("threshold")
            scope = condition.get("scope", "global")
            if not isinstance(threshold, (int, float)):
                raise ValueError(f"Victory condition threshold must be numeric: {condition}")
            if resource_name not in known_resources:
                raise ValueError(f"Victory condition references unknown resource '{resource_name}'.")
            if not self._resource_can_grow(config, resource_name):
                if scope == "individual" and initial_individual_max.get(resource_name, float("-inf")) < threshold:
                    raise ValueError(f"Victory condition is infeasible without a producer for '{resource_name}': {condition}")
                if scope != "individual" and initial_totals.get(resource_name, 0) < threshold:
                    raise ValueError(f"Victory condition is infeasible without a producer for '{resource_name}': {condition}")

    def _set_config(self, yaml_text: str, source_kind: str = "text", source_value: str = "runtime"):
        parsed = yaml.safe_load(yaml_text) or {}
        self._validate_config_dict(parsed)
        self.raw_config = parsed
        self.global_rules = self.raw_config.get("global_rules", {})
        self.config_text = yaml_text.strip() + "\n"
        self.config_source = {"kind": source_kind, "value": source_value}
        self.env = SimulationEnvironment(self.raw_config, log_verbose=self.log_verbose, rag_limit=self.rag_limit, logger=self.logger)
        self.log = self.env.log
        uses_ollama = any(actor.get("provider", "ollama").lower() == "ollama" for actor in self.raw_config.get("actors", []))
        if uses_ollama:
            self.startOllama()

    def validate_yaml(self, yaml_text: str):
        """Parse and validate *yaml_text* without changing engine state.

        Returns:
            ``{"valid": True, "config": parsed_dict}`` on success.

        Raises:
            ``ValueError`` with a descriptive message on the first detected
            structural or semantic error.
        """
        parsed = yaml.safe_load(yaml_text) or {}
        self._validate_config_dict(parsed)
        return {"valid": True, "config": parsed}

    def get_config(self):
        return {
            "yaml_text": self.config_text,
            "source": self.config_source,
            "config": self.raw_config,
        }

    def update_config_text(self, yaml_text: str):
        with self._state_lock:
            if self.state in {"running", "paused"}:
                raise RuntimeError("Stop or reset the simulation before changing the config.")
            self._set_config(yaml_text, source_kind="text", source_value="api")
            self._reset_runtime_storage()
            self.env.reset(self.raw_config["actors"])
            self.record_event({"type": "config_updated", "text": "Runtime YAML updated"})
            self.record_snapshot("config_updated")
            return self.get_config()

    def load_config_path(self, path: str):
        with open(path, "r", encoding="utf-8") as file_handle:
            yaml_text = file_handle.read()
        with self._state_lock:
            if self.state in {"running", "paused"}:
                raise RuntimeError("Stop or reset the simulation before changing the config.")
            self._set_config(yaml_text, source_kind="path", source_value=path)
            self._reset_runtime_storage()
            self.env.reset(self.raw_config["actors"])
            self.record_event({"type": "config_loaded", "text": path})
            self.record_snapshot("config_loaded")
            return self.get_config()

    def _reset_runtime_storage(self):
        self.event_history = []
        self.resource_history = []
        self.current_epoch = 0
        self.current_step = 0
        self.last_error = None
        self._manual_agent_index = 0

    def _next_run_id(self, prefix: str = "run"):
        self.run_sequence += 1
        return f"{prefix}-{self.run_sequence}-{uuid.uuid4().hex[:8]}"

    def _iter_known_agents(self):
        for actor in self.raw_config.get("actors", []):
            replicas = actor.get("replicas", 1)
            for index in range(replicas):
                agent_id = f"{actor['id']}_{index + 1}" if replicas > 1 else actor["id"]
                yield agent_id, actor

    def _find_agent_config(self, agent_id: str):
        for known_agent_id, actor in self._iter_known_agents():
            if known_agent_id == agent_id:
                return actor
        return None

    def list_agents(self):
        alive_agents = set(self.env.agents.keys())
        return [
            {
                "id": agent_id,
                "alive": agent_id in alive_agents,
            }
            for agent_id, _actor in self._iter_known_agents()
        ]

    def get_agent_details(self, agent_id: str):
        agent = self.env.agents.get(agent_id)
        if agent:
            return {
                "agent": agent_id,
                "portfolio": dict(self.env.portfolios.get(agent_id, {})),
                "constraints": deepcopy(getattr(agent, "constraints", {})),
                "config": deepcopy(getattr(agent, "config", {})),
                "alive": True,
                "death_reason": None,
            }

        actor = self._find_agent_config(agent_id)
        if not actor:
            return None

        portfolio = deepcopy(actor.get("initial_portfolio", {}))
        for snapshot in reversed(self.resource_history):
            if agent_id in snapshot["agents"]:
                portfolio = dict(snapshot["agents"][agent_id])
                break

        death_reason = None
        for event in reversed(self.event_history):
            if event.get("type") == "kill" and event.get("agent") == agent_id:
                death_reason = event.get("reason")
                break

        constraints = {
            **deepcopy(self.global_rules.get("constraints", {})),
            **deepcopy(actor.get("constraints", {})),
        }
        return {
            "agent": agent_id,
            "portfolio": portfolio,
            "constraints": constraints,
            "config": deepcopy(actor),
            "alive": False,
            "death_reason": death_reason,
        }

    def get_status(self):
        return {
            "state": self.state,
            "run_id": self.run_id,
            "epoch": self.current_epoch,
            "step": self.current_step,
            "last_error": self.last_error,
            "agent_count": len(self.env.agents),
            "available_actions": {
                "can_run": self.state in {"idle", "completed", "errored"},
                "can_pause": self.state == "running",
                "can_resume": self.state == "paused",
                "can_reset": self.state in {"idle", "paused", "completed", "errored"},
                "can_restart": self.state in {"idle", "running", "paused", "completed", "errored"},
                "can_step": self.state in {"idle", "paused", "completed", "errored"},
            },
        }

    def record_event(self, event: dict):
        normalized = dict(event)
        normalized.setdefault("timestamp", time.time())
        normalized.setdefault("run_id", self.run_id)
        normalized.setdefault("epoch", self.current_epoch or None)
        normalized.setdefault("step", self.current_step or None)
        normalized.setdefault("state", self.state)
        with self._state_lock:
            self.event_history.append(normalized)
            self.event_history = self.event_history[-50000:]
        return normalized

    def _compute_totals(self):
        totals = {}
        for portfolio in self.env.portfolios.values():
            for resource_name, amount in portfolio.items():
                totals[resource_name] = totals.get(resource_name, 0) + amount
        return totals

    def record_snapshot(self, reason: str, focus_agent: str = None):
        with self.env._lock:
            agents_copy = {agent_id: dict(portfolio) for agent_id, portfolio in self.env.portfolios.items()}
        snapshot = {
            "timestamp": time.time(),
            "run_id": self.run_id,
            "epoch": self.current_epoch,
            "step": self.current_step,
            "state": self.state,
            "reason": reason,
            "focus_agent": focus_agent,
            "totals": {res: sum(p.get(res, 0) for p in agents_copy.values()) for res in {r for p in agents_copy.values() for r in p}},
            "agents": agents_copy,
        }
        with self._state_lock:
            self.resource_history.append(snapshot)
            self.resource_history = self.resource_history[-2000:]
        return snapshot

    def get_global_timeline(self):
        with self._state_lock:
            return list(self.resource_history)

    def get_agent_timeline(self, agent_id: str):
        timeline = []
        for snapshot in self.resource_history:
            if agent_id in snapshot["agents"]:
                timeline.append({
                    "timestamp": snapshot["timestamp"],
                    "run_id": snapshot["run_id"],
                    "epoch": snapshot["epoch"],
                    "step": snapshot["step"],
                    "state": snapshot["state"],
                    "reason": snapshot["reason"],
                    "resources": snapshot["agents"][agent_id],
                })
        return timeline

    def get_agent_memory_graph(self, agent_id: str, limit: int = 80):
        return self.env.get_agent_memory_graph(agent_id, limit)

    def get_events(self, limit: int = 500):
        with self._state_lock:
            return self.event_history[-limit:]

    def get_events_page(self, limit: int = 500, offset: int = 0):
        """Paginazione degli eventi: offset 0 = più recenti."""
        with self._state_lock:
            total = len(self.event_history)
            start = max(0, total - limit - offset)
            end = max(0, total - offset)
            return self.event_history[start:end], total

    def make_ws_snapshot(self):
        """Restituisce l'ultimo snapshot come messaggio WS arricchito con stato e agenti."""
        if not self.resource_history:
            return None
        last = self.resource_history[-1]
        return {
            "type": "snapshot",
            **last,
            "agents_alive": self.list_agents(),
            "status": self.get_status(),
            "markets": self.get_markets(),
            "relations": self.get_relations(),
            "macro": self.get_macro_metrics(),
        }

    def stop_current_run(self, wait: bool = True):
        thread = None
        with self._state_lock:
            self._stop_event.set()
            self._pause_event.set()
            thread = self._run_thread
        if wait and thread and thread.is_alive():
            thread.join(timeout=5)
        with self._state_lock:
            self._run_thread = None

    def start_run(self):
        with self._state_lock:
            if self.state == "running":
                raise RuntimeError("Simulation is already running.")
            if self._run_thread and self._run_thread.is_alive():
                raise RuntimeError("Another run is still shutting down.")
            self._stop_event.clear()
            self._pause_event.set()
            self.state = "running"
            self.run_id = self._next_run_id("run")
            self._run_thread = threading.Thread(target=self.run, daemon=True)
            self._run_thread.start()
            return self.get_status()

    def pause_run(self):
        with self._state_lock:
            if self.state != "running":
                raise RuntimeError("Simulation is not running.")
            self._pause_event.clear()
            self.state = "paused"
            return self.get_status()

    def resume_run(self):
        with self._state_lock:
            if self.state != "paused":
                raise RuntimeError("Simulation is not paused.")
            self._pause_event.set()
            self.state = "running"
            return self.get_status()

    def restart_run(self):
        self.stop_current_run(wait=True)
        self.reset_simulation()
        return self.start_run()

    def reset_simulation(self):
        self.stop_current_run(wait=True)
        with self._state_lock:
            self.state = "idle"
            self.run_id = self._next_run_id("reset")
            self._reset_runtime_storage()
            self.env.reset(self.raw_config["actors"])
            self.record_event({"type": "reset", "text": "Simulation reset"})
            self.record_snapshot("reset")
            return self.get_status()

    def step_once(self, agent_id: str = None):
        with self._state_lock:
            if self.state == "running":
                raise RuntimeError("Pause the simulation before stepping manually.")
            if self.state in {"completed", "errored", "idle"} and not self.env.agents:
                self.env.reset(self.raw_config["actors"])
            if not self.run_id:
                self.run_id = self._next_run_id("manual")
            previous_state = self.state
            self.state = "paused" if previous_state == "paused" else "idle"
            if self.current_epoch == 0:
                self.current_epoch = 1
            self.current_step += 1
            active_agents = list(self.env.agents.keys())
            if not active_agents:
                return self.get_status()
            if agent_id:
                selected_agent = agent_id
            else:
                self._manual_agent_index = self._manual_agent_index % len(active_agents)
                selected_agent = active_agents[self._manual_agent_index]
                self._manual_agent_index += 1
            if selected_agent not in self.env.agents:
                raise RuntimeError(f"Agent '{selected_agent}' not found.")
        if self.log:
            self.log.print_step(self.current_step)
        self.env._current_tick = self.current_step
        self._step_agent(selected_agent)
        self._run_market_clearing()
        self._run_world_events()
        self._update_price_expectations()
        self._run_macro_step()
        self.record_snapshot("manual_step", selected_agent)
        return self.get_status()

    def _wait_if_paused(self):
        while not self._pause_event.is_set():
            if self._stop_event.is_set():
                return False
            time.sleep(0.05)
        return not self._stop_event.is_set()

    def _apply_maintenance(self, ids):
        """Deduct per-step maintenance resource costs and evaluate kill conditions.

        For each agent in *ids*:
        * Subtracts ``global_rules.maintenance`` amounts from their portfolio.
        * Decays the ``panic`` resource toward 0 by ``panic_decay_rate``.
        * Optionally increases ``panic`` based on portfolio value distress
          compared to the previous snapshot.
        * Checks all applicable kill conditions; eliminates agents that
          breach any threshold.

        Also decays all trust edges toward neutral (0.5) by ``trust_decay_rate``.
        """
        maintenance = self.global_rules.get("maintenance", {})
        rel_dyn = self.global_rules.get("relation_dynamics", {})
        trust_decay = rel_dyn.get("trust_decay_rate", 0.0)
        panic_decay = rel_dyn.get("panic_decay_rate", 0.0)

        # Hold the shared environment lock for the entire maintenance pass so that
        # portfolio mutations are visible atomically to any agent threads that
        # snapshot state during a parallel step.
        with self.env._lock:
            for agent_id in list(ids):
                if agent_id not in self.env.agents:
                    continue
                for resource_name, amount in maintenance.items():
                    self.env.portfolios[agent_id][resource_name] = self.env.portfolios[agent_id].get(resource_name, 0) - amount
                # Decay panic resource toward 0 (clamp at 0)
                if panic_decay and "panic" in self.env.portfolios[agent_id]:
                    current_panic = self.env.portfolios[agent_id]["panic"]
                    self.env.portfolios[agent_id]["panic"] = max(0.0, current_panic - panic_decay)
                # Portfolio distress → panic feedback
                distress_rate = rel_dyn.get("portfolio_distress_panic_rate", 0.0)
                if distress_rate > 0.0 and self.resource_history:
                    prev_snap = self.resource_history[-1]
                    if agent_id in prev_snap.get("agents", {}):
                        prev_port = prev_snap["agents"][agent_id]
                        prev_total = sum(max(0.0, v) for v in prev_port.values() if isinstance(v, (int, float)))
                        curr_total = sum(max(0.0, self.env.portfolios[agent_id].get(r, 0)) for r in prev_port)
                        if prev_total > 0:
                            drop = (prev_total - curr_total) / prev_total
                            if drop > 0:
                                self.env.portfolios[agent_id]["panic"] = (
                                    self.env.portfolios[agent_id].get("panic", 0.0)
                                    + drop * distress_rate
                                )
                kill_conds = self.global_rules.get("kill_conditions", []) + self.env.agents[agent_id].config.get("kill_conditions", [])
                for cond in kill_conds:
                    resource_name = cond["resource"]
                    threshold = cond["threshold"]
                    if self.env.portfolios[agent_id].get(resource_name, 0) <= threshold:
                        if self.log:
                            self.log.print_kill(agent_id, f"Condition met: {resource_name} <= {threshold}")
                        self.record_event({"type": "kill", "agent": agent_id, "reason": f"{resource_name} <= {threshold}"})
                        if agent_id in self.env.agents:
                            del self.env.agents[agent_id]
                        if agent_id in self.env.portfolios:
                            del self.env.portfolios[agent_id]
                        break

            # Trust decay toward neutral (also under the lock: relation graph is not internally locked)
            if trust_decay:
                self.env.relation_graph.decay_all(trust_decay)

    def godmode(self, action: str, params: dict) -> str:
        """Privileged operator interface for live state overrides.

        Supported *action* values:

        * ``inject_resource``    — add *amount* of *resource* to *agent*’s portfolio.
        * ``set_constraint``     — update min/max constraint for *resource* on *agent*.
        * ``set_portfolio``      — replace *agent*’s entire portfolio with *portfolio*.
        * ``send_message``       — inject a message into *agent*’s AutoGen history.
        * ``impersonate_action`` — invoke a registered function on *agent*’s behalf.

        All successful actions record a snapshot tagged with the godmode action name.
        Returns:
            ``"SUCCESS: <action> executed."`` or a ``"FAILED: …"`` message.
        """
        if action == 'inject_resource':
            with self.env._lock:
                agent = params['agent']
                resource_name = params['resource']
                amount = params['amount']
                if agent not in self.env.portfolios:
                    return f"FAILED: Agent {agent} not found."
                self.env.portfolios[agent][resource_name] = self.env.portfolios[agent].get(resource_name, 0) + amount
        elif action == 'set_constraint':
            with self.env._lock:
                agent = params['agent']
                resource_name = params['resource']
                minv = params.get('min')
                maxv = params.get('max')
                if agent not in self.env.agents:
                    return f"FAILED: Agent {agent} not found."
                if resource_name not in self.env.agents[agent].constraints:
                    self.env.agents[agent].constraints[resource_name] = {}
                if minv is not None:
                    self.env.agents[agent].constraints[resource_name]['min'] = minv
                if maxv is not None:
                    self.env.agents[agent].constraints[resource_name]['max'] = maxv
        elif action == 'set_portfolio':
            with self.env._lock:
                agent = params['agent']
                portfolio = params['portfolio']
                if agent not in self.env.portfolios:
                    return f"FAILED: Agent {agent} not found."
                self.env.portfolios[agent] = dict(portfolio)
        elif action == 'send_message':
            target = params['to']
            message = params['message']
            if target not in self.env.agents:
                return f"FAILED: Agent {target} not found."
            self.env.agents[target].receive(message=message, sender="HUMAN", request_reply=False)
        elif action == 'impersonate_action':
            agent = params['agent']
            func = params['function']
            args = params.get('args', {})
            if agent not in self.env.agents:
                return f"FAILED: Agent {agent} not found."
            target_agent = self.env.agents[agent]
            function_ref = getattr(target_agent, func, None) or target_agent._function_map.get(func)
            if not function_ref:
                return f"FAILED: Function {func} not found for agent {agent}."
            try:
                function_ref(**args) if args else function_ref()
            except Exception as exc:
                return f"FAILED: Exception: {exc}"
        else:
            return "FAILED: Unknown godmode action."
        self.record_snapshot(f"godmode:{action}", params.get("agent"))
        return f"SUCCESS: {action} executed."

    def export_data(self, query: dict, format: str = "json"):
        result = {}
        if query is None or not isinstance(query, dict) or len(query) == 0:
            query = {"agents": True, "portfolios": True, "trades": True, "history": True, "resources": True, "markets": True, "relations": True}
        if query.get("agents"):
            result["agents"] = list(self.env.agents.keys())
        if "portfolios" in query:
            if query["portfolios"] is True:
                result["portfolios"] = {agent_id: dict(values) for agent_id, values in self.env.portfolios.items()}
            elif isinstance(query["portfolios"], list):
                result["portfolios"] = {agent_id: dict(self.env.portfolios[agent_id]) for agent_id in query["portfolios"] if agent_id in self.env.portfolios}
        if query.get("trades"):
            result["trades"] = dict(self.env.pending_trades)
        if "resources" in query:
            result["resources"] = {
                "totals": self._compute_totals(),
                "agents": {agent_id: dict(values) for agent_id, values in self.env.portfolios.items()},
            }
        if query.get("markets"):
            result["markets"] = self.get_markets()
        if query.get("relations"):
            result["relations"] = self.get_relations()
        if query.get("history"):
            result["history"] = {
                "events": self.event_history,
                "timeline": self.resource_history,
            }
        if format == "dict":
            return result
        if format == "json":
            return result
        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            if "resources" in result:
                resource_names = sorted(result["resources"]["totals"].keys())
                writer.writerow(["agent"] + resource_names)
                for agent_id, portfolio in result["resources"]["agents"].items():
                    writer.writerow([agent_id] + [portfolio.get(resource_name, 0) for resource_name in resource_names])
            elif "portfolios" in result:
                resource_names = sorted({resource_name for values in result["portfolios"].values() for resource_name in values.keys()})
                writer.writerow(["agent"] + resource_names)
                for agent_id, portfolio in result["portfolios"].items():
                    writer.writerow([agent_id] + [portfolio.get(resource_name, 0) for resource_name in resource_names])
            else:
                writer.writerow(["message"])
                writer.writerow(["CSV export supported only for portfolios/resources."])
            return output.getvalue()
        raise ValueError(f"Format '{format}' not supported.")

    def build_export_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            manifest = {
                "generated_at": time.time(),
                "run_id": self.run_id,
                "status": self.get_status(),
                "config_source": self.config_source,
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("config.yaml", self.config_text)
            archive.writestr("events/events.json", json.dumps(self.event_history, indent=2))
            archive.writestr("events/timeline.json", json.dumps(self.resource_history, indent=2))
            archive.writestr("events/events.csv", self._events_csv())
            for agent_id in sorted(self.env.portfolios.keys()):
                archive.writestr(f"resources/{agent_id}.csv", self._agent_timeline_csv(agent_id))
        buffer.seek(0)
        return buffer.getvalue()

    def _events_csv(self):
        output = io.StringIO()
        fieldnames = ["timestamp", "run_id", "state", "epoch", "step", "type", "agent", "target", "action", "text", "result", "reason"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for event in self.event_history:
            writer.writerow({key: json.dumps(event.get(key)) if isinstance(event.get(key), (dict, list)) else event.get(key) for key in fieldnames})
        return output.getvalue()

    def _summary(self):
        '''Generate a brief text summary of the last simulation, using DoxaChatbot as a NLP engine explainer, based on _events_csv'''
        prompt = f"""Given the following CSV of events from a multi-agent simulation, provide a brief summary of the key outcomes, trends, and notable moments. Focus on high-level insights rather than granular details.
CSV:
{self._events_csv()}
Summary:"""
        a = self.chatbot.ask(prompt)
        return a

    def _agent_timeline_csv(self, agent_id: str):
        timeline = self.get_agent_timeline(agent_id)
        resource_names = sorted({resource_name for point in timeline for resource_name in point["resources"].keys()})
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "run_id", "epoch", "step", "state", "reason"] + resource_names)
        for point in timeline:
            writer.writerow([
                point["timestamp"],
                point["run_id"],
                point["epoch"],
                point["step"],
                point["state"],
                point["reason"],
            ] + [point["resources"].get(resource_name, 0) for resource_name in resource_names])
        return output.getvalue()

    def startOllama(self):
        import subprocess

        def run_ollama_serve():
            subprocess.Popen(["ollama", "serve"])

        thread = threading.Thread(target=run_ollama_serve, daemon=True)
        thread.start()
        time.sleep(5)

    def run(self):
        """Main simulation loop — runs on the background thread started by ``start_run()``.

        Iterates over ``epochs`` \u00d7 ``steps`` (from YAML ``global_rules``).  Each
        step:

        1. Shuffles agent order (sequential mode) or fans out to a thread pool
           (parallel mode).
        2. Applies maintenance costs and checks kill conditions.
        3. Runs each agent’s LLM turn (tool-call loop via ``_step_agent``).
        4. Clears markets (``_run_market_clearing``).
        5. Fires world events (``_run_world_events``).
        6. Updates EWA price expectations (``_update_price_expectations``).
        7. Records a macro snapshot (``_run_macro_step``).

        Sets ``self.state`` to ``"completed"`` on clean exit or ``"errored"``
        on exception.  Always clears the ``_run_thread`` reference on exit.
        """
        try:
            self._reset_runtime_storage()
            epochs = self.global_rules.get('epochs', 1)
            steps = self.global_rules.get('steps', 5)
            mode = self.global_rules.get('execution_mode', 'sequential')
            for epoch_index in range(epochs):
                if self._stop_event.is_set():
                    break
                if not self._wait_if_paused():
                    break
                self.current_epoch = epoch_index + 1
                self.current_step = 0
                self.env.reset(self.raw_config['actors'])
                if self.log:
                    self.log.print_epoch(self.current_epoch)
                self.record_snapshot("epoch_start")
                for step_index in range(steps):
                    if self._stop_event.is_set():
                        break
                    if not self._wait_if_paused():
                        break
                    self.current_step = step_index + 1
                    self.env._current_tick = self.current_step
                    if self.log:
                        self.log.print_step(self.current_step)
                    ids = list(self.env.agents.keys())
                    random.shuffle(ids)
                    self._apply_maintenance(ids)
                    active_ids = [agent_id for agent_id in ids if agent_id in self.env.agents]
                    if mode == 'sequential':
                        step_delay = self.global_rules.get('step_delay', 0)
                        for agent_id in active_ids:
                            if self._stop_event.is_set():
                                break
                            if not self._wait_if_paused():
                                break
                            self._step_agent(agent_id)
                            self.record_snapshot("agent_step", agent_id)
                            if step_delay > 0:
                                time.sleep(step_delay)
                    else:
                        with ThreadPoolExecutor() as executor:
                            executor.map(self._step_agent, active_ids)
                        self.record_snapshot("step_complete")
                    # Market clearing (per_step / call_auction markets)
                    self._run_market_clearing()
                    # World events
                    self._run_world_events()
                    # Price expectations + macro metrics
                    self._update_price_expectations()
                    self._run_macro_step()
                for agent_id in list(self.env.agents.keys()):
                    self.check_victory_conditions(agent_id)
            with self._state_lock:
                if self.state != "errored":
                    self.state = "completed" if not self._stop_event.is_set() else "idle"
        except Exception as exc:
            with self._state_lock:
                self.state = "errored"
                self.last_error = str(exc)
            self.record_event({"type": "error", "text": str(exc)})
            raise
        finally:
            with self._state_lock:
                self._run_thread = None
                self._stop_event.clear()
                self._pause_event.set()

    def _is_transient_llm_error(self, message: str) -> bool:
        lowered = message.lower()
        uppered = message.upper()
        return (
            "503" in message
            or "429" in message
            or "UNAVAILABLE" in uppered
            or "high demand" in lowered
            or "rate limit" in lowered
            or "timeout" in lowered
            or "temporarily unavailable" in lowered
        )

    def _generate_reply_with_retry(self, agent, a_id: str, max_attempts: int = 3, base_delay: float = None):
        provider = getattr(agent, 'provider', 'ollama')
        if base_delay is None:
            base_delay = 2.0 if provider == 'google' else 0.4
        messages = agent.chat_messages[agent] + [{"role": "user", "content": "Your turn."}]
        for attempt in range(1, max_attempts + 1):
            try:
                return agent.generate_reply(messages=messages)
            except Exception as exc:
                message = str(exc)
                if not self._is_transient_llm_error(message):
                    raise
                last_attempt = attempt == max_attempts
                notice = (
                    f"FAILED: transient LLM error for {a_id} after {attempt} attempts: {message}"
                    if last_attempt
                    else f"RETRY {attempt}/{max_attempts}: transient LLM error for {a_id}: {message}"
                )
                if self.log:
                    self.log.print_action(a_id, "llm_generate_reply", None, notice)
                self.record_event({
                    "type": "llm_transient_error",
                    "agent": a_id,
                    "attempt": attempt,
                    "text": notice,
                })
                if last_attempt:
                    return None
                time.sleep(base_delay * (2 ** (attempt - 1)))
        return None

    def _step_agent(self, a_id):
        """Run one LLM turn for agent *a_id* and dispatch the resulting tool-calls.

        Calls ``generate_reply()`` with retry logic for transient API errors.
        The reply is either:

        * A ``dict`` with ``"tool_calls"`` — each call is dispatched through the
          agent’s registered ``_function_map`` (standard tools) or falls back
          to ``env.execute_operation()`` for custom YAML ops.
        * A plain ``str`` (implicit thought) — logged but not acted upon.

        After all tool calls the agent’s victory conditions are checked.
        """
        if a_id not in self.env.agents:
            return
        if self.log:
            self.log.print_turn(a_id)
        agent = self.env.agents[a_id]
        reply = self._generate_reply_with_retry(agent, a_id)
        if reply is None:
            return
        if isinstance(reply, dict) and "tool_calls" in reply:
            for tc in reply["tool_calls"]:
                try:
                    res = agent.execute_function(tc['function'])
                    if isinstance(res, tuple) and res[0] is False:
                        raise Exception(res[1].get('content', 'Unknown error'))
                except Exception:
                    ftc = tc['function'] if 'function' in tc else tc
                    if ftc is None or 'name' not in ftc:
                        res = "FAILED: Tool call missing or malformed."
                        if self.log:
                            self.log.print_action(a_id, "tool_call", None, res)
                        agent.send(str(res), agent, request_reply=False, silent=True)
                        continue
                    name = ftc['name'][3:] if ftc['name'].startswith('op_') else ftc['name']
                    args = ftc.get('arguments', {})
                    if not isinstance(args, dict):
                        try:
                            args = json.loads(args)
                        except Exception as exc:
                            res = f"FAILED: Invalid arguments for tool '{name}': {exc}"
                            if self.log:
                                self.log.print_action(a_id, f"op_{name}", None, res)
                            agent.send(str(res), agent, request_reply=False, silent=True)
                            continue
                    target = args.get('target')
                    multiplier = args.get('multiplier', args.get('inputMultiplier', 1))
                    function_name = ftc['name']
                    function_ref = getattr(agent, function_name, None) or agent._function_map.get(function_name)
                    if not function_ref and function_name != name:
                        function_ref = getattr(agent, name, None) or agent._function_map.get(name)
                    if function_ref:
                        try:
                            res = function_ref(**args) if args else function_ref()
                        except TypeError as exc:
                            res = f"FAILED: Invalid arguments for tool '{name}': {exc}"
                        except Exception as exc:
                            res = f"FAILED: Tool '{name}' raised exception: {exc}"
                    else:
                        res = self.env.execute_operation(a_id, name, target, multiplier)
                    if self.log:
                        self.log.print_action(a_id, f"op_{name}", target, res)
                agent.send(str(res), agent, request_reply=False, silent=True)
        elif isinstance(reply, str) and reply.strip() and self.log:
            self.log.print_think(a_id, f"(Implicit) {reply}")
        self.check_victory_conditions(a_id)

    def _run_market_clearing(self):
        """Expire stale orders, re-quote market makers, then match for per_step and call_auction markets."""
        me = self.env.market_engine
        if not me:
            return
        me.expire_orders(self.current_step, self.env.portfolios)
        me.refresh_market_makers(self.env.portfolios, self.current_step)
        for resource, market in me.markets.items():
            if market.config.get("clearing", "per_step") in ("per_step", "call_auction"):
                fills = me.clear_market(resource, self.env.portfolios, self.current_step)
                for fill in fills:
                    self.record_event({"type": "market_fill", **fill})
                    if self.log:
                        self.log.print_market_fill(
                            fill["buyer"], fill["seller"],
                            fill["fill_qty"], fill["resource"],
                            fill["fill_price"], market.currency,
                        )

    def _run_world_events(self):
        """Tick the world event scheduler and record any fired events."""
        scheduler = self.env.event_scheduler
        if not scheduler:
            return
        fired = scheduler.tick(
            portfolios=self.env.portfolios,
            agents=self.env.agents,
            market_engine=self.env.market_engine,
            relation_graph=self.env.relation_graph,
            engine_ref=self,
            current_tick=self.current_step,
        )
        for ev_record in fired:
            self.record_event({"type": "world_event", **ev_record})
            if self.log:
                self.log.print(f"[WORLD EVENT] {ev_record['name']} ({ev_record['type']}): {ev_record.get('effects', [])}")

    def _update_price_expectations(self):
        """Update per-agent EWA price expectations from current market prices."""
        me = self.env.market_engine
        if not me:
            return
        econ_map = self.env.agent_economics_map
        if not econ_map:
            return
        for resource, market in me.markets.items():
            current_price = market.current_price
            for agent_id, econ in econ_map.items():
                lr = econ.learning_rate
                prev = self.env.price_expectations.get(agent_id, {}).get(resource, current_price)
                new_exp = round((1.0 - lr) * prev + lr * current_price, 8)
                self.env.price_expectations.setdefault(agent_id, {})[resource] = new_exp

    def _run_macro_step(self):
        """Compute and record macro-level metrics (Gini, HHI, volatility, panic)."""
        snap = self.env.macro_tracker.compute(
            self.env.portfolios, self.env.market_engine, self.current_step
        )
        self.record_event({"type": "macro_snapshot", **snap})

    def get_macro_metrics(self) -> Dict:
        """Return the latest macro metrics snapshot."""
        latest = self.env.macro_tracker.latest()
        return latest or {"tick": self.current_step, "resources": {}, "market_stats": {}, "system_panic": 0.0}

    def get_macro_history(self) -> List[Dict]:
        """Return full macro metrics history."""
        return list(self.env.macro_tracker.history)

    def get_markets(self) -> Dict:
        """Return market summary for API."""
        me = self.env.market_engine
        if not me:
            return {}
        return me.summary()

    def get_market_orderbook(self, resource: str, depth: int = 10) -> Optional[Dict]:
        """Return full order book for a resource."""
        me = self.env.market_engine
        if not me:
            return None
        return me.get_order_book(resource, depth)

    def get_market_price_history(self, resource: str) -> Optional[Dict]:
        """Return price history for a resource market."""
        me = self.env.market_engine
        if not me:
            return None
        m = me.markets.get(resource)
        if not m:
            return None
        return {"resource": resource, "prices": [{"tick": t, "price": p} for t, p in m.price_history]}

    def get_relations(self) -> List[Dict]:
        """Return full relation graph as list of relation records."""
        return self.env.relation_graph.to_list()

    def check_victory_conditions(self, a_id):
        """Check and record any victory conditions met by *a_id* after its turn.

        Conditions can be scoped:
        * ``individual`` — agent’s own resource quantity meets the threshold.
        * global (default) — the *total* resource across all portfolios meets
          the threshold (fires for ``"GLOBAL"`` rather than the agent).
        """
        if a_id not in self.env.agents or a_id not in self.env.portfolios:
            return
        conditions = self.global_rules.get('victory_conditions', []) + self.env.agents[a_id].config.get('victory_conditions', [])
        for cond in conditions:
            resource_name = cond['resource']
            threshold = cond['threshold']
            scope = cond.get('scope', 'global')
            if scope == 'individual':
                if self.env.portfolios[a_id].get(resource_name, 0) >= threshold:
                    if self.log:
                        self.log.print_victory(f"{a_id} wins with {resource_name} = {self.env.portfolios[a_id].get(resource_name, 0)}")
                    self.record_event({"type": "victory", "agent": a_id, "resource": resource_name, "value": self.env.portfolios[a_id].get(resource_name, 0)})
            else:
                total_value = sum(portfolio.get(resource_name, 0) for portfolio in self.env.portfolios.values())
                if total_value >= threshold:
                    if self.log:
                        self.log.print_victory(f"GLOBAL wins with total {resource_name} = {total_value}")
                    self.record_event({"type": "victory", "agent": "GLOBAL", "resource": resource_name, "value": total_value})
        


# ==========================================
# 5. CONFIG (Dilemma + Trade)
# ==========================================
config_yaml = """
global_rules:
  epochs: 1
  steps: 12
  execution_mode: sequential
  maintenance:
    corn: 1
  kill_conditions:
  - resource: corn
    threshold: 0
  victory_conditions:
  - resource: gold
    threshold: 34
    scope: individual
  relation_dynamics:
    on_trade_success:
      trust_delta: 0.03
    on_trade_rejected:
      trust_delta: -0.02
    on_broadcast:
      trust_delta: 0.01
    trust_decay_rate: 0.01
    panic_decay_rate: 0.05
  relations:
  - source: player
    target: miners
    trust: 0.68
    type: neutral
  - source: miners
    target: player
    trust: 0.58
    type: neutral
  markets:
  - resource: gold
    currency: credits
    initial_price: 6.0
    min_price: 1.0
    max_price: 40.0
    clearing: per_step
  - resource: corn
    currency: credits
    initial_price: 2.4
    min_price: 0.5
    max_price: 15.0
    clearing: per_step
world_events:
- name: gold_spike
  type: shock
  trigger:
    tick: 4
  effect:
    market: gold
    price_multiplier: 1.4
- name: corn_shortage
  type: shock
  trigger:
    tick: 6
  effect:
    market: corn
    price_multiplier: 1.35
- name: panic_wave
  type: trend
  trigger:
    tick: 2
  duration: 3
  effect:
    targets: all
    resource: panic
    rate: 0.08
- name: food_relief
  type: conditional
  trigger:
    condition:
      resource: corn
      operator: lt
      threshold: 6
      scope: any_agent
  effect:
    targets: all
    resource: corn
    delta: 3
actors:
- id: player
  provider: google
  model_name: gemini-2.5-pro
  persona: Farmer-trader. Your core business is converting gold into corn. Keep enough corn to survive maintenance and monetize surplus.
  trading_mode: lob
  initial_portfolio:
    credits: 45
    corn: 12
    gold: 5
    panic: 0.0
  constraints:
    gold:
      min: 0
    corn:
      min: 0
    credits:
      min: 0
    panic:
      min: 0
      max: 1
  operations:
    farm:
      input:
        gold: 1
      output:
        corn: 4
- id: miners
  provider: google
  model_name: gemini-2.5-pro
  persona: Miner-merchant. Your core business is converting corn into gold. Keep enough corn to continue mining.
  trading_mode: lob
  initial_portfolio:
    credits: 55
    corn: 6
    gold: 16
    panic: 0.0
  constraints:
    gold:
      min: 0
    corn:
      min: 0
    credits:
      min: 0
    panic:
      min: 0
      max: 1
  operations:
    mine:
      input:
        corn: 2
      output:
        gold: 5
"""