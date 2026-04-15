from events.WorldEventScheduler import WorldEventScheduler  # type: ignore[import]
from market.MarketEngine import MarketEngine  # type: ignore[import]
from relations.RelationGraph import RelationGraph  # type: ignore[import]


def _make_market_engine():
    return MarketEngine(
        [
            {
                "resource": "gold",
                "currency": "credits",
                "initial_price": 10.0,
                "min_price": 1.0,
                "max_price": 100.0,
                "clearing": "per_step",
            }
        ]
    )


def test_shock_event_applies_delta_once():
    scheduler = WorldEventScheduler(
        [
            {
                "name": "panic_spike",
                "type": "shock",
                "trigger": {"tick": 2},
                "effect": {"targets": "all", "resource": "panic", "delta": 0.2},
            }
        ]
    )
    portfolios = {"alice": {"panic": 0.0}}
    agents = {"alice": object()}

    assert scheduler.tick(portfolios, agents, None, None, None, 1) == []
    fired = scheduler.tick(portfolios, agents, None, None, None, 2)
    assert len(fired) == 1
    assert portfolios["alice"]["panic"] == 0.2
    assert scheduler.tick(portfolios, agents, None, None, None, 3) == []
    assert portfolios["alice"]["panic"] == 0.2


def test_trend_event_applies_rate_for_full_duration():
    scheduler = WorldEventScheduler(
        [
            {
                "name": "relief_flow",
                "type": "trend",
                "trigger": {"tick": 1},
                "duration": 3,
                "effect": {"targets": "all", "resource": "food", "rate": 1.5},
            }
        ]
    )
    portfolios = {"alice": {"food": 0.0}, "bob": {"food": 1.0}}
    agents = {"alice": object(), "bob": object()}

    assert len(scheduler.tick(portfolios, agents, None, None, None, 1)) == 1
    assert len(scheduler.tick(portfolios, agents, None, None, None, 2)) == 1
    assert len(scheduler.tick(portfolios, agents, None, None, None, 3)) == 1
    assert scheduler.tick(portfolios, agents, None, None, None, 4) == []
    assert portfolios["alice"]["food"] == 4.5
    assert portfolios["bob"]["food"] == 5.5


def test_conditional_event_updates_market_and_trust_once():
    scheduler = WorldEventScheduler(
        [
            {
                "name": "ceasefire",
                "type": "conditional",
                "trigger": {
                    "condition": {
                        "resource": "panic",
                        "operator": "gt",
                        "threshold": 0.5,
                        "scope": "any_agent",
                    }
                },
                "effect": {
                    "targets": ["beta"],
                    "market": "gold",
                    "price_multiplier": 1.5,
                    "trust_source": "alpha",
                    "trust_delta": 0.2,
                },
            }
        ]
    )
    portfolios = {"alpha": {"panic": 0.1}, "beta": {"panic": 0.7}}
    agents = {"alpha": object(), "beta": object()}
    market_engine = _make_market_engine()
    relation_graph = RelationGraph()
    relation_graph.init_from_yaml(
        [{"source": "alpha", "target": "beta", "trust": 0.5, "type": "neutral"}],
        ["alpha", "beta"],
    )

    fired = scheduler.tick(portfolios, agents, market_engine, relation_graph, None, 1)
    assert len(fired) == 1
    assert market_engine.get_price("gold") == 15.0
    assert relation_graph.get_trust("alpha", "beta") == 0.7

    assert scheduler.tick(portfolios, agents, market_engine, relation_graph, None, 2) == []
    assert market_engine.get_price("gold") == 15.0