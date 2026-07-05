import pytest

from engine.MacroTracker import MacroTracker


def test_system_panic_defaults_to_literal_panic_resource():
    """Backward compatibility: existing scenarios never set panic_resource,
    so the metric must keep reading the literal 'panic' key."""
    tracker = MacroTracker()
    portfolios = {
        "alice": {"credits": 10.0, "panic": 0.2},
        "bob": {"credits": 5.0, "panic": 0.6},
    }

    snap = tracker.compute(portfolios, market_engine=None, tick=1)

    assert snap["system_panic"] == pytest.approx(0.4)


def test_system_panic_reads_configured_panic_resource():
    """A scenario in another domain (e.g. clinical/behavioral-health) can
    point panic_resource at a differently-named bounded resource and still
    get the system_panic aggregate under the same output key."""
    tracker = MacroTracker(panic_resource="relapse_risk")
    portfolios = {
        "patient_1": {"self_efficacy": 40.0, "relapse_risk": 0.3, "panic": 0.9},
        "patient_2": {"self_efficacy": 22.0, "relapse_risk": 0.7},
    }

    snap = tracker.compute(portfolios, market_engine=None, tick=1)

    # Averages relapse_risk (0.3, 0.7) -> 0.5, and ignores the stray literal
    # "panic" key entirely since panic_resource has been redirected.
    assert snap["system_panic"] == pytest.approx(0.5)


def test_system_panic_is_zero_when_no_agent_holds_the_panic_resource():
    tracker = MacroTracker(panic_resource="relapse_risk")
    portfolios = {"alice": {"credits": 10.0}}

    snap = tracker.compute(portfolios, market_engine=None, tick=1)

    assert snap["system_panic"] == 0.0
