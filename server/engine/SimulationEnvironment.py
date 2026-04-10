"""
SimulationEnvironment
---------------------
Central shared state container for one simulation run.

Responsibilities
~~~~~~~~~~~~~~~~
* Holds the canonical portfolio dict (``_portfolios``), agent dict
  (``_agents``), and pending-trade dict (``_pending_trades``).
* Owns subsystem instances: ``RelationGraph``, ``MarketEngine``,
  ``WorldEventScheduler``, ``MacroTracker``, and per-agent
  ``AgentEconomics`` / price-expectation maps.
* Manages per-agent persistent RAG memory (``ChromaDBVectorMemory``) with
  automatic eviction when the item cap (``rag_limit``) is exceeded.
* Exposes ``@property`` shims for backward compatibility.
* Provides the public trade/operation API used by ``DoxaEngine`` and
  ``DoxaAgent``.

Threading
~~~~~~~~~
All mutable state accesses go through ``self._lock`` (a ``threading.RLock``
shared with ``MarketEngine``).
"""
from typing import Any, Dict, Optional
import os
import tempfile
import re
from copy import deepcopy
from agents.AgentEconomics import AgentEconomics
from relations.RelationGraph import RelationGraph
from market.MarketEngine import MarketEngine
from events.WorldEventScheduler import WorldEventScheduler
from MacroTracker import MacroTracker
from agents.DoxaAgent import DoxaAgent
from utils.ConsoleLogger import ConsoleLogger
import threading

from autogen_core.memory import MemoryContent, MemoryMimeType
from autogen_ext.memory.chromadb import ChromaDBVectorMemory, PersistentChromaDBVectorMemoryConfig, SentenceTransformerEmbeddingFunctionConfig

# ==========================================
# 3. ENVIRONMENT
# ==========================================
class SimulationEnvironment:
    """Central shared-state container for one simulation epoch.

    Created once per ``DoxaEngine`` instance; ``reset()`` is called at the
    start of every epoch to re-initialise portfolios and agents while
    preserving RAG memories.
    """
    def __init__(self, config, log_verbose=True, rag_limit=200, logger=None):
        """Initialise the environment from *config* (the parsed YAML dict).

        Args:
            config:      Full parsed YAML dict (``global_rules`` + ``actors`` + …).
            log_verbose: If ``True`` and no *logger* is supplied, create a
                         ``ConsoleLogger`` for formatted terminal output.
            rag_limit:   Maximum number of RAG memory entries per agent before
                         oldest entries are evicted (LRU-like).
            logger:      Optional pre-built logger instance; overrides
                         *log_verbose* if provided.
        """
        import threading
        self.config = config
        self.global_rules = config.get('global_rules', {})
        # Backward-compat mutable dicts (also accessed via WorldState properties)
        self._portfolios: Dict[str, Dict] = {}
        self._agents: Dict[str, Any] = {}
        self._pending_trades: Dict[str, Dict] = {}
        self.trade_counter = 1
        if logger is not None:
            self.log = logger
        else:
            self.log = ConsoleLogger() if log_verbose else None
        # RAG memory per agent (persistente tra i reset)
        self.agent_memories = {}
        self._rag_locks = {}
        self._rag_stats = {}
        self.rag_limit = rag_limit
        self._lock = threading.RLock()
        self._current_tick: int = 0

        # New subsystems — initialized/reset in reset()
        self.relation_graph = RelationGraph()
        self.market_engine: Optional[MarketEngine] = self._build_market_engine()
        self.event_scheduler: Optional[WorldEventScheduler] = self._build_event_scheduler()
        # Macro and agent-economics subsystems (no reset required until reset() is called)
        self.macro_tracker: MacroTracker = MacroTracker()
        self.agent_economics_map: Dict[str, AgentEconomics] = {}
        self.price_expectations: Dict[str, Dict[str, float]] = {}  # agent_id → resource → EWA price

    # ── backward-compat property shims ──────────────────────────────────────────────────
    # Allow code written against the old flat-attribute style to continue working.
    @property
    def portfolios(self) -> Dict[str, Dict]:
        """Live portfolio mapping: ``{agent_id: {resource: quantity}}``."""
        return self._portfolios

    @portfolios.setter
    def portfolios(self, v):
        self._portfolios = v

    @property
    def agents(self) -> Dict[str, Any]:
        """Live agent mapping: ``{agent_id: DoxaAgent}``."""
        return self._agents

    @agents.setter
    def agents(self, v):
        self._agents = v

    @property
    def pending_trades(self) -> Dict[str, Dict]:
        """Pending OTC trade offers awaiting acceptance/rejection by the target agent."""
        return self._pending_trades

    @pending_trades.setter
    def pending_trades(self, v):
        self._pending_trades = v

    # ── subsystem builders ───────────────────────────────────────────────────
    def _build_market_engine(self) -> Optional["MarketEngine"]:
        """Build a ``MarketEngine`` from ``global_rules.markets``, or return ``None``."""
        markets_cfg = self.global_rules.get('markets', [])
        if not markets_cfg:
            return None
        return MarketEngine(markets_cfg, shared_lock=self._lock)

    def _build_event_scheduler(self) -> Optional["WorldEventScheduler"]:
        """Build a ``WorldEventScheduler`` from ``world_events``, or return ``None``."""
        events_cfg = self.config.get('world_events', [])
        if not events_cfg:
            return None
        return WorldEventScheduler(events_cfg)

    def _setup_market_maker_portfolios(self):
        """Create synthetic portfolio entries for the per-market market-maker agent."""
        me = self.market_engine
        if not me:
            return
        for resource, market in me.markets.items():
            mm_cfg = market.config.get("market_maker")
            if not mm_cfg:
                continue
            mm_id = f"__mm_{resource}"
            depth = float(mm_cfg.get("depth", 10))
            inv_limit = float(mm_cfg.get("inventory_limit", 200))
            initial_price = market.current_price
            self._portfolios[mm_id] = {
                market.currency: max(inv_limit * initial_price * 2, depth * initial_price * 4),
                resource: max(inv_limit, depth * 2),
            }

    # ────────────────────────────────────────────────────────────────────────
    def reset(self, actors_cfg):
        """Re-initialise all mutable state for a new epoch.

        * Clears portfolios, agents, pending trades, and tick counter.
        * Creates/reuses ``DoxaAgent`` instances (RAG memories are preserved
          across epochs to allow agents to retain learned knowledge).
        * Reconnects leader -> sub-agent relationships.
        * Rebuilds ``RelationGraph``, ``MarketEngine``, ``WorldEventScheduler``,
          ``MacroTracker``, and per-agent ``AgentEconomics`` maps.
        * Provisions synthetic portfolios for any configured market-makers.

        Args:
            actors_cfg: The ``actors`` list from the parsed YAML config.
        """
        with self._lock:
            self._portfolios = {}
            self._agents = {}
            self._pending_trades = {}
            self._current_tick = 0
            # Non ricreare agent_memories se già esistono
            for actor in actors_cfg:
                replicas = actor.get('replicas', 1)
                for i in range(replicas):
                    a_id = f"{actor['id']}_{i+1}" if replicas > 1 else actor['id']
                    self._portfolios[a_id] = deepcopy(actor['initial_portfolio'])
                    self._agents[a_id] = DoxaAgent(a_id, actor, self)
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
                    if can_rag and a_id not in self._rag_locks:
                        self._rag_locks[a_id] = threading.RLock()
                    if can_rag and a_id not in self._rag_stats:
                        self._rag_stats[a_id] = {"initialized": False, "estimated_count": 0}
            # Cleanup memorie non più usate
            to_remove = [aid for aid in self.agent_memories if aid not in self._portfolios]
            for aid in to_remove:
                try:
                    self.agent_memories[aid].close()
                except Exception:
                    pass
                del self.agent_memories[aid]
                self._rag_locks.pop(aid, None)
                self._rag_stats.pop(aid, None)
            # Collega sub-agenti ai leader (dopo creazione agenti)
            for a_id, agent in self._agents.items():
                if getattr(agent, 'is_leader', False):
                    # Se non specificato, tutti tranne se stesso
                    if not agent.sub_agents:
                        agent.sub_agents = [k for k in self._agents if k != a_id]
                    else:
                        # Filtra solo quelli esistenti
                        agent.sub_agents = [k for k in agent.sub_agents if k in self._agents]
            # Init / reset subsystems
            agent_ids = list(self._agents.keys())
            self.relation_graph = RelationGraph()
            self.relation_graph.init_from_yaml(
                self.global_rules.get('relations', []), agent_ids
            )
            self.market_engine = self._build_market_engine()
            if self.event_scheduler:
                self.event_scheduler.reset()
            else:
                self.event_scheduler = self._build_event_scheduler()
            # Reset macro / economics subsystems
            self.macro_tracker.reset()
            self.price_expectations = {}
            self.agent_economics_map = {}
            for _actor in actors_cfg:
                _replicas = _actor.get("replicas", 1)
                _econ = AgentEconomics.from_config(_actor.get("economics"))
                for _i in range(_replicas):
                    _a_id = f"{_actor['id']}_{_i+1}" if _replicas > 1 else _actor["id"]
                    self.agent_economics_map[_a_id] = _econ
            self._setup_market_maker_portfolios()

    def save_memory_rag(self, agent_id, knowledge):
        """
        Save a piece of knowledge to the agent's RAG memory
        """
        with self._lock:
            memory = self.agent_memories.get(agent_id)
            rag_lock = self._rag_locks.get(agent_id)
            rag_stats = self._rag_stats.setdefault(agent_id, {"initialized": False, "estimated_count": 0})
            rag_limit = self.rag_limit
        if not memory or not rag_lock:
            return "FAILED: No RAG memory for this agent."

        payload = [knowledge] if isinstance(knowledge, str) else knowledge
        if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
            return "FAILED: Invalid knowledge type."
        if not payload:
            return "FAILED: Empty knowledge payload."

        import asyncio

        async def add_knowledge():
            estimated_count = int(rag_stats.get("estimated_count", 0))
            initialized = bool(rag_stats.get("initialized", False))
            docs = None

            if not initialized:
                docs = await memory.list()
                estimated_count = len(docs)
                initialized = True

            overflow = max(0, estimated_count + len(payload) - rag_limit)
            if overflow > 0:
                docs = docs if docs is not None else await memory.list()
                delete_count = min(len(docs), overflow)
                for document in docs[:delete_count]:
                    await memory.delete(document.id)
                estimated_count = max(0, len(docs) - delete_count)

            for item in payload:
                await memory.add(MemoryContent(content=item, mime_type=MemoryMimeType.TEXT))
            estimated_count += len(payload)
            return {"initialized": initialized, "estimated_count": estimated_count}

        with rag_lock:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            updated_stats = loop.run_until_complete(add_knowledge())

        with self._lock:
            self._rag_stats[agent_id] = updated_stats
        return "SUCCESS: Knowledge saved to RAG."

    def get_agent_memory_graph(self, agent_id: str, limit: int = 80):
        import asyncio

        memory = self.agent_memories.get(agent_id)
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
        """Create a pending OTC trade offer from *sender* to *target*.

        Verifies that *sender* exists and has sufficient *g_res*.
        Notifies the target via AutoGen message including the new trade ID.

        Returns:
            ``"SUCCESS: TRD_N created"`` or a ``"FAILED: …"`` message.
        """
        with self._lock:
            if target not in self._portfolios: return "FAILED: Target not found"
            if self._portfolios[sender].get(g_res, 0) < g_qty: return f"FAILED: You don't have {g_qty} {g_res}"
            tid = f"TRD_{self.trade_counter}"
            self.trade_counter += 1
            self._pending_trades[tid] = {
                "id": tid,
                "from_agent": sender, "to_agent": target,
                # backward-compat keys for any JSON views
                "from": sender, "to": target,
                "give": {g_res: g_qty}, "take": {t_res: t_qty}
            }
            # Notifica il target tramite AutoGen
            self._agents[sender].send(f"I offered you {tid}: {g_qty} {g_res} for {t_qty} {t_res}", self._agents[target], request_reply=False, silent=True)
            return f"SUCCESS: {tid} created"

    def resolve_trade(self, responder, tid, accept):
        """Accept or reject a pending trade offer.

        On acceptance:
        * Verifies both parties still hold the required resources.
        * Checks post-swap constraint compliance (min/max) for both agents;
          rolls back on violation.
        * Executes the portfolio swap atomically under ``self._lock``.
        * Updates trust: +delta on success (bidirectional), -delta on rejection.

        Args:
            responder: Agent ID of the trade target (the one responding).
            tid:       Trade ID string (``"TRD_N"``).
            accept:    ``True`` to accept, ``False`` to reject.

        Returns:
            ``"SUCCESS: Trade completed / rejected"`` or a ``"FAILED: …"`` message.
        """
        with self._lock:
            trade = self._pending_trades.get(tid)
            if not trade or trade['to_agent'] != responder: return "FAILED: Trade not found or not for you"
            sender = trade['from_agent']
            rel_dyn = self.global_rules.get('relation_dynamics', {})
            if not accept:
                del self._pending_trades[tid]
                # Trust penalty on rejection
                reject_delta = rel_dyn.get('on_trade_rejected', {}).get('trust_delta', -0.02)
                if reject_delta:
                    self.relation_graph.update_trust(responder, sender, reject_delta)
                return "SUCCESS: Trade rejected"
            # Check resources for both
            g_res, g_qty = list(trade['give'].items())[0]
            t_res, t_qty = list(trade['take'].items())[0]
            if self._portfolios[sender].get(g_res, 0) < g_qty: return "FAILED: Sender no longer has resources"
            if self._portfolios[responder].get(t_res, 0) < t_qty: return "FAILED: You don't have resources"
            agentAConstraints = self._agents[sender].constraints
            agentBConstraints = self._agents[responder].constraints
            if agentAConstraints is None: agentAConstraints = {}
            if agentBConstraints is None: agentBConstraints = {}
            if agentAConstraints.get(g_res, {}).get('min', float('-inf')) > self._portfolios[sender].get(g_res, 0) - g_qty: return "FAILED: Sender would violate constraints"
            if agentAConstraints.get(g_res, {}).get('max', float('inf')) < self._portfolios[sender].get(g_res, 0) - g_qty: return "FAILED: Sender would violate constraints"
            if agentAConstraints.get(t_res, {}).get('min', float('-inf')) > self._portfolios[sender].get(t_res, 0) + t_qty: return "FAILED: Sender would violate constraints"
            if agentAConstraints.get(t_res, {}).get('max', float('inf')) <  self._portfolios[sender].get(t_res, 0) + t_qty: return "FAILED: Sender would violate constraints"
            if agentBConstraints.get(t_res, {}).get('min', float('-inf')) > self._portfolios[responder].get(t_res, 0) - t_qty: return "FAILED: Responder would violate constraints"
            if agentBConstraints.get(t_res, {}).get('max', float('inf')) <  self._portfolios[responder].get(t_res, 0) - t_qty: return "FAILED: Responder would violate constraints"
            if agentBConstraints.get(g_res, {}).get('min', float('-inf')) > self._portfolios[responder].get(g_res, 0) + g_qty: return "FAILED: Responder would violate constraints"
            if agentBConstraints.get(g_res, {}).get('max', float('inf')) < self._portfolios[responder].get(g_res, 0) + g_qty: return "FAILED: Responder would violate constraints"
            # Rollbackable swap
            self._portfolios[sender][g_res] -= g_qty
            self._portfolios[responder][g_res] += g_qty
            self._portfolios[responder][t_res] -= t_qty
            self._portfolios[sender][t_res] += t_qty
            del self._pending_trades[tid]
            # Trust bonus on success (bidirectional)
            success_delta = rel_dyn.get('on_trade_success', {}).get('trust_delta', 0.03)
            if success_delta:
                self.relation_graph.update_trust(sender, responder, success_delta)
                self.relation_graph.update_trust(responder, sender, success_delta)
            return "SUCCESS: Trade completed"

    def get_pending_trades_for(self, agent_id):
        return [f"- {tid} from {t['from_agent']}: Wants {t['take']} for {t['give']}" 
                for tid, t in self._pending_trades.items() if t['to_agent'] == agent_id]

    def execute_operation(self, actor_id, op_name, target_id=None, multiplier=1):
        """Execute a named operation on behalf of *actor_id*.

        Resolves the operation definition from global and actor-level ops,
        checks input resources, applies inputs/outputs, optionally applies
        ``target_impact`` to a second agent, then validates constraints for
        both agents.  Rolls back the entire state change on any violation.

        Args:
            actor_id:   ID of the agent executing the operation.
            op_name:    Operation name as declared in YAML.
            target_id:  Optional second agent affected by ``target_impact``.
            multiplier: Scale factor applied to all input/output amounts.

        Returns:
            ``"SUCCESS"`` or a ``"FAILED: …"`` message.
        """
        with self._lock:
            ops = {**self.global_rules.get('operations', {}), **self._agents[actor_id].config.get('operations', {})}
            op = ops.get(op_name)
            if not op:
                return f"FAILED: Operation '{op_name}' not found."
            port = self._portfolios[actor_id]
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
            if target_id and 'target_impact' in op and target_id in self._portfolios:
                tbefore = deepcopy(self._portfolios[target_id])
                if target_id in self._portfolios:
                    for r, v in op['target_impact'].items():
                        self._portfolios[target_id][r] = self._portfolios[target_id].get(r, 0) + v * multiplier
                if self.log:
                    self.log.print(f"Target delta on {target_id}")
                    self.log.print_delta(tbefore, self._portfolios[target_id])
            rollback = False
            constraints = self._agents[actor_id].constraints
            for r, c in constraints.items():
                if port.get(r, 0) < c.get('min', float('-inf')): rollback = True
                if port.get(r, 0) > c.get('max', float('inf')): rollback = True
            if target_id and target_id in self._portfolios:
                constraints = self._agents[target_id].constraints
                for r, c in constraints.items():
                    if self._portfolios[target_id].get(r, 0) < c.get('min', float('-inf')): rollback = True
                    if self._portfolios[target_id].get(r, 0) > c.get('max', float('inf')): rollback = True
            if rollback == True:
                self._portfolios[actor_id] = before
                if target_id and tbefore is not None:
                    self._portfolios[target_id] = tbefore
                return "FAILED: Constraint violation, operation rolled back."
            if self.log:
                self.log.print(f"Main delta on {actor_id}")
                self.log.print_delta(before, self._portfolios[actor_id])
            return "SUCCESS"
