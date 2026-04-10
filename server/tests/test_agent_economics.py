import unittest

from engine.agents.AgentEconomics import AgentEconomics


class AgentEconomicsTests(unittest.TestCase):
    def test_compute_utility_uses_reference_prices_when_provided(self):
        economics = AgentEconomics()
        portfolio = {"credits": 10.0, "gold": 2.0, "panic": 0.5}

        utility = economics.compute_utility(
            portfolio,
            {"credits": 1.0, "gold": 5.0, "panic": 0.0},
        )

        self.assertEqual(utility, 20.0)

    def test_simulate_portfolio_delta_does_not_mutate_original(self):
        economics = AgentEconomics()
        portfolio = {"credits": 10.0, "gold": 2.0}

        simulated = economics.simulate_portfolio_delta(portfolio, {"gold": -1.0, "corn": 4.0})

        self.assertEqual(portfolio, {"credits": 10.0, "gold": 2.0})
        self.assertEqual(simulated, {"credits": 10.0, "gold": 1.0, "corn": 4.0})

    def test_evaluate_trade_utility_returns_positive_delta_for_favorable_trade(self):
        economics = AgentEconomics()
        portfolio = {"credits": 10.0, "gold": 1.0}
        reference_prices = {"credits": 1.0, "gold": 5.0, "corn": 2.5}

        delta = economics.evaluate_trade_utility(
            portfolio,
            {"credits": 4.0},
            {"corn": 3.0},
            reference_prices,
        )

        self.assertEqual(delta, 3.5)

    def test_evaluate_order_utility_handles_bid_and_ask(self):
        economics = AgentEconomics()
        portfolio = {"credits": 20.0, "gold": 4.0}
        reference_prices = {"credits": 1.0, "gold": 6.0}

        bid_delta = economics.evaluate_order_utility(
            portfolio,
            "bid",
            "gold",
            quantity=2.0,
            price=5.0,
            reference_prices=reference_prices,
        )
        ask_delta = economics.evaluate_order_utility(
            portfolio,
            "ask",
            "gold",
            quantity=2.0,
            price=7.0,
            reference_prices=reference_prices,
        )

        self.assertEqual(bid_delta, 2.0)
        self.assertEqual(ask_delta, 2.0)

    def test_evaluate_order_utility_rejects_invalid_side(self):
        economics = AgentEconomics()

        with self.assertRaises(ValueError):
            economics.evaluate_order_utility({"credits": 10.0}, "hold", "gold", 1.0, 5.0)


if __name__ == "__main__":
    unittest.main()