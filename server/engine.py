import yaml
import autogen
import json
import random
import csv
import io
import re
import threading
import time
import uuid
import zipfile
from copy import deepcopy
from typing import Annotated, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
#import google_genai
# RAG/Memory imports
import os
import tempfile
from autogen_core.memory import MemoryContent, MemoryMimeType
from autogen_ext.memory.chromadb import ChromaDBVectorMemory, PersistentChromaDBVectorMemoryConfig, SentenceTransformerEmbeddingFunctionConfig

# ==========================================
# 1. UI & LOGGING
# ==========================================

class ConsoleLogger:
    def print_header(self, text): print(f"\n\033[96m{'═'*60}\n{text}\n{'═'*60}\033[0m")
    def print_epoch(self, n): print(f"\n\033[1;35m--- EPOCH {n} STARTING ---\033[0m")
    def print_step(self, step): print(f"\n\033[1;37m{'—'*20} GLOBAL STEP {step} {'—'*20}\033[0m")
    def print_kill(self, agent_id, reason): print(f"\n\033[41mAGENT {agent_id.upper()} KILLED: {reason}\033[0m")
    def print_turn(self, agent_id): print(f"\n\033[1;33m► TURN: {agent_id.upper()}\033[0m")
    def print_think(self, agent_id, thought): print(f"\033[90m[{agent_id}] THINK: {thought}\033[0m")
    def print_action(self, agent_id, action, target, res):
        color = "\033[32m" if "SUCCESS" in res else "\033[31m"
        tgt = f" on {target}" if target else ""
        print(f"  \033[36m└─ [ACTION] {action}{tgt} -> {color}{res}\033[0m")
    def print_delta(self, before, after):
        for res in set(before.keys()) | set(after.keys()):
            diff = after.get(res, 0) - before.get(res, 0)
            if diff > 0: print(f"     \033[92m▲ +{diff} {res}\033[0m")
            elif diff < 0: print(f"     \033[91m▼ {diff} {res}\033[0m")
    def print(self, text): print(f"\033[90m{text}\033[0m")
    def print_communication(self, sender, message, target = "PUBLIC"):
        color = "\033[34m" if target == "PUBLIC" else "\033[35m"
        print(f"{color}[{sender} -> {target}]: {message}\033[0m")
    def print_trade(self, agent_id, target, give_res, give_qty, take_res, take_qty, result):
        color = "\033[32m" if "SUCCESS" in str(result) else "\033[31m"
        print(f"\033[36m[{agent_id} → {target}] TRADE: {give_qty}×{give_res} ↔ {take_qty}×{take_res} → {color}{result}\033[0m")
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
        elif provider == 'google':
            llm_config = {
                "config_list": [{
                    "model": model,
                    "api_type": "google",
                    "api_key": config.get('api_key', 'AIzaSyABmY06JX28X0000_lKS875yf-WIXv7-70'),
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
            """Send a private message to another agent."""
            if recipient not in self.env.agents: return "Error: Recipient not found."
            self.logger.print_communication(self.agent_id, message, target=recipient)
            self.send(f"[PRIVATE] {message}", self.env.agents[recipient], request_reply=False, silent=True)

            return "Message sent."
        def broadcast(message: str) -> str:
            """Broadcast a message to all other agents."""
            self.logger.print_communication(self.agent_id, message, target="PUBLIC")
            for name, agent in self.env.agents.items():
                if name != self.agent_id:
                    self.send(f"[PUBLIC] {self.agent_id}: {message}", agent, request_reply=False, silent=True)
            return "Broadcast sent."
        # 2. Trade
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
                self.logger.print_trade(trade['from'], trade['to'], g_res, g_qty, t_res, t_qty, f"ACCEPTED: {res}")
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
                self.logger.print_trade(trade['from'], trade['to'], g_res, g_qty, t_res, t_qty, f"REJECTED: {res}")
            else:
                self.logger.print_action(self.agent_id, "reject_trade", trade_id, res)
            return res
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

# ==========================================
# 3. ENVIRONMENT
# ==========================================
class SimulationEnvironment:
    def __init__(self, config, log_verbose=True, rag_limit=200, logger=None):
        import threading
        self.config = config
        self.global_rules = config.get('global_rules', {})
        self.portfolios = {}
        self.agents = {}
        self.pending_trades = {}
        self.trade_counter = 1
        if logger is not None:
            self.log = logger
        else:
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
        Save a piece of knowledge to the agent's RAG memory
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

    def get_agent_memory_graph(self, agent_id: str, limit: int = 80):
        import asyncio

        memory = self.env.agent_memories.get(agent_id)
        if not memory:
            return {
                "agent": agent_id,
                "docs": [],
                "graph": {
                    "nodes": [{"id": agent_id, "name": agent_id, "category": "agent", "symbolSize": 44, "value": 1}],
                    "edges": [],
                },
                "stats": {"documents": 0, "links": 0},
            }

        async def load_docs():
            listed = await memory.list()
            return listed[-limit:]

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        documents = loop.run_until_complete(load_docs())

        def normalize_doc(doc, index: int):
            content = getattr(doc, "content", None)
            if content is None and isinstance(doc, dict):
                content = doc.get("content")
            content = str(content or "")
            doc_id = getattr(doc, "id", None)
            if doc_id is None and isinstance(doc, dict):
                doc_id = doc.get("id")
            doc_id = str(doc_id or f"mem-{index + 1}")
            tokens = [
                token
                for token in re.findall(r"[a-zA-Z0-9_]{4,}", content.lower())
                if token not in {"that", "this", "with", "from", "have", "will", "your", "agent", "trade", "resource", "about"}
            ]
            unique_tokens = []
            for token in tokens:
                if token not in unique_tokens:
                    unique_tokens.append(token)
                if len(unique_tokens) >= 10:
                    break
            return {
                "id": doc_id,
                "content": content,
                "preview": content[:240],
                "tokens": unique_tokens,
            }

        docs = [normalize_doc(doc, index) for index, doc in enumerate(documents)]
        nodes = [{"id": agent_id, "name": agent_id, "category": "agent", "symbolSize": 44, "value": max(1, len(docs))}]
        edges = []

        for doc in docs:
            weight = max(1, len(doc["tokens"]))
            nodes.append({
                "id": doc["id"],
                "name": doc["id"],
                "category": "memory",
                "symbolSize": 20 + min(weight, 10),
                "value": weight,
                "preview": doc["preview"],
                "tokens": doc["tokens"],
            })
            edges.append({"source": agent_id, "target": doc["id"], "value": weight})

        similarity_edges = []
        for index, left in enumerate(docs):
            left_tokens = set(left["tokens"])
            if not left_tokens:
                continue
            for right in docs[index + 1:]:
                overlap = sorted(left_tokens.intersection(right["tokens"]))
                if len(overlap) >= 2:
                    similarity_edges.append({
                        "source": left["id"],
                        "target": right["id"],
                        "value": len(overlap),
                        "label": ", ".join(overlap[:4]),
                    })

        similarity_edges.sort(key=lambda edge: edge["value"], reverse=True)
        edges.extend(similarity_edges[:120])
        return {
            "agent": agent_id,
            "docs": docs,
            "graph": {
                "nodes": nodes,
                "edges": edges,
            },
            "stats": {
                "documents": len(docs),
                "links": len(edges),
            },
        }

    def create_trade(self, sender, target, g_res, g_qty, t_res, t_qty):
        """
        Propose a trade to target
        """
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
        """
        Reply to a trade offer (accept/reject)
        """
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
            if agentAConstraints is None: agentAConstraints = {}
            if agentBConstraints is None: agentBConstraints = {}
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
            ops = {**self.global_rules.get('operations', {}), **self.agents[actor_id].config.get('operations', {})}
            op = ops.get(op_name)
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
from typing import Optional

# 4. CHATBOT (Natural Language Query)
# ==========================================

# Nuova versione: chatbot come agent conversazionale con tool
import autogen
class DoxaChatbot(autogen.ConversableAgent):
    """
    Chatbot esterno che risponde a domande in linguaggio naturale sulla simulazione.
    Ha accesso allo YAML iniziale e a tool per estrarre dati (come export_data).
    """
    def __init__(self, engine, model: Optional[str] = None, provider: Optional[str] = None):
        self.engine = engine
        self.model = model or "llama3.1:8b"
        self.provider = provider or "ollama"
        if self.provider == "ollama":
            llm_config = {
                "config_list": [{
                    "model": self.model,
                    "base_url": "http://localhost:11434/v1",
                    "api_type": "openai",
                    "api_key": "ollama",
                    "price": [0,0]
                }],
                "temperature": 0.2,
            }
        else:
            raise ValueError(f"Provider {self.provider} not supported yet for chatbot.")
        super().__init__(
            name="DoxaChatbot",
            llm_config=llm_config,
            human_input_mode="NEVER",
        )
        self._register_tools()

    def _register_tools(self):
        # Tool: export_data
        def export_data_tool(query: dict = None, format: str = "json") -> str:
            """Estrae dati dalla simulazione secondo la query (come l'API export_data)."""
            return self.engine.export_data(query, format)
        # Tool: get_yaml
        def get_yaml_tool() -> str:
            """Restituisce lo YAML iniziale della simulazione."""
            import yaml
            return yaml.dump(self.engine.raw_config)
        # Tool: get_state
        def get_state_tool() -> str:
            """Restituisce lo stato attuale (portafogli, trades, agenti)."""
            return self.engine.export_data({"agents": True, "portfolios": True, "trades": True, "resources": True}, format="json")
        self.register_for_llm(name="export_data", description=export_data_tool.__doc__)(export_data_tool)
        self.register_for_execution(name="export_data")(export_data_tool)
        self.register_for_llm(name="get_yaml", description=get_yaml_tool.__doc__)(get_yaml_tool)
        self.register_for_execution(name="get_yaml")(get_yaml_tool)
        self.register_for_llm(name="get_state", description=get_state_tool.__doc__)(get_state_tool)
        self.register_for_execution(name="get_state")(get_state_tool)

    def answer(self, query: str) -> str:
        """
        Answers a natural language question about the simulation using the available tools. Always in English.
        """
        prompt = (
            "You are an assistant that answers questions about the following multi-agent simulation. "
            "You have access to tools to extract data and to the initial YAML. "
            "If the question is hypothetical, explain what would happen according to the rules and current state. "
            "If it is factual, answer only based on the provided data. "
            "If you cannot answer with certainty, explain what is missing. "
            "Use the tools if needed. "
            "Always answer in clear, detailed English."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query}
        ]
        reply = self.generate_reply(messages=messages)
        if isinstance(reply, dict) and "content" in reply:
            return reply["content"]
        return str(reply)


# 5. ENGINE
# ==========================================
class DoxaEngineV26:

    def __init__(self, yaml_str, log_verbose=True, rag_limit=200, logger=None):
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
        self.config_source = {"kind": "embedded", "value": "config_yaml"}
        self.config_text = ""
        self._set_config(yaml_str, source_kind="embedded", source_value="config_yaml")
        self.chatbot = DoxaChatbot(self)

    def _validate_config_dict(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError("YAML root must be a mapping.")
        if "actors" not in config or not isinstance(config["actors"], list) or not config["actors"]:
            raise ValueError("Config must define a non-empty 'actors' list.")
        if "global_rules" not in config or not isinstance(config["global_rules"], dict):
            raise ValueError("Config must define 'global_rules' as a mapping.")
        for actor in config["actors"]:
            if not isinstance(actor, dict):
                raise ValueError("Each actor must be a mapping.")
            if not actor.get("id"):
                raise ValueError("Each actor must define an 'id'.")
            if "initial_portfolio" not in actor or not isinstance(actor["initial_portfolio"], dict):
                raise ValueError(f"Actor '{actor.get('id', '<unknown>')}' must define 'initial_portfolio'.")

    def _set_config(self, yaml_text: str, source_kind: str = "text", source_value: str = "runtime"):
        parsed = yaml.safe_load(yaml_text) or {}
        self._validate_config_dict(parsed)
        self.raw_config = parsed
        self.config_text = yaml_text.strip() + "\n"
        self.config_source = {"kind": source_kind, "value": source_value}
        self.env = SimulationEnvironment(self.raw_config, log_verbose=self.log_verbose, rag_limit=self.rag_limit, logger=self.logger)
        self.log = self.env.log
        uses_ollama = any(actor.get("provider", "ollama").lower() == "ollama" for actor in self.raw_config.get("actors", []))
        if uses_ollama:
            self.startOllama()

    def validate_yaml(self, yaml_text: str):
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
            **deepcopy(self.raw_config.get("global_rules", {}).get("constraints", {})),
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
        snapshot = {
            "timestamp": time.time(),
            "run_id": self.run_id,
            "epoch": self.current_epoch,
            "step": self.current_step,
            "state": self.state,
            "reason": reason,
            "focus_agent": focus_agent,
            "totals": self._compute_totals(),
            "agents": {agent_id: dict(portfolio) for agent_id, portfolio in self.env.portfolios.items()},
        }
        self.resource_history.append(snapshot)
        self.resource_history = self.resource_history[-2000:]
        return snapshot

    def get_global_timeline(self):
        return self.resource_history

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
        return self.event_history[-limit:]

    def get_events_page(self, limit: int = 500, offset: int = 0):
        """Paginazione degli eventi: offset 0 = più recenti."""
        total = len(self.event_history)
        # offset 0 restituisce gli ultimi `limit` eventi
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
            selected_agent = agent_id or active_agents[0]
            if selected_agent not in self.env.agents:
                raise RuntimeError(f"Agent '{selected_agent}' not found.")
        if self.log:
            self.log.print_step(self.current_step)
        self._step_agent(selected_agent)
        self.record_snapshot("manual_step", selected_agent)
        return self.get_status()

    def _wait_if_paused(self):
        while not self._pause_event.is_set():
            if self._stop_event.is_set():
                return False
            time.sleep(0.05)
        return not self._stop_event.is_set()

    def _apply_maintenance(self, ids):
        maintenance = self.raw_config.get("maintenance", {})
        for agent_id in list(ids):
            if agent_id not in self.env.agents:
                continue
            for resource_name, amount in maintenance.items():
                self.env.portfolios[agent_id][resource_name] = self.env.portfolios[agent_id].get(resource_name, 0) - amount
            kill_conds = self.raw_config.get("kill_conditions", []) + self.env.agents[agent_id].config.get("kill_conditions", [])
            for cond in kill_conds:
                resource_name = cond["resource"]
                threshold = cond["threshold"]
                if self.env.portfolios[agent_id].get(resource_name, 0) <= threshold:
                    if self.log:
                        self.log.print_kill(agent_id, f"Condition met: {resource_name} <= {threshold}")
                    if agent_id in self.env.agents:
                        del self.env.agents[agent_id]
                    if agent_id in self.env.portfolios:
                        del self.env.portfolios[agent_id]
                    break

    def godmode(self, action: str, params: dict) -> str:
        if action == 'inject_resource':
            agent = params['agent']
            resource_name = params['resource']
            amount = params['amount']
            if agent not in self.env.portfolios:
                return f"FAILED: Agent {agent} not found."
            self.env.portfolios[agent][resource_name] = self.env.portfolios[agent].get(resource_name, 0) + amount
        elif action == 'set_constraint':
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
            query = {"agents": True, "portfolios": True, "trades": True, "history": True, "resources": True}
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
        try:
            self._reset_runtime_storage()
            epochs = self.raw_config['global_rules'].get('epochs', 1)
            steps = self.raw_config['global_rules'].get('steps', 5)
            mode = self.raw_config['global_rules'].get('execution_mode', 'sequential')
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
                    if self.log:
                        self.log.print_step(self.current_step)
                    ids = list(self.env.agents.keys())
                    random.shuffle(ids)
                    self._apply_maintenance(ids)
                    active_ids = [agent_id for agent_id in ids if agent_id in self.env.agents]
                    if mode == 'sequential':
                        for agent_id in active_ids:
                            if self._stop_event.is_set():
                                break
                            if not self._wait_if_paused():
                                break
                            self._step_agent(agent_id)
                            self.record_snapshot("agent_step", agent_id)
                    else:
                        with ThreadPoolExecutor() as executor:
                            executor.map(self._step_agent, active_ids)
                        self.record_snapshot("step_complete")
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

    def _step_agent(self, a_id):
        if a_id not in self.env.agents:
            return
        if self.log:
            self.log.print_turn(a_id)
        agent = self.env.agents[a_id]
        try:
            reply = agent.generate_reply(messages=agent.chat_messages[agent] + [{"role": "user", "content": "Your turn."}])
        except Exception as exc:
            message = str(exc)
            transient_llm_error = (
                "503" in message
                or "UNAVAILABLE" in message.upper()
                or "high demand" in message.lower()
            )
            if transient_llm_error:
                notice = f"SKIPPED: transient LLM error for {a_id}: {message}"
                if self.log:
                    self.log.print_action(a_id, "llm_generate_reply", None, notice)
                self.record_event({
                    "type": "llm_transient_error",
                    "agent": a_id,
                    "text": notice,
                })
                return
            raise
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
                    res = self.env.execute_operation(a_id, name, target, multiplier)
                    if self.log:
                        self.log.print_action(a_id, f"op_{name}", target, res)
                agent.send(str(res), agent, request_reply=False, silent=True)
        elif isinstance(reply, str) and reply.strip() and self.log:
            self.log.print_think(a_id, f"(Implicit) {reply}")
        self.check_victory_conditions(a_id)

    def check_victory_conditions(self, a_id):
        if a_id not in self.env.agents or a_id not in self.env.portfolios:
            return
        conditions = self.raw_config.get('victory_conditions', []) + self.env.agents[a_id].config.get('victory_conditions', [])
        for cond in conditions:
            resource_name = cond['resource']
            threshold = cond['threshold']
            scope = cond.get('scope', 'global')
            if scope == 'individual':
                if self.env.portfolios[a_id].get(resource_name, 0) >= threshold:
                    self.log.print_victory(f"{a_id} wins with {resource_name} = {self.env.portfolios[a_id].get(resource_name, 0)}")
            else:
                for agent_id, portfolio in self.env.portfolios.items():
                    if portfolio.get(resource_name, 0) >= threshold:
                        self.log.print_victory(f"{agent_id} wins with {resource_name} = {portfolio.get(resource_name, 0)}")
        


# ==========================================
# 5. CONFIG (Dilemma + Trade)
# ==========================================
config_yaml = """
global_rules:
  epochs: 1
  steps: 10
  execution_mode: 'sequential'

maintenance: {corn: 1}
  
kill_conditions:
  - {resource: 'corn', threshold: 0} 
    
victory_conditions:
  - {resource: 'gold', threshold: 100}  # threshold può essere 'min', 'max', 'count'

actors:
  - id: 'player'
    replicas: 2
    provider: 'google'
    model_name: 'gemini-2.5-pro' #'qwen2.5:1.5b' #'llama3.1:8b'
    persona: "Trade and collaborate"
    initial_portfolio: {corn: 20, gold: 10}
    constraints:
      gold: {min: 0}
      corn: {min: 0}
    operations: 
        farm:
            input: {gold: 2}
            output: {corn: 5}
  - id: 'miners'
    replicas: 2
    provider: 'google'
    model_name: 'gemini-2.5-pro' #'qwen2.5:1.5b' #'llama3.1:8b'
    persona: "Trade and collaborate"
    initial_portfolio: {gold: 20, corn: 10}
    constraints:
      gold: {min: 0}
      corn: {min: 0}
    operations: 
        mine:
            input: {corn: 2}
            output: {gold: 5}
    
"""

if __name__ == "__main__":
    engine = DoxaEngineV26(config_yaml)
    engine.run()