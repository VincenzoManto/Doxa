import yaml
import autogen
import json
import random
from copy import deepcopy
from typing import Annotated, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
# RAG/Memory imports
import os
import tempfile
from autogen_core.memory import MemoryContent, MemoryMimeType
from autogen_ext.memory.chromadb import ChromaDBVectorMemory, PersistentChromaDBVectorMemoryConfig, SentenceTransformerEmbeddingFunctionConfig

# ==========================================
# 1. UI & LOGGING
# ==========================================
class ConsoleLogger:
    @staticmethod
    def print_header(text): print(f"\n\033[96m{'═'*60}\n{text}\n{'═'*60}\033[0m")
    @staticmethod
    def print_epoch(n): print(f"\n\033[1;35m--- EPOCH {n} STARTING ---\033[0m")
    @staticmethod
    def print_step(step): print(f"\n\033[1;37m{'—'*20} GLOBAL STEP {step} {'—'*20}\033[0m")
    @staticmethod
    def print_turn(agent_id): print(f"\n\033[1;33m► TURN: {agent_id.upper()}\033[0m")
    @staticmethod
    def print_think(agent_id, thought): print(f"\033[90m[{agent_id}] THINK: {thought}\033[0m")
    @staticmethod
    def print_action(agent_id, action, target, res):
        color = "\033[32m" if "SUCCESS" in res else "\033[31m"
        tgt = f" on {target}" if target else ""
        print(f"  \033[36m└─ [ACTION] {action}{tgt} -> {color}{res}\033[0m")
    @staticmethod
    def print_delta(before, after):
        for res in set(before.keys()) | set(after.keys()):
            diff = after.get(res, 0) - before.get(res, 0)
            if diff > 0: print(f"     \033[92m▲ +{diff} {res}\033[0m")
            elif diff < 0: print(f"     \033[91m▼ {diff} {res}\033[0m")
    def print(self, text): print(f"\033[90m{text}\033[0m")
# ==========================================
# 2. DOXA AGENT
# ==========================================
class DoxaAgent(autogen.ConversableAgent):
    def __init__(self, agent_id, config, env):
        self.agent_id = agent_id
        self.env = env
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
        if provider == 'ollama':
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
        elif provider == 'openai':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "openai",
                    "api_key": config.get('api_key', os.environ.get('OPENAI_API_KEY', '')),
                    "base_url": config.get('base_url', 'https://api.openai.com/v1'),
                }],
                "temperature": 0.1,
            }
        elif provider == 'genai':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "genai",
                    "api_key": config.get('api_key', os.environ.get('GENAI_API_KEY', '')),
                    "base_url": config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta'),
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
            raise ValueError(f"Unknown provider: {provider}")

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

        state_prompt = f"""{self.persona}
=== YOUR STATE ===
ID: {self.agent_id} | PORTFOLIO: {portfolio}
OTHERS: {other_agents}
{trade_info}

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
        # 1. Messaging
        def send_message(recipient: str, message: str) -> str:
            if recipient not in self.env.agents: return "Error: Recipient not found."
            self.send(f"[PRIVATE] {message}", self.env.agents[recipient], request_reply=False, silent=True)
            return "Message sent."
        def broadcast(message: str) -> str:
            for name, agent in self.env.agents.items():
                if name != self.agent_id:
                    self.send(f"[PUBLIC] {self.agent_id}: {message}", agent, request_reply=False, silent=True)
            return "Broadcast sent."
        # 2. Trade
        def make_trade_offer(target: str, give_res: str, give_qty: int, take_res: str, take_qty: int) -> str:
            res = self.env.create_trade(self.agent_id, target, give_res, give_qty, take_res, take_qty)
            ConsoleLogger.print_action(self.agent_id, "make_trade", target, res)
            return res
        def accept_trade(trade_id: str) -> str:
            res = self.env.resolve_trade(self.agent_id, trade_id, True)
            ConsoleLogger.print_action(self.agent_id, "accept_trade", trade_id, res)
            return res
        def reject_trade(trade_id: str) -> str:
            res = self.env.resolve_trade(self.agent_id, trade_id, False)
            ConsoleLogger.print_action(self.agent_id, "reject_trade", trade_id, res)
            return res
        def think(thought: str) -> str:
            ConsoleLogger.print_think(self.agent_id, thought)
            return "Thought logged."
        def save_knowledge(knowledge: str) -> str:
            """Salva una knowledge string nella memoria RAG dell'agente."""
            if not can_rag:
                return "RAG disabled for this agent."
            res = self.env.save_memory_rag(self.agent_id, knowledge)
            return res
        def query_knowledge(query: str, top_k: int = 3) -> str:
            """Recupera i documenti più rilevanti dalla memoria RAG dell'agente."""
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
            """(Leader only) Assegna un task a un sub-agente."""
            if not self.is_leader:
                return "Not a leader agent."
            if sub_agent not in self.env.agents:
                return f"Sub-agent {sub_agent} not found."
            self.send(f"[TASK] {task}", self.env.agents[sub_agent], request_reply=False, silent=True)
            return f"Task sent to {sub_agent}."
        available_tools = []
        if can_trade:
            available_tools += [make_trade_offer, accept_trade, reject_trade]
        if can_think:
            available_tools.append(think)
        if can_chat:
            available_tools += [send_message, broadcast]
        if can_rag:
            available_tools += [save_knowledge, query_knowledge]
        if self.is_leader:
            available_tools.append(assign_task)
        for f in available_tools:
            self.register_for_llm(name=f.__name__, description=f.__doc__ or "Action")(f)
            self.register_for_execution(name=f.__name__)(f)

    def _register_custom_ops(self, config, global_rules):
        all_ops = {**global_rules.get('operations', {}), **config.get('operations', {})}
        for op_name, op_def in all_ops.items():
            def make_op(name=op_name):
                def op_func(target: str = None, inputMultiplier: float = 1) -> str:
                    print(f"{self.agent_id} is executing operation '{name}' with target '{target}'")
                    res = self.env.execute_operation(self.agent_id, name, target, inputMultiplier)
                    ConsoleLogger.print_action(self.agent_id, f"op_{name}", target, res)
                    return res
                return op_func
            
            f = make_op()
            f.__name__ = f"op_{op_name}"
            print(f"Registering operation: {f.__name__} with definition {op_def}")
            self.register_for_llm(name=f.__name__, description=f"Execute {op_name} -> {op_def}")(f)
            self.register_for_execution(name=f.__name__)(f)

# ==========================================
# 3. ENVIRONMENT
# ==========================================
class SimulationEnvironment:
    def __init__(self, config, log_verbose=True, rag_limit=200):
        import threading
        self.config = config
        self.global_rules = config.get('global_rules', {})
        self.portfolios = {}
        self.agents = {}
        self.pending_trades = {}
        self.trade_counter = 1
        self.log = ConsoleLogger() if log_verbose else None
        # RAG memory per agent (persistente tra i reset)
        self.agent_memories = {}
        self.rag_limit = rag_limit
        self._lock = threading.RLock()

    def reset(self, actors_cfg):
        with self._lock:
            self.portfolios = {}
            self.agents = {}
            self.pending_trades = {}
            # Non ricreare agent_memories se già esistono
            for actor in actors_cfg:
                replicas = actor.get('replicas', 1)
                for i in range(replicas):
                    a_id = f"{actor['id']}_{i+1}" if replicas > 1 else actor['id']
                    self.portfolios[a_id] = deepcopy(actor['initial_portfolio'])
                    self.agents[a_id] = DoxaAgent(a_id, actor, self)
                    # Setup RAG memory solo se non esiste e se can_rag true
                    can_rag = actor.get('can_rag', True)
                    if can_rag and a_id not in self.agent_memories:
                        tmpdir = tempfile.gettempdir()
                        collection_name = f"rag_{a_id}"
                        persistence_path = os.path.join(tmpdir, f"chromadb_{a_id}")
                        memory = ChromaDBVectorMemory(
                            config=PersistentChromaDBVectorMemoryConfig(
                                collection_name=collection_name,
                                persistence_path=persistence_path,
                                k=3,
                                score_threshold=0.4,
                                embedding_function_config=SentenceTransformerEmbeddingFunctionConfig(
                                    model_name="all-MiniLM-L6-v2"
                                ),
                            )
                        )
                        self.agent_memories[a_id] = memory
            # Cleanup memorie non più usate
            to_remove = [aid for aid in self.agent_memories if aid not in self.portfolios]
            for aid in to_remove:
                try:
                    self.agent_memories[aid].close()
                except Exception:
                    pass
                del self.agent_memories[aid]
            # Collega sub-agenti ai leader (dopo creazione agenti)
            for a_id, agent in self.agents.items():
                if getattr(agent, 'is_leader', False):
                    # Se non specificato, tutti tranne se stesso
                    if not agent.sub_agents:
                        agent.sub_agents = [k for k in self.agents if k != a_id]
                    else:
                        # Filtra solo quelli esistenti
                        agent.sub_agents = [k for k in agent.sub_agents if k in self.agents]

    def save_memory_rag(self, agent_id, knowledge):
        """
        Salva una knowledge string nella memoria RAG dell'agente, con pruning FIFO se supera il limite.
        """
        with self._lock:
            memory = self.agent_memories.get(agent_id)
            if not memory:
                return "FAILED: No RAG memory for this agent."
            import asyncio
            async def add_knowledge():
                # Pruning FIFO se superato il limite
                docs = await memory.list()
                if len(docs) >= self.rag_limit:
                    # Rimuovi i più vecchi
                    to_remove = docs[:len(docs)-self.rag_limit+1]
                    for d in to_remove:
                        await memory.delete(d.id)
                if isinstance(knowledge, str):
                    await memory.add(MemoryContent(content=knowledge, mime_type=MemoryMimeType.TEXT))
                elif isinstance(knowledge, list):
                    for k in knowledge:
                        await memory.add(MemoryContent(content=k, mime_type=MemoryMimeType.TEXT))
                else:
                    return "FAILED: Invalid knowledge type."
                return "SUCCESS: Knowledge saved to RAG."
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(add_knowledge())

    def create_trade(self, sender, target, g_res, g_qty, t_res, t_qty):
        with self._lock:
            if target not in self.portfolios: return "FAILED: Target not found"
            if self.portfolios[sender].get(g_res, 0) < g_qty: return f"FAILED: You don't have {g_qty} {g_res}"
            tid = f"TRD_{self.trade_counter}"
            self.trade_counter += 1
            self.pending_trades[tid] = {
                "from": sender, "to": target, 
                "give": {g_res: g_qty}, "take": {t_res: t_qty}
            }
            # Notifica il target tramite AutoGen
            self.agents[sender].send(f"I offered you {tid}: {g_qty} {g_res} for {t_qty} {t_res}", self.agents[target], request_reply=False, silent=True)
            return f"SUCCESS: {tid} created"

    def resolve_trade(self, responder, tid, accept):
        with self._lock:
            trade = self.pending_trades.get(tid)
            if not trade or trade['to'] != responder: return "FAILED: Trade not found or not for you"
            sender = trade['from']
            if not accept:
                del self.pending_trades[tid]
                return "SUCCESS: Trade rejected"
            # Check resources for both
            g_res, g_qty = list(trade['give'].items())[0]
            t_res, t_qty = list(trade['take'].items())[0]
            if self.portfolios[sender].get(g_res, 0) < g_qty: return "FAILED: Sender no longer has resources"
            if self.portfolios[responder].get(t_res, 0) < t_qty: return "FAILED: You don't have resources"
            agentAConstraints = self.agents[sender].constraints
            agentBConstraints = self.agents[responder].constraints
            if agentAConstraints.get(g_res, {}).get('min', float('-inf')) > self.portfolios[sender].get(g_res, 0) - g_qty: return "FAILED: Sender would violate constraints"
            if agentAConstraints.get(g_res, {}).get('max', float('inf')) < self.portfolios[sender].get(g_res, 0) - g_qty: return "FAILED: Sender would violate constraints"
            if agentAConstraints.get(t_res, {}).get('min', float('-inf')) > self.portfolios[sender].get(t_res, 0) + t_qty: return "FAILED: Sender would violate constraints"
            if agentAConstraints.get(t_res, {}).get('max', float('inf')) <  self.portfolios[sender].get(t_res, 0) + t_qty: return "FAILED: Sender would violate constraints"
            if agentBConstraints.get(t_res, {}).get('min', float('-inf')) > self.portfolios[responder].get(t_res, 0) - t_qty: return "FAILED: Responder would violate constraints"
            if agentBConstraints.get(t_res, {}).get('max', float('inf')) <  self.portfolios[responder].get(t_res, 0) - t_qty: return "FAILED: Responder would violate constraints"
            if agentBConstraints.get(g_res, {}).get('min', float('-inf')) > self.portfolios[responder].get(g_res, 0) + g_qty: return "FAILED: Responder would violate constraints"
            if agentBConstraints.get(g_res, {}).get('max', float('inf')) < self.portfolios[responder].get(g_res, 0) + g_qty: return "FAILED: Responder would violate constraints"
            # Rollbackable swap
            self.portfolios[sender][g_res] -= g_qty
            self.portfolios[responder][g_res] += g_qty
            self.portfolios[responder][t_res] -= t_qty
            self.portfolios[sender][t_res] += t_qty
            del self.pending_trades[tid]
            return "SUCCESS: Trade completed"

    def get_pending_trades_for(self, agent_id):
        return [f"- {tid} from {t['from']}: Wants {t['take']} for {t['give']}" 
                for tid, t in self.pending_trades.items() if t['to'] == agent_id]

    def execute_operation(self, actor_id, op_name, target_id=None, multiplier=1):
        with self._lock:
            op = self.global_rules['operations'].get(op_name)
            if not op:
                return f"FAILED: Operation '{op_name}' not found."
            port = self.portfolios[actor_id]
            before = deepcopy(port)
            tbefore = None
            try:
                multiplier = float(multiplier)
            except Exception:
                return f"FAILED: Invalid multiplier value: {multiplier}"
            for r, v in op.get('input', {}).items():
                if port.get(r, 0) < v * multiplier: return f"FAILED: Missing {r}"
            for r, v in op.get('input', {}).items(): port[r] -= v * multiplier
            for r, v in op.get('output', {}).items(): port[r] = port.get(r, 0) + v * multiplier
            if target_id and 'target_impact' in op and target_id in self.portfolios:
                tbefore = deepcopy(self.portfolios[target_id])
                if target_id in self.portfolios:
                    for r, v in op['target_impact'].items():
                        self.portfolios[target_id][r] = self.portfolios[target_id].get(r, 0) + v * multiplier
                if self.log:
                    self.log.print(f"Target delta on {target_id}")
                    self.log.print_delta(tbefore, self.portfolios[target_id])
            rollback = False
            constraints = self.agents[actor_id].constraints
            for r, c in constraints.items():
                if port.get(r, 0) < c.get('min', float('-inf')): rollback = True
                if port.get(r, 0) > c.get('max', float('inf')): rollback = True
            if target_id and target_id in self.portfolios:
                constraints = self.agents[target_id].constraints
                for r, c in constraints.items():
                    if self.portfolios[target_id].get(r, 0) < c.get('min', float('-inf')): rollback = True
                    if self.portfolios[target_id].get(r, 0) > c.get('max', float('inf')): rollback = True
            if rollback == True:
                self.portfolios[actor_id] = before
                if target_id and tbefore is not None:
                    self.portfolios[target_id] = tbefore
                return "FAILED: Constraint violation, operation rolled back."
            if self.log:
                self.log.print(f"Main delta on {actor_id}")
                self.log.print_delta(before, self.portfolios[actor_id])
            return "SUCCESS"

# ==========================================
# 4. ENGINE
# ==========================================
class DoxaEngineV26:
    def godmode(self, action: str, params: dict) -> str:
        """
        API Godmode: permette interventi esterni sulla simulazione.
        action: tipo di intervento, tra:
            - 'inject_resource': aggiungi risorse a un agente
                params: {'agent': 'id', 'resource': 'nome', 'amount': valore}
            - 'set_constraint': modifica vincoli di un agente
                params: {'agent': 'id', 'resource': 'nome', 'min': x, 'max': y}
            - 'set_portfolio': imposta il portafoglio di un agente
                params: {'agent': 'id', 'portfolio': {...}}
            - 'send_message': invia un messaggio come umano a un agente
                params: {'to': 'id', 'message': '...'}
            - 'impersonate_action': esegui un'azione come un agente
                params: {'agent': 'id', 'function': 'nome', 'args': {...}}
        """
        # 1. Inject resource
        if action == 'inject_resource':
            agent = params['agent']
            res = params['resource']
            amount = params['amount']
            if agent not in self.env.portfolios:
                return f"FAILED: Agent {agent} not found."
            self.env.portfolios[agent][res] = self.env.portfolios[agent].get(res, 0) + amount
            return f"SUCCESS: Injected {amount} {res} to {agent}."
        # 2. Set constraint
        elif action == 'set_constraint':
            agent = params['agent']
            res = params['resource']
            minv = params.get('min')
            maxv = params.get('max')
            if agent not in self.env.agents:
                return f"FAILED: Agent {agent} not found."
            if res not in self.env.agents[agent].constraints:
                self.env.agents[agent].constraints[res] = {}
            if minv is not None:
                self.env.agents[agent].constraints[res]['min'] = minv
            if maxv is not None:
                self.env.agents[agent].constraints[res]['max'] = maxv
            return f"SUCCESS: Constraint updated for {agent} {res}."
        # 3. Set portfolio
        elif action == 'set_portfolio':
            agent = params['agent']
            portfolio = params['portfolio']
            if agent not in self.env.portfolios:
                return f"FAILED: Agent {agent} not found."
            self.env.portfolios[agent] = dict(portfolio)
            return f"SUCCESS: Portfolio set for {agent}."
        # 4. Send message as human
        elif action == 'send_message':
            to = params['to']
            msg = params['message']
            if to not in self.env.agents:
                return f"FAILED: Agent {to} not found."
            self.env.agents[to].receive(message=msg, sender="HUMAN", request_reply=False)
            return f"SUCCESS: Message sent to {to}."
        # 5. Impersonate action
        elif action == 'impersonate_action':
            agent = params['agent']
            func = params['function']
            args = params.get('args', {})
            if agent not in self.env.agents:
                return f"FAILED: Agent {agent} not found."
            ag = self.env.agents[agent]
            # Cerca funzione tra quelle registrate
            f = getattr(ag, func, None)
            if not f:
                # Prova tra i tool registrati
                f = ag._function_map.get(func)
            if not f:
                return f"FAILED: Function {func} not found for agent {agent}."
            try:
                res = f(**args) if args else f()
            except Exception as e:
                return f"FAILED: Exception: {e}"
            return f"SUCCESS: {func} executed for {agent}: {res}"
        else:
            return "FAILED: Unknown godmode action."
    def export_data(self, query: dict, format: str = "json"):
        """
        Esporta dati della simulazione secondo la query specificata.
        query: dict con chiavi tra ["agents", "portfolios", "trades", "history", "resources"] e filtri opzionali.
        format: "json" | "csv" | "dict"
        Esempi di query:
            {"agents": True}  # tutti gli agenti
            {"portfolios": ["agent1", "agent2"]}  # solo certi agenti
            {"trades": True}  # tutti i trades
            {"resources": ["score", "token"]}  # solo certe risorse
        """
        import csv
        import io
        result = {}
        if query is None or not isinstance(query, dict) or len(query) == 0:
            query = {"agents": True, "portfolios": True, "trades": True, "history": True}
        # AGENTS
        if query.get("agents"):
            result["agents"] = list(self.env.agents.keys())
        # PORTFOLIOS
        if "portfolios" in query:
            if query["portfolios"] is True:
                result["portfolios"] = {k: dict(v) for k, v in self.env.portfolios.items()}
            elif isinstance(query["portfolios"], list):
                result["portfolios"] = {k: dict(self.env.portfolios[k]) for k in query["portfolios"] if k in self.env.portfolios}
        # TRADES
        if query.get("trades"):
            result["trades"] = dict(self.env.pending_trades)
        # RESOURCES
        if "resources" in query:
            # Estrae risorse da portafogli
            res_names = query["resources"]
            portfolios = self.env.portfolios
            filtered = {}
            for aid, port in portfolios.items():
                filtered[aid] = {r: v for r, v in port.items() if r in res_names}
            result["resources"] = filtered
        # HISTORY (non implementato, placeholder)
        if query.get("history"):
            result["history"] = "Not implemented."
        # Output
        if format == "dict":
            return result
        elif format == "json":
            import json
            return json.dumps(result, indent=2)
        elif format == "csv":
            # Esporta solo portfolios o resources (tabellare)
            output = io.StringIO()
            if "resources" in result:
                # Riga: agent, resource1, resource2, ...
                agents = list(result["resources"].keys())
                res_names = set()
                for v in result["resources"].values():
                    res_names.update(v.keys())
                res_names = sorted(res_names)
                writer = csv.writer(output)
                writer.writerow(["agent"] + res_names)
                for aid in agents:
                    row = [aid] + [result["resources"][aid].get(r, 0) for r in res_names]
                    writer.writerow(row)
            elif "portfolios" in result:
                agents = list(result["portfolios"].keys())
                res_names = set()
                for v in result["portfolios"].values():
                    res_names.update(v.keys())
                res_names = sorted(res_names)
                writer = csv.writer(output)
                writer.writerow(["agent"] + res_names)
                for aid in agents:
                    row = [aid] + [result["portfolios"][aid].get(r, 0) for r in res_names]
                    writer.writerow(row)
            else:
                output.write("CSV export supported only for portfolios/resources.")
            return output.getvalue()
        else:
            return f"Format '{format}' not supported."
        
    def startOllama(self):
        import threading
        import subprocess
        import time

        def run_ollama_serve():
            subprocess.Popen(["ollama", "serve"])

        thread = threading.Thread(target=run_ollama_serve)
        thread.start()
        time.sleep(5)

    def __init__(self, yaml_str, log_verbose=True, rag_limit=200):
        self.raw_config = yaml.safe_load(yaml_str)
        self.env = SimulationEnvironment(self.raw_config, log_verbose=log_verbose, rag_limit=rag_limit)
        self.log = self.env.log
        # Se usa Ollama, avvia il server (solo per provider Ollama, si assume che i modelli siano già importati)
        uses_ollama = any(agent.get('provider', 'ollama').lower() == 'ollama' for agent in self.raw_config.get('actors', []))
        if uses_ollama:
            self.startOllama()

    def run(self):
        epochs = self.raw_config['global_rules'].get('epochs', 1)
        steps = self.raw_config['global_rules'].get('steps', 5)
        mode = self.raw_config['global_rules'].get('execution_mode', 'sequential')

        for e in range(epochs):
            self.log.print_epoch(e + 1)
            self.env.reset(self.raw_config['actors'])
            
            for s in range(steps):
                self.log.print_step(s + 1)
                ids = list(self.env.agents.keys())
                random.shuffle(ids)
                
                if mode == 'sequential':
                    for a_id in ids: self._step_agent(a_id)
                else:
                    with ThreadPoolExecutor() as executor:
                        executor.map(self._step_agent, ids)

    def _step_agent(self, a_id):
        if self.log:
            self.log.print_turn(a_id)
        agent = self.env.agents[a_id]
        reply = agent.generate_reply(messages=agent.chat_messages[agent] + [{"role": "user", "content": "Your turn."}])
        if isinstance(reply, dict) and "tool_calls" in reply:
            for tc in reply["tool_calls"]:
                try:
                    res = agent.execute_function(tc['function'])
                    if isinstance(res, tuple) and res[0] == False:
                        raise Exception(res[1].get('content', 'Unknown error'))
                except Exception as e:
                    ftc = tc['function'] if 'function' in tc else tc
                    if ftc is None or 'name' not in ftc:
                        res = f"FAILED: Tool call missing or malformed."
                        if self.log:
                            self.log.print_action(a_id, "tool_call", None, res)
                        agent.send(str(res), agent, request_reply=False, silent=True)
                        continue
                    name = ftc['name'][3:] if ftc['name'].startswith('op_') else ftc['name']
                    # Parsing robusto parametri
                    args = ftc.get('arguments', {})
                    if not isinstance(args, dict):
                        import json
                        try:
                            args = json.loads(args)
                        except Exception as ex:
                            res = f"FAILED: Invalid arguments for tool '{name}': {ex}"
                            if self.log:
                                self.log.print_action(a_id, f"op_{name}", None, res)
                            agent.send(str(res), agent, request_reply=False, silent=True)
                            continue
                    target = args.get('target')
                    multiplier = args.get('multiplier', 1)
                    res = self.env.execute_operation(a_id, name, target, multiplier)
                    if self.log:
                        self.log.print_action(a_id, f"op_{name}", target, res)
                agent.send(str(res), agent, request_reply=False, silent=True)
        elif isinstance(reply, str) and reply.strip():
            if self.log:
                self.log.print_think(a_id, f"(Implicit) {reply}")
        self.check_victory_conditions(a_id)

    def check_victory_conditions(self, a_id):
        # controlla le condizioni di vincita globali e per agente
        conditions = self.raw_config.get('victory_conditions', []) + self.env.agents[a_id].config.get('victory_conditions', [])
        for cond in conditions:
            res = cond['resource']
            threshold = cond['threshold']
            scope = cond.get('scope', 'global')
            if scope == 'individual':
                if self.env.portfolios[a_id].get(res, 0) >= threshold:
                    self.log.print(f"\033[1;32m>>> {a_id} WINS with {res} = {self.env.portfolios[a_id].get(res, 0)}\033[0m")
            else:
                for agent_id, portfolio in self.env.portfolios.items():
                    if portfolio.get(res, 0) >= threshold:
                        self.log.print(f"\033[1;32m>>> {agent_id} WINS with {res} = {portfolio.get(res, 0)}\033[0m")
        


# ==========================================
# 5. CONFIG (Dilemma + Trade)
# ==========================================
config_yaml = """
global_rules:
  epochs: 5
  steps: 1
  execution_mode: 'sequential'
  operations:
    cooperate:
      input: {token: 1}
      output: {score: 1}
      target_impact: {score: 3}
    defect:
      input: {token: 1}
      output: {score: 3}
      target_impact: {score: -2}
constraints:
  score: {min: -10}
  token: {min: 0}
    
victory_conditions:
  - {resource: 'score', threshold: 10}  # threshold può essere 'min', 'max', 'count'

actors:
  - id: 'player'
    replicas: 2
    model_name: 'llama3.1:8b'
    can_trade: false
    can_think: false
    can_chat: false
    persona: "Maximize score and overcome. You are selfish."
    initial_portfolio: {score: 0, token: 2}
    victory_conditions:
        - {resource: 'score', threshold: 10, scope: 'individual'}
    constraints:
        score: {min: -10}
"""

if __name__ == "__main__":
    engine = DoxaEngineV26(config_yaml)
    engine.run()