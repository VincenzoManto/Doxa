import os

import autogen
from typing import Dict, List, Optional


_LOCAL_ENV_CACHE: Optional[Dict[str, str]] = None


def _read_local_env_file() -> Dict[str, str]:
    """Load simple KEY=VALUE pairs from server/.env once.
    This keeps local development working without requiring the caller to export env vars.
    """
    global _LOCAL_ENV_CACHE
    if _LOCAL_ENV_CACHE is not None:
        return _LOCAL_ENV_CACHE
    values: Dict[str, str] = {}
    # search .env in current and parent directories
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if not os.path.exists(env_path):
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    if os.path.exists(env_path):
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
    return os.environ.get(name) or _read_local_env_file().get(name, default)
    

# ==========================================
# 2. DOXA AGENT
# ==========================================
class DoxaAgent(autogen.ConversableAgent):
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
        model = config.get('model', config.get('model_name', 'llama3.1:8b'))
        if provider == 'openai':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "openai",
                    "api_key": config.get('api_key', os.environ.get('OPENAI_API_KEY', '')),
                    "base_url": config.get('base_url', 'https://api.openai.com/v1'),
                }],
                "temperature": 0.1,
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
                "temperature": 0.1,
            }
        
        elif provider == 'grok':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "grok",
                    "api_key": config.get('api_key', os.environ.get('GROK_API_KEY', '')),
                    "base_url": config.get('base_url', 'https://api.grok.x.ai/v1'),
                }],
                "temperature": 0.1,
            }
        else:
            llm_config = {
                "config_list": [{
                    "model": model,
                    "base_url": "http://localhost:11434/v1",
                    "api_type": "openai",
                    "api_key": "ollama",
                    "price": [0,0]
                }],
                "temperature": 0.1,
            }
        print(llm_config)

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
        portfolio = self.env.portfolios[self.agent_id]
        other_agents = [a for a in self.env.portfolios.keys() if a != self.agent_id]
        
        # Recupera trade pendenti per questo agente
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
"""
        new_messages = [{"role": "system", "content": state_prompt}]
        for m in messages:
            if m.get("role") != "system": new_messages.append(m)
        return new_messages

    def _register_standard_tools(self):
        can_trade = self.config.get('can_trade', True)
        can_think = self.config.get('can_think', True)
        can_chat = self.config.get('can_chat', True)
        can_rag = self.can_rag
        trading_mode = self.config.get('trading_mode', 'otc')   # otc | lob | both
        # 1. Messaging
        def send_message(recipient: str, message: str) -> str:
            """Send a private message to another agent."""
            if recipient not in self.env.agents: return "Error: Recipient not found."
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
