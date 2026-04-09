from typing import Dict, List
from copy import deepcopy
from market.MarketEngine import MarketEngine
from relations.RelationGraph import RelationGraph
from events.WorldEventEffect import WorldEventDef, WorldEventEffect

def _parse_world_event(raw: Dict) -> WorldEventDef:
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
