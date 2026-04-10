"""
events.WorldEventScheduler
---------------------------
Parses, evaluates, and applies world events during the simulation loop.

Event types
~~~~~~~~~~~
* ``shock``       \u2014 fires **once** when ``current_tick >= trigger.tick``.
                   Applies ``effect.delta`` to target portfolios and / or
                   multiplies a market price.
* ``trend``       \u2014 fires for ``duration`` consecutive ticks starting at
                   ``trigger.tick`` (or when a condition first becomes true).
                   Applies ``effect.rate`` each tick.
* ``conditional`` \u2014 fires **once** the first time the portfolio condition
                   (resource / operator / threshold / scope) is satisfied.

At the end of each epoch, ``reset()`` deep-copies the original event
definitions back so every epoch starts with a clean state.

Call sequence per simulation step
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. ``DoxaEngine._run_world_events()`` calls ``scheduler.tick(...)``
2. ``tick()`` iterates all ``WorldEventDef`` objects and decides which
   should fire this tick.
3. For each firing event ``_apply()`` mutates portfolios, market prices,
   and relation-graph trust edges as specified.
4. ``tick()`` returns a list of event-record dicts that are appended to
   ``DoxaEngine.event_history``.
"""
from typing import Dict, List
from copy import deepcopy
from market.MarketEngine import MarketEngine
from relations.RelationGraph import RelationGraph
from events.WorldEventEffect import WorldEventDef, WorldEventEffect

def _parse_world_event(raw: Dict) -> WorldEventDef:
    """Convert a raw YAML event dict into a ``WorldEventDef`` instance."""
    eff_raw = raw.get("effect", {})
    effect = WorldEventEffect(
        targets=eff_raw.get("targets", "all"),
        resource=eff_raw.get("resource"),
        delta=eff_raw.get("delta"),
        rate=eff_raw.get("rate"),
        market=eff_raw.get("market"),
        price_multiplier=eff_raw.get("price_multiplier"),
        price_set=eff_raw.get("price_set"),
        trust_source=eff_raw.get("trust_source"),
        trust_delta=eff_raw.get("trust_delta"),
        contagion_rate=float(eff_raw.get("contagion_rate", 0.0)),
    )
    trigger = raw.get("trigger", {})
    cond = trigger.get("condition", {})
    return WorldEventDef(
        name=raw["name"],
        event_type=raw.get("type", "shock"),
        effect=effect,
        trigger_tick=trigger.get("tick"),
        duration=raw.get("duration", 1),
        condition_resource=cond.get("resource"),
        condition_operator=cond.get("operator"),
        condition_threshold=cond.get("threshold"),
        condition_scope=cond.get("scope", "any_agent"),
    )


class WorldEventScheduler:
    """Evaluates and applies world events each simulation tick."""

    def __init__(self, events_cfg: List[Dict]):
        """Parse *events_cfg* (the ``world_events`` YAML list) into ``WorldEventDef`` objects."""
        self._defs = [_parse_world_event(e) for e in (events_cfg or [])]
        # Deep-copy preserved for epoch resets
        self._initial_defs = deepcopy(self._defs)

    def reset(self):
        """Restore all event definitions to their initial (untriggered) state for a new epoch."""
        self._defs = deepcopy(self._initial_defs)

    def tick(self, portfolios: Dict, agents: Dict, market_engine: "MarketEngine",
             relation_graph: "RelationGraph", engine_ref, current_tick: int) -> List[Dict]:
        """Advance the event scheduler by one tick and apply any events that should fire.

        Args:
            portfolios:      Live ``{agent_id: {resource: qty}}`` dict (mutated in-place).
            agents:          Live agent objects dict (read-only; used for target resolution).
            market_engine:   ``MarketEngine`` instance (mutated for price effects).
            relation_graph:  ``RelationGraph`` instance (mutated for trust effects).
            engine_ref:      Reference to the ``DoxaEngine`` (currently unused; reserved
                             for future hook support).
            current_tick:    Current simulation tick index.

        Returns:
            List of event-record dicts, each with keys
            ``name``, ``type``, ``tick``, ``effects`` (list of change strings).
        """
        fired = []
        for ev in self._defs:
            should_apply = False

            # \u2500\u2500 Shock: fires once on or after trigger_tick \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            if ev.event_type == "shock" and not ev.triggered:
                if ev.trigger_tick is not None and current_tick >= ev.trigger_tick:
                    should_apply = True
                    ev.triggered = True

            # \u2500\u2500 Trend: fires each tick for `duration` ticks after start condition \u2500\u2500\u2500\u2500
            elif ev.event_type == "trend" and not ev.triggered:
                if ev.trigger_tick is not None and current_tick >= ev.trigger_tick:
                    ev.triggered = True
                    ev.remaining = ev.duration
                    should_apply = True
                elif ev.trigger_tick is None:
                    # Condition-based trend start
                    if self._check_condition(ev, portfolios):
                        ev.triggered = True
                        ev.remaining = ev.duration
                        should_apply = True

            elif ev.event_type == "trend" and ev.triggered and ev.remaining > 0:
                should_apply = True  # Trend still has ticks left

            # \u2500\u2500 Conditional: fires once the first time condition is satisfied \u2500\u2500\u2500\u2500\u2500\u2500
            elif ev.event_type == "conditional" and not ev.triggered:
                if self._check_condition(ev, portfolios):
                    should_apply = True
                    ev.triggered = True

            if should_apply:
                result = self._apply(ev, portfolios, agents, market_engine, relation_graph, current_tick)
                fired.append({"name": ev.name, "type": ev.event_type, "tick": current_tick, "effects": result})
                # Decrement trend counter after application
                if ev.event_type == "trend" and ev.remaining > 0:
                    ev.remaining -= 1

        return fired

    def _check_condition(self, ev: WorldEventDef, portfolios: Dict) -> bool:
        """Evaluate the portfolio condition for *ev* against current portfolios.

        Returns ``True`` if the condition is satisfied according to
        ``ev.condition_scope`` (``any_agent`` or ``all_agents``).
        """
        if not ev.condition_resource or ev.condition_threshold is None:
            return False
        op = ev.condition_operator or "lt"
        res = ev.condition_resource
        thresh = ev.condition_threshold
        values = [p.get(res, 0) for p in portfolios.values()]
        if not values:
            return False

        def _test(v):
            if op == "lt": return v < thresh
            if op == "gt": return v > thresh
            if op == "le": return v <= thresh
            if op == "ge": return v >= thresh
            if op == "eq": return v == thresh
            return False

        if ev.condition_scope == "all_agents":
            return all(_test(v) for v in values)
        return any(_test(v) for v in values)

    def _resolve_targets(self, targets, agents: Dict) -> List[str]:
        """Resolve the ``targets`` field to a concrete list of agent IDs."""
        if targets == "all":
            return list(agents.keys())
        if isinstance(targets, list):
            return [t for t in targets if t in agents]
        if isinstance(targets, str) and targets in agents:
            return [targets]
        return []

    def _apply(self, ev: WorldEventDef, portfolios: Dict, agents: Dict,
               market_engine: "MarketEngine", relation_graph: "RelationGraph",
               tick: int) -> List[str]:
        """Apply the event effect and return a list of human-readable change strings."""
        eff = ev.effect
        results = []
        target_ids = self._resolve_targets(eff.targets, agents)

        # \u2500\u2500 1. Portfolio resource delta / rate \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if eff.resource:
            # Shocks/conditionals use one-time delta; trends use per-step rate.
            amount = eff.delta if ev.event_type in ("shock", "conditional") else eff.rate
            if amount is not None:
                for aid in target_ids:
                    port = portfolios.get(aid, {})
                    port[eff.resource] = port.get(eff.resource, 0) + amount
                    results.append(f"{aid}.{eff.resource} {'+' if amount >= 0 else ''}{amount}")

        # \u2500\u2500 2. Market price effect \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if eff.market and market_engine and eff.market in market_engine.markets:
            m = market_engine.markets[eff.market]
            if eff.price_set is not None:
                m.current_price = eff.price_set
                m.price_history.append((tick, m.current_price))
                results.append(f"market.{eff.market}.price_set={eff.price_set}")
            elif eff.price_multiplier is not None:
                m.current_price = round(m.current_price * eff.price_multiplier, 8)
                cfg = m.config
                # Clamp to configured price bounds
                m.current_price = max(cfg.get("min_price", 0), min(cfg.get("max_price", float("inf")), m.current_price))
                m.price_history.append((tick, m.current_price))
                results.append(f"market.{eff.market}.price\u00d7{eff.price_multiplier}={m.current_price}")

        # \u2500\u2500 3. Trust effect (directed from trust_source to each target) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if eff.trust_source and eff.trust_delta and relation_graph:
            src = eff.trust_source
            for tgt in target_ids:
                if tgt != src:
                    relation_graph.update_trust(src, tgt, eff.trust_delta)
                    results.append(f"trust.{src}->{tgt} {'+' if eff.trust_delta >= 0 else ''}{eff.trust_delta}")

        # \u2500\u2500 4. Contagion: propagate resource delta through trust graph \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if eff.contagion_rate > 0.0 and eff.resource and relation_graph:
            base_amount = (eff.delta if ev.event_type in ("shock", "conditional") else eff.rate) or 0.0
            for aid in target_ids:
                for rec in relation_graph.get_relations_for(aid):
                    neighbor = rec.target
                    if neighbor in portfolios and neighbor not in target_ids:
                        # Contagion amount scales with trust and contagion_rate
                        spread = base_amount * eff.contagion_rate * rec.trust
                        portfolios[neighbor][eff.resource] = (
                            portfolios[neighbor].get(eff.resource, 0) + spread
                        )
                        results.append(
                            f"contagion.{aid}->{neighbor}.{eff.resource} "
                            f"{'+' if spread >= 0 else ''}{spread:.4f}"
                        )

        return results


class WorldEventScheduler:
    """Evaluates and applies world events each simulation tick."""

    def __init__(self, events_cfg: List[Dict]):
        self._defs = [_parse_world_event(e) for e in (events_cfg or [])]
        # Deep-copy for reset
        self._initial_defs = deepcopy(self._defs)

    def reset(self):
        self._defs = deepcopy(self._initial_defs)

    def tick(self, portfolios: Dict, agents: Dict, market_engine: "MarketEngine",
             relation_graph: "RelationGraph", engine_ref, current_tick: int) -> List[Dict]:
        fired = []
        for ev in self._defs:
            should_apply = False

            if ev.event_type == "shock" and not ev.triggered:
                if ev.trigger_tick is not None and current_tick >= ev.trigger_tick:
                    should_apply = True
                    ev.triggered = True

            elif ev.event_type == "trend" and not ev.triggered:
                if ev.trigger_tick is not None and current_tick >= ev.trigger_tick:
                    ev.triggered = True
                    ev.remaining = ev.duration
                    should_apply = True
                elif ev.trigger_tick is None:
                    # condition-based trend start
                    if self._check_condition(ev, portfolios):
                        ev.triggered = True
                        ev.remaining = ev.duration
                        should_apply = True

            elif ev.event_type == "trend" and ev.triggered and ev.remaining > 0:
                should_apply = True

            elif ev.event_type == "conditional" and not ev.triggered:
                if self._check_condition(ev, portfolios):
                    should_apply = True
                    ev.triggered = True

            if should_apply:
                result = self._apply(ev, portfolios, agents, market_engine, relation_graph, current_tick)
                fired.append({"name": ev.name, "type": ev.event_type, "tick": current_tick, "effects": result})
                if ev.event_type == "trend" and ev.remaining > 0:
                    ev.remaining -= 1

        return fired

    def _check_condition(self, ev: WorldEventDef, portfolios: Dict) -> bool:
        if not ev.condition_resource or ev.condition_threshold is None:
            return False
        op = ev.condition_operator or "lt"
        res = ev.condition_resource
        thresh = ev.condition_threshold
        values = [p.get(res, 0) for p in portfolios.values()]
        if not values:
            return False

        def _test(v):
            if op == "lt": return v < thresh
            if op == "gt": return v > thresh
            if op == "le": return v <= thresh
            if op == "ge": return v >= thresh
            if op == "eq": return v == thresh
            return False

        if ev.condition_scope == "all_agents":
            return all(_test(v) for v in values)
        return any(_test(v) for v in values)

    def _resolve_targets(self, targets, agents: Dict) -> List[str]:
        if targets == "all":
            return list(agents.keys())
        if isinstance(targets, list):
            return [t for t in targets if t in agents]
        if isinstance(targets, str) and targets in agents:
            return [targets]
        return []

    def _apply(self, ev: WorldEventDef, portfolios: Dict, agents: Dict,
               market_engine: "MarketEngine", relation_graph: "RelationGraph",
               tick: int) -> List[str]:
        eff = ev.effect
        results = []
        target_ids = self._resolve_targets(eff.targets, agents)

        # Portfolio resource delta / rate
        if eff.resource:
            amount = eff.delta if ev.event_type in ("shock", "conditional") else eff.rate
            if amount is not None:
                for aid in target_ids:
                    port = portfolios.get(aid, {})
                    port[eff.resource] = port.get(eff.resource, 0) + amount
                    results.append(f"{aid}.{eff.resource} {'+' if amount >= 0 else ''}{amount}")

        # Market price effect
        if eff.market and market_engine and eff.market in market_engine.markets:
            m = market_engine.markets[eff.market]
            if eff.price_set is not None:
                m.current_price = eff.price_set
                m.price_history.append((tick, m.current_price))
                results.append(f"market.{eff.market}.price_set={eff.price_set}")
            elif eff.price_multiplier is not None:
                m.current_price = round(m.current_price * eff.price_multiplier, 8)
                cfg = m.config
                m.current_price = max(cfg.get("min_price", 0), min(cfg.get("max_price", float("inf")), m.current_price))
                m.price_history.append((tick, m.current_price))
                results.append(f"market.{eff.market}.price×{eff.price_multiplier}={m.current_price}")

        # Trust effect
        if eff.trust_source and eff.trust_delta and relation_graph:
            src = eff.trust_source
            for tgt in target_ids:
                if tgt != src:
                    relation_graph.update_trust(src, tgt, eff.trust_delta)
                    results.append(f"trust.{src}->{tgt} {'+' if eff.trust_delta >= 0 else ''}{eff.trust_delta}")

        # Contagion: propagate resource delta through trust graph to non-target neighbors
        if eff.contagion_rate > 0.0 and eff.resource and relation_graph:
            base_amount = (eff.delta if ev.event_type in ("shock", "conditional") else eff.rate) or 0.0
            for aid in target_ids:
                for rec in relation_graph.get_relations_for(aid):
                    neighbor = rec.target
                    if neighbor in portfolios and neighbor not in target_ids:
                        spread = base_amount * eff.contagion_rate * rec.trust
                        portfolios[neighbor][eff.resource] = (
                            portfolios[neighbor].get(eff.resource, 0) + spread
                        )
                        results.append(
                            f"contagion.{aid}->{neighbor}.{eff.resource} "
                            f"{'+' if spread >= 0 else ''}{spread:.4f}"
                        )

        return results
