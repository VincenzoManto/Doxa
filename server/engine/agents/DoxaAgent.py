"""
agents.DoxaAgent
----------------
The core LLM-backed agent class for the Doxa simulation.

Each active actor in a simulation run is represented by exactly one
``DoxaAgent`` instance.  It subclasses AutoGen's ``ConversableAgent``
so the full tool-calling loop (LLM generates a tool call \u2192 execution
layer runs it \u2192 result injected back into context) works out of the box.

Architecture
~~~~~~~~~~~~
* **Provider / model selection** \u2014 ``__init__`` reads ``actor.provider`` and
  ``actor.model_name`` from the YAML config and builds the matching
  ``llm_config`` dict.  Supported providers: ``openai``, ``google``
  (Gemini via the OpenAI-compat endpoint), ``grok``, ``ollama``.

* **State injection** \u2014 ``_inject_state_hook`` is registered as a
  ``process_all_messages_before_reply`` hook; it prepend a system message
  on every LLM call with the agent's current portfolio, pending trades,
  relation graph, market prices, economics metrics, kill & victory
  conditions, and active tool set.

* **Tool registration** \u2014 Two tool categories are registered:
  1. *Standard tools* (``_register_standard_tools``): messaging, OTC
     trades, LOB orders, market queries, RAG memory, leader delegation.
     Which tools are available depends on ``trading_mode``, ``can_trade``,
     ``can_think``, ``can_chat``, ``can_rag``, and ``leader`` flags.
  2. *Custom operations* (``_register_custom_ops``): operations declared
     under ``global_rules.operations`` and ``actor.operations`` in YAML
     are wrapped into callable LLM tools automatically.

* **API key resolution** \u2014 ``_resolve_secret()`` looks for a key in
  environment variables first, then in a ``.env`` file located in the
  server root (walking up the directory tree up to two levels).

* **RAG memory** \u2014 each agent has an optional persistent
  ``ChromaDBVectorMemory`` (``save_knowledge`` / ``query_knowledge`` tools).
  Memory is stored in a temporary directory and persists across epochs
  within a single process run.
"""
import os
from copy import deepcopy
import autogen
from typing import Dict, List, Optional


_LOCAL_ENV_CACHE: Optional[Dict[str, str]] = None


def _candidate_env_paths() -> List[str]:
    """Return env-file lookup candidates from closest to project root."""
    env_override = os.environ.get("DOXA_ENV_FILE")
    if env_override:
        return [env_override]

    current_dir = os.path.abspath(os.path.dirname(__file__))
    candidates: List[str] = []
    for _ in range(5):
        candidates.append(os.path.join(current_dir, ".env"))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
    return candidates


def _read_local_env_file() -> Dict[str, str]:
    """Load simple KEY=VALUE pairs from server/.env once and cache the result.

    This enables LLM API keys to be stored in a local ``.env`` file during
    development without having to export them as shell environment variables.
    The file is searched from the current directory up to the repository root;
    the first match wins. An explicit ``DOXA_ENV_FILE`` path overrides this.
    """
    global _LOCAL_ENV_CACHE
    if _LOCAL_ENV_CACHE is not None:
        return _LOCAL_ENV_CACHE
    values: Dict[str, str] = {}
    env_path = next((path for path in _candidate_env_paths() if os.path.exists(path)), None)
    if env_path:
        try:
            with open(env_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        values[key] = value
        except OSError:
            pass
    _LOCAL_ENV_CACHE = values
    return values



def _resolve_secret(name: str, default: str = "") -> str:
    """Return the value of secret *name*, checking ``os.environ`` first,
    then the cached ``.env`` file, and finally returning *default*."""
    return os.environ.get(name) or _read_local_env_file().get(name, default)


def _resolve_ollama_base_url(config: Dict) -> str:
    """Resolve the Ollama endpoint URL from actor config or environment."""
    return config.get('base_url') or os.environ.get('OLLAMA_URL', 'http://localhost:11434/v1')


def _resolve_claude_api_key(config: Dict) -> str:
    """Resolve the Claude/Anthropic API key from actor config or environment."""
    return config.get('api_key') or _resolve_secret('CLAUDE_API_KEY', _resolve_secret('ANTHROPIC_API_KEY', ''))


def _resolve_claude_base_url(config: Dict) -> str:
    """Resolve the Claude/Anthropic endpoint URL from actor config or environment."""
    return config.get('base_url') or os.environ.get('CLAUDE_URL', 'https://api.anthropic.com/v1')


def _resolve_agent_temperature(config: Dict) -> float:
    """Resolve the effective LLM temperature for an agent config.

    Supported YAML fields:
    * ``temperature``: direct control in [0, 2]
    * ``irrationality``: semantic control in [0, 1], mapped to [0.1, 1.3]

    ``temperature`` takes precedence when both are provided.
    """
    explicit_temperature = config.get("temperature")
    if explicit_temperature is not None:
        return float(explicit_temperature)

    irrationality = config.get("irrationality")
    if irrationality is not None:
        return 0.1 + (float(irrationality) * 1.2)

    return 0.1
    

# ==========================================
# 2. DOXA AGENT
# ==========================================
class DoxaAgent(autogen.ConversableAgent):
    """An AutoGen ConversableAgent that acts as an economic agent in the simulation.

    At every step the engine calls ``generate_reply()`` on this agent;
    the LLM either emits a tool-call (which the engine or AutoGen runtime
    executes) or a plain-text thought (logged but not acted upon).

    Constructor args:
        agent_id: Unique string identifier (matches ``actor.id`` in YAML).
        config:   The raw actor config dict from the parsed YAML.
        env:      The shared ``SimulationEnvironment`` instance.
    """
    def __init__(self, agent_id, config, env):
        self.agent_id = agent_id
        self.env = env
        self.logger = env.log
        self.persona = config.get('persona', "")
        self.config = config
        self.is_leader = config.get('leader', False)
        self.sub_agents = []  # Popolato se leader
        self.can_rag = config.get('can_rag', True)
        # define constraints as sum of global and local (they are dict)
        self.constraints = {**env.global_rules.get('constraints', {}), **config.get('constraints', {})}
        # Provider/model selection logic
        provider = config.get('provider', 'ollama').lower()
        model = config.get('model', config.get('model_name'))
        if model is None:
            if provider in {'claude', 'anthropic'}:
                model = 'claude-3.5-std'
            else:
                model = 'llama3.1:8b'
        temperature = _resolve_agent_temperature(config)
        if provider == 'openai':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "openai",
                    "api_key": config.get('api_key', os.environ.get('OPENAI_API_KEY', '')),
                    "base_url": config.get('base_url', 'https://api.openai.com/v1'),
                }],
                "temperature": temperature,
            }
        elif provider == 'google':
            google_api_key = config.get('api_key') or _resolve_secret('GOOGLE_API_KEY', '')
            print(f"Using Google API key: {'set' if google_api_key else 'NOT SET'}")
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "openai",
                    "api_key": google_api_key,
                    "base_url": config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta/openai/'),
                }],
                "temperature": temperature,
            }
        elif provider == 'grok':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "grok",
                    "api_key": config.get('api_key', os.environ.get('GROK_API_KEY', '')),
                    "base_url": config.get('base_url', 'https://api.grok.x.ai/v1'),
                }],
                "temperature": temperature,
            }
        elif provider in {'claude', 'anthropic'}:
            claude_api_key = _resolve_claude_api_key(config)
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "anthropic",
                    "api_key": claude_api_key,
                    "base_url": _resolve_claude_base_url(config),
                }],
                "temperature": temperature,
            }
        else:
            llm_config = {
                "config_list": [{
                    "model": model,
                    "base_url": _resolve_ollama_base_url(config),
                    "api_type": "openai",
                    "api_key": "ollama",
                    "price": [0,0]
                }],
                "temperature": temperature,
            }

        super().__init__(
            name=agent_id,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )
        self.register_hook(hookable_method="process_all_messages_before_reply", hook=self._inject_state_hook)
        self._register_standard_tools()
        self._register_custom_ops(config, env.global_rules)
        # Se leader, popola sub_agents (solo id, popolamento reale dopo reset)
        if self.is_leader:
            self.sub_agents = config.get('sub_agents', [])

    def _inject_state_hook(self, messages: List[Dict]):
        """AutoGen message hook — prepends a fresh system-state message before every LLM call.

        Builds a prompt block containing:
        * Current portfolio
        * Other agent IDs (potential trade/message targets)
        * Pending OTC trade offers addressed to this agent
        * Outbound trust/type summary from the relation graph
        * Market best-bid / best-ask for each configured instrument
        * Utility value, risk profile, and liquidity advisories (if economics configured)
        * Per-resource price expectations (EWA)
        * Kill / victory conditions
        * Active trading mode description
        * Binding portfolio constraints
        """
        # Take a consistent snapshot of mutable shared state under the env lock so
        # concurrent agent turns in parallel execution mode don't race on dict reads.
        _env_lock = getattr(self.env, '_lock', None)
        if _env_lock is not None:
            with _env_lock:
                portfolio = dict(self.env.portfolios.get(self.agent_id, {}))
                other_agents = [a for a in self.env.portfolios.keys() if a != self.agent_id]
                pending = self.env.get_pending_trades_for(self.agent_id)
        else:
            portfolio = dict(self.env.portfolios.get(self.agent_id, {}))
            other_agents = [a for a in self.env.portfolios.keys() if a != self.agent_id]
            pending = self.env.get_pending_trades_for(self.agent_id)
        trade_info = "\nPENDING TRADES:\n" + ("None" if not pending else "\n".join(pending))

        # Relations
        rel_lines = []
        graph = getattr(self.env, 'relation_graph', None)
        if graph:
            for rec in graph.get_relations_for(self.agent_id):
                rel_lines.append(f"  {rec.target}: trust={rec.trust:.2f} ({rec.rel_type})")
        relations_info = "\n=== RELATIONS ===\n" + ("\n".join(rel_lines) if rel_lines else "None")

        # Market prices
        market_lines = []
        me = getattr(self.env, 'market_engine', None)
        market_summary = me.summary() if me else {}
        if market_summary:
            for res, m in market_summary.items():
                bb = m.get('mid_price') if m.get('bids_count', 0) > 0 else None
                ba = None
                book = me.get_order_book(res, depth=1) if me else None
                if book:
                    bb = book['bids'][0]['price'] if book['bids'] else None
                    ba = book['asks'][0]['price'] if book['asks'] else None
                market_lines.append(
                    f"  {res}/{m['currency']}: last={m['current_price']:.4f}"
                    + (f" bid={bb:.4f}" if bb is not None else "")
                    + (f" ask={ba:.4f}" if ba is not None else "")
                )
        market_info = "\n=== MARKETS ===\n" + ("\n".join(market_lines) if market_lines else "None")

        # Economics & objectives context
        econ = getattr(self.env, 'agent_economics_map', {}).get(self.agent_id)
        economics_lines = []
        if econ is not None:
            util_val = econ.compute_utility(portfolio)
            economics_lines.append(
                f"  Utility ({econ.utility_fn}, risk_aversion={econ.risk_aversion:.2f}): "
                f"{util_val:.4f} | Profile: {econ.risk_label()}"
            )
            advisories = econ.liquidity_advisory(portfolio)
            if advisories:
                economics_lines.append("⚠ Liquidity advisory: " + "; ".join(advisories))
        price_exp = getattr(self.env, 'price_expectations', {}).get(self.agent_id, {})
        if price_exp:
            exp_strs = ", ".join(f"{res}={val:.4f}" for res, val in sorted(price_exp.items()))
            economics_lines.append(f"  Price expectations (EWA): {exp_strs}")
        economics_info = "\n=== OBJECTIVES & EXPECTATIONS ===\n" + (
            "\n".join(economics_lines) if economics_lines else "None"
        )

        kill_conditions = self.env.global_rules.get("kill_conditions", []) + self.config.get("kill_conditions", [])
        win_conditions = self.env.global_rules.get("victory_conditions", []) + self.config.get("victory_conditions", [])
        market_mode = ""
        if self.config.get('trading_mode') == 'lob':
            market_mode = "limit order book (use place_buy_order, place_sell_order, get_market_price, get_order_book)"
        elif self.config.get('trading_mode') == 'otc':
            market_mode = "OTC bilateral trades (use make_trade_offer, accept_trade, reject_trade)"
        else:
            market_mode = "both limit order book and OTC bilateral trades. Use what's more convenient."

        constraints = {
            **deepcopy(self.env.global_rules.get("constraints", {})),
            **deepcopy(self.config.get("constraints", {})),
        }

        state_prompt = f"""{self.persona}
=== YOUR STATE ===
ID: {self.agent_id} | PORTFOLIO: {portfolio}
OTHERS: {other_agents}
{trade_info}
{relations_info}
{market_info}
{economics_info}

=== RULES ===
1. You MUST use a tool to act.
2. NO PLAIN TEXT RESPONSES.
3. For tradable resources: you can use {market_mode}. You can evaluate utility of such ops.
4. Only send messages or offers to agent IDs listed in OTHERS.
{ f"You'll die if: {kill_conditions}" if kill_conditions else "" }
{ f"You'll win if: {win_conditions}" if win_conditions else "" }
{ f"Constraints: {constraints}" if constraints else "" }
"""
        new_messages = [{"role": "system", "content": state_prompt}]
        for m in messages:
            if m.get("role") != "system": new_messages.append(m)
        return new_messages

    def _register_standard_tools(self):
        """Register all built-in agent tools based on capability flags.

        Tools are gated by these actor config flags:

        * ``can_trade`` (default ``True``) + ``trading_mode`` (``otc`` | ``lob`` | ``both``)
          — enables OTC trade tools (make_trade_offer, accept_trade, reject_trade)
            and/or LOB tools (place_buy_order, place_sell_order,
            place_market_buy_order, place_market_sell_order, cancel_order,
            get_market_price, get_order_book).
        * ``can_think`` (default ``True``) — enables the ``think`` tool.
        * ``can_chat``  (default ``True``) — enables ``send_message`` and ``broadcast``.
        * ``can_rag``   (inferred from actor config, default ``True``) — enables
          ``save_knowledge`` and ``query_knowledge``.
        * ``leader``    (default ``False``) — enables ``assign_task``.

        Every tool is registered under the name ``op_<function_name>`` so the
        engine’s fallback dispatcher can recognise it.
        """
        can_trade = self.config.get('can_trade', True)
        can_think = self.config.get('can_think', True)
        can_chat = self.config.get('can_chat', True)
        can_rag = self.can_rag
        trading_mode = self.config.get('trading_mode', 'otc')   # otc | lob | both
        def build_reference_prices() -> Dict[str, float]:
            prices: Dict[str, float] = {"credits": 1.0, "panic": 0.0}
            me = getattr(self.env, 'market_engine', None)
            if me:
                for resource_name, market in me.markets.items():
                    prices[resource_name] = float(market.current_price)
                    prices.setdefault(market.currency, 1.0)
            for resource_name, expected_price in getattr(self.env, 'price_expectations', {}).get(self.agent_id, {}).items():
                prices[resource_name] = float(expected_price)
            return prices

        def format_utility_report(label: str, simulated_portfolio: Dict[str, float], delta_value: float) -> str:
            econ = getattr(self.env, 'agent_economics_map', {}).get(self.agent_id)
            if econ is None:
                return "FAILED: No economics profile configured."
            reference_prices = build_reference_prices()
            current_portfolio = self.env.portfolios[self.agent_id]
            current_utility = econ.compute_utility(current_portfolio, reference_prices)
            projected_utility = econ.compute_utility(simulated_portfolio, reference_prices)
            current_wealth = econ.compute_wealth(current_portfolio, reference_prices)
            projected_wealth = econ.compute_wealth(simulated_portfolio, reference_prices)
            advisories = econ.liquidity_advisory(simulated_portfolio)
            lines = [
                f"=== UTILITY CHECK: {label} ===",
                f"Current utility: {current_utility:.6f}",
                f"Projected utility: {projected_utility:.6f}",
                f"Utility delta: {delta_value:+.6f}",
                f"Current wealth proxy: {current_wealth:.6f}",
                f"Projected wealth proxy: {projected_wealth:.6f}",
            ]
            if advisories:
                lines.append("Projected liquidity advisory: " + "; ".join(advisories))
            return "\n".join(lines)

        # 1. Messaging
        def send_message(recipient: str, message: str) -> str:
            """Send a private message to another agent."""
            if recipient not in self.env.agents:
                live_agents = ", ".join(sorted(a for a in self.env.agents.keys() if a != self.agent_id)) or "none"
                return f"Error: Recipient '{recipient}' not found. Live counterparts: {live_agents}."
            self.logger.print_communication(self.agent_id, message, target=recipient)
            self.send(f"[PRIVATE] {message}", self.env.agents[recipient], request_reply=False, silent=True)
            return "Message sent."
        def broadcast(message: str) -> str:
            """Broadcast a message to all other agents."""
            self.logger.print_communication(self.agent_id, message, target="PUBLIC")
            rel_dyn = self.env.global_rules.get('relation_dynamics', {})
            broadcast_delta = rel_dyn.get('on_broadcast', {}).get('trust_delta', 0.01)
            graph = getattr(self.env, 'relation_graph', None)
            for name, agent in self.env.agents.items():
                if name != self.agent_id:
                    self.send(f"[PUBLIC] {self.agent_id}: {message}", agent, request_reply=False, silent=True)
                    if graph and broadcast_delta:
                        graph.update_trust(self.agent_id, name, broadcast_delta)
            return "Broadcast sent."
        # 2. Trade (OTC)
        def make_trade_offer(target: str, give_res: str, give_qty: int, take_res: str, take_qty: int) -> str:
            """Propose a trade to target: give_qty of give_res for take_qty of take_res."""
            res = self.env.create_trade(self.agent_id, target, give_res, give_qty, take_res, take_qty)
            self.logger.print_trade(self.agent_id, target, give_res, give_qty, take_res, take_qty, res)
            return res
        def accept_trade(trade_id: str) -> str:
            """Accept a pending trade offer by its ID."""
            trade = self.env.pending_trades.get(trade_id)
            res = self.env.resolve_trade(self.agent_id, trade_id, True)
            if trade:
                g_res, g_qty = list(trade['give'].items())[0]
                t_res, t_qty = list(trade['take'].items())[0]
                self.logger.print_trade(trade['from_agent'], trade['to_agent'], g_res, g_qty, t_res, t_qty, f"ACCEPTED: {res}")
            else:
                self.logger.print_action(self.agent_id, "accept_trade", trade_id, res)
            return res
        def reject_trade(trade_id: str) -> str:
            """Reject a pending trade offer by its ID."""
            trade = self.env.pending_trades.get(trade_id)
            res = self.env.resolve_trade(self.agent_id, trade_id, False)
            if trade:
                g_res, g_qty = list(trade['give'].items())[0]
                t_res, t_qty = list(trade['take'].items())[0]
                self.logger.print_trade(trade['from_agent'], trade['to_agent'], g_res, g_qty, t_res, t_qty, f"REJECTED: {res}")
            else:
                self.logger.print_action(self.agent_id, "reject_trade", trade_id, res)
            return res
        def evaluate_trade_utility(give_res: str, give_qty: float, take_res: str, take_qty: float) -> str:
            """Estimate utility change for a hypothetical OTC trade without executing it."""
            econ = getattr(self.env, 'agent_economics_map', {}).get(self.agent_id)
            if econ is None:
                return "FAILED: No economics profile configured."
            portfolio = self.env.portfolios[self.agent_id]
            reference_prices = build_reference_prices()
            simulated_portfolio = econ.simulate_portfolio_delta(
                portfolio,
                {
                    give_res: -float(give_qty),
                    take_res: float(take_qty),
                },
            )
            delta_value = econ.evaluate_trade_utility(
                portfolio,
                {give_res: float(give_qty)},
                {take_res: float(take_qty)},
                reference_prices,
            )
            return format_utility_report(
                f"give {give_qty} {give_res} / take {take_qty} {take_res}",
                simulated_portfolio,
                delta_value,
            )
        def evaluate_order_utility(side: str, resource: str, quantity: float, price: float, currency: str = "credits") -> str:
            """Estimate utility change if an order fully executes at the given price without placing it."""
            # Accept natural-language aliases so the LLM can use 'buy'/'sell'
            side = {"buy": "bid", "sell": "ask"}.get(side.lower(), side.lower())
            econ = getattr(self.env, 'agent_economics_map', {}).get(self.agent_id)
            if econ is None:
                return "FAILED: No economics profile configured."
            portfolio = self.env.portfolios[self.agent_id]
            reference_prices = build_reference_prices()
            qty = float(quantity)
            px = float(price)
            if side == "bid":
                simulated_portfolio = econ.simulate_portfolio_delta(
                    portfolio,
                    {resource: qty, currency: -(qty * px)},
                )
            elif side == "ask":
                simulated_portfolio = econ.simulate_portfolio_delta(
                    portfolio,
                    {resource: -qty, currency: qty * px},
                )
            else:
                return f"FAILED: Unsupported order side '{side}'. Use 'bid' or 'ask'."
            try:
                delta_value = econ.evaluate_order_utility(
                    portfolio,
                    side,
                    resource,
                    qty,
                    px,
                    currency,
                    reference_prices,
                )
            except ValueError as exc:
                return f"FAILED: {exc}"
            return format_utility_report(
                f"{side} {qty} {resource} @ {px} {currency}",
                simulated_portfolio,
                delta_value,
            )
        # 3. LOB market tools
        def place_buy_order(resource: str, quantity: float, max_price: float) -> str:
            """Place a limit buy order on the market for the given resource at max_price per unit."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            tick = getattr(self.env, '_current_tick', 0)
            return me.add_order(self.agent_id, "bid", resource, quantity, max_price, self.env.portfolios, tick)
        def place_sell_order(resource: str, quantity: float, min_price: float) -> str:
            """Place a limit sell order on the market for the given resource at min_price per unit."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            tick = getattr(self.env, '_current_tick', 0)
            return me.add_order(self.agent_id, "ask", resource, quantity, min_price, self.env.portfolios, tick)
        def cancel_order(order_id: str) -> str:
            """Cancel one of your open market orders by its ID."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            return me.cancel_order(order_id, self.agent_id, self.env.portfolios)
        def get_market_price(resource: str) -> str:
            """Get the current last-trade price for a resource on the exchange."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            p = me.get_price(resource)
            return f"Current price for {resource}: {p}" if p is not None else f"FAILED: No market for {resource}."
        def get_order_book(resource: str) -> str:
            """Get the top-of-book bids and asks for a resource (depth 5)."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            book = me.get_order_book(resource, depth=5)
            if not book:
                return f"FAILED: No market for {resource}."
            lines = [f"=== ORDER BOOK: {resource}/{book['currency']} (last={book['last_price']:.4f}) ==="]
            bid_line = ", ".join(f"{e['qty']}@{e['price']}" for e in book["bids"])
            ask_line = ", ".join(f"{e['qty']}@{e['price']}" for e in book["asks"])
            lines.append("BIDS: " + (bid_line or "empty"))
            lines.append("ASKS: " + (ask_line or "empty"))
            return "\n".join(lines)
        def place_market_buy_order(resource: str, quantity: float) -> str:
            """Place a market buy order that sweeps best asks at current price (+slip). Expires next tick if unmatched."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            tick = getattr(self.env, '_current_tick', 0)
            return me.add_market_order(self.agent_id, "bid", resource, quantity, self.env.portfolios, tick)
        def place_market_sell_order(resource: str, quantity: float) -> str:
            """Place a market sell order that sweeps best bids at current price (-slip). Expires next tick if unmatched."""
            me = getattr(self.env, 'market_engine', None)
            if not me:
                return "FAILED: No market engine configured."
            tick = getattr(self.env, '_current_tick', 0)
            return me.add_market_order(self.agent_id, "ask", resource, quantity, self.env.portfolios, tick)
        def think(thought: str) -> str:
            self.logger.print_think(self.agent_id, thought)
            return "Thought logged."
        def save_knowledge(knowledge: str) -> str:
            """Save a piece of knowledge to your RAG memory."""
            if not can_rag:
                return "RAG disabled for this agent."
            res = self.env.save_memory_rag(self.agent_id, knowledge)
            return res
        def query_knowledge(query: str, top_k: int = 3) -> str:
            """Query your RAG memory for relevant knowledge."""
            if not can_rag:
                return "RAG disabled for this agent."
            memory = self.env.agent_memories.get(self.agent_id)
            if not memory:
                return "FAILED: No RAG memory for this agent."
            import asyncio
            async def do_query():
                results = await memory.query(query, k=top_k)
                if not results:
                    return "No relevant knowledge found."
                return "\n".join([f"[{i+1}] {mc.content}" for i, mc in enumerate(results)])
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(do_query())
        # Leader tools
        def assign_task(sub_agent: str, task: str) -> str:
            """(Leader only) Assign a task to a sub-agent."""
            if not self.is_leader:
                return "Not a leader agent."
            if sub_agent not in self.env.agents:
                return f"Sub-agent {sub_agent} not found."
            self.send(f"[TASK] {task}", self.env.agents[sub_agent], request_reply=False, silent=True)
            return f"Task sent to {sub_agent}."
        available_tools = []
        available_tools += [evaluate_trade_utility, evaluate_order_utility]
        if can_trade and trading_mode in ('otc', 'both'):
            available_tools += [make_trade_offer, accept_trade, reject_trade]
        if can_trade and trading_mode in ('lob', 'both'):
            available_tools += [place_buy_order, place_sell_order,
                                place_market_buy_order, place_market_sell_order,
                                cancel_order, get_market_price, get_order_book]
        if can_think:
            available_tools.append(think)
        if can_chat:
            available_tools += [send_message, broadcast]
        if can_rag:
            available_tools += [save_knowledge, query_knowledge]
        if self.is_leader:
            available_tools.append(assign_task)
        for f in available_tools:
            print(f"Registering tool: {f.__name__} for {f.__doc__}")
            self.register_for_llm(name=f"op_{f.__name__}", description=f"{f.__doc__ or 'Action'}")(f)
            self.register_for_execution(name=f"op_{f.__name__}")(f)

    def _register_custom_ops(self, config, global_rules):
        """Wrap every declared YAML operation into a registered LLM tool.

        Operations from ``global_rules.operations`` and ``actor.operations``
        are merged (actor-level takes precedence on name collision) and each
        is registered as ``op_<name>`` with a description showing its
        input/output resource mapping.

        The generated tool signature is::

            op_<name>(target: str = None, inputMultiplier: float = 1) -> str

        This makes the LLM able to call multi-step operations (e.g. ``mine``
        or ``farm``) and optionally apply them to a *target* agent or scale
        with a multiplier.
        """
        all_ops = {**global_rules.get('operations', {}), **config.get('operations', {})}
        for op_name, op_def in all_ops.items():
            def make_op(name=op_name):
                def op_func(target: str = None, inputMultiplier: float = 1) -> str:
                    print(f"{self.agent_id} is executing operation '{name}' with target '{target}'")
                    res = self.env.execute_operation(self.agent_id, name, target, inputMultiplier)
                    self.logger.print_action(self.agent_id, f"op_{name}", target, res)
                    return res
                return op_func
            
            f = make_op()
            f.__name__ = f"op_{op_name}"
            print(f"Registering operation: {f.__name__} with definition {op_def}")
            self.register_for_llm(name=f.__name__, description=f"Execute {op_name} -> {op_def}")(f)
            self.register_for_execution(name=f.__name__)(f)
