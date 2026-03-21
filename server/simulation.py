import asyncio
import time
from typing import List, Dict, Any
from models import FullConfigModel, ActionModel
from manager import WorldManager
from agents import Agent
from parser import ActionParser

class SimulationEngine:
    world_manager: WorldManager
    agents: Dict[str, Agent]
    feedbacks: Dict[str, str]

    def __init__(self, config: FullConfigModel, socketio):
        self.config = config
        self.socketio = socketio
        self.running = False
        self.tick_count = 0
        self.action_queue = asyncio.Queue()
        self.manual_actions = []
        self.thoughts_data = {}
        self.thinking_actors = set() 
        self._tasks = [] # To track background tasks
        self._init_components(config)

    def _init_components(self, config: FullConfigModel):
        self.world_manager = WorldManager(config)
        self.agents = {a.id: Agent(a, config) for a in config.all_actors}
        self.feedbacks = {a.id: "" for a in config.all_actors}
        self.thinking_actors.clear() # Reset on config update

    def update_config(self, new_config: FullConfigModel):
        """Update configuration on the fly."""
        self.config = new_config
        self._init_components(new_config)
        print("SimulationEngine: Configuration updated on the fly.")

    def inject_action(self, action: ActionModel):
        self.manual_actions.append(action)

    async def run(self):
        print("[ENGINE] run() called. Starting Continuous Flow...")
        # Cancel any previous running tasks
        await self.stop()
        
        self.running = True
        
        # 1. Start Agent Loops or Sequential Process
        if self.config.world and self.config.world.process == "sequential":
            _task = asyncio.create_task(self.sequential_loop())
            self._tasks.append(_task)
        else:
            for aid in self.agents:
                task = asyncio.create_task(self.actor_loop(aid))
                self._tasks.append(task)
            
        # 2. Start World Heartbeat
        heartbeat_task = asyncio.create_task(self.world_heartbeat())
        self._tasks.append(heartbeat_task)
        
        # Keep run() alive until stopped
        while self.running:
            await asyncio.sleep(1)

    async def stop(self):
        """Cleanly stop the simulation and all tasks."""
        self.running = False
        if self._tasks:
            print(f"[ENGINE] Stopping {len(self._tasks)} tasks...")
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []
        self.thinking_actors.clear()

    async def world_heartbeat(self):
        """Periodic world maintenance and state broadcasting."""
        while self.running:
            self.tick_count += 1
            # Apply periodic world effects (decay, etc.)
            self.world_manager.apply_world_effects()
            
            # Process Manual Injected Actions
            while self.manual_actions:
                action = self.manual_actions.pop(0)
                self.world_manager.execute_action(action)

            # Broadcast current state
            state = {
                "tick": self.tick_count,
                "actors": {aid: a.model_dump() for aid, a in self.world_manager.actors.items()},
                "rooms": {rid: r.model_dump() for rid, r in self.world_manager.rooms.items()},
                "alliances": {aid: al.model_dump() for aid, al in self.world_manager.alliances.items()},
                "thoughts": self.thoughts_data,
                "logs": self.world_manager.logs[-15:] 
            }
            self.socketio.emit('state_update', state)
            
            await asyncio.sleep(self.config.world.tick_interval if self.config.world else 2.0)

    async def actor_loop(self, aid: str):
        """Independent thinking loop for each agent (Parallel Mode)."""
        import random
        while self.running:
            # Random jitter to prevent synchronized load spikes on Ollama
            await asyncio.sleep(random.uniform(0.1, 1.0))
            
            if aid not in self.thinking_actors and aid in self.world_manager.actors:
                self.thinking_actors.add(aid)
                try:
                    await self.actor_think_routine(aid)
                finally:
                    self.thinking_actors.discard(aid)

    async def sequential_loop(self):
        """Sequential turn-based process for structured games."""
        print("[ENGINE] Sequential Loop started.")
        while self.running:
            order = self.config.world.turn_order if self.config.world else []
            if not order:
                order = list(self.agents.keys())
            
            for aid in order:
                if not self.running: break
                if aid not in self.world_manager.actors: continue
                
                self.thinking_actors.add(aid)
                try:
                    await self.actor_think_routine(aid)
                finally:
                    self.thinking_actors.discard(aid)
                
                # Wait a bit between turns for readability
                await asyncio.sleep(self.config.world.tick_interval if self.config.world else 2.0)

    async def actor_think_routine(self, aid: str):
        """Background routine for an agent to think without blocking the simulation."""
        try:
            # Find rooms and alliances for this actor
            rooms = [r.id for r in self.world_manager.rooms.values() if aid in r.members]
            alliances = [al.id for al in self.world_manager.alliances.values() if aid in al.members]
            
            # Fetch recent context visible to this agent
            context = self.world_manager.get_agent_context(aid)
            
            # Start thinking (can take multiple ticks)
            print(f"[ENGINE] Agent {aid} started thinking with {len(context)} context logs...")
            text = await self.agents[aid].think(rooms, alliances, context, self.feedbacks[aid])
            print(f"[ENGINE] Agent {aid} finished thinking.")
            
            # Parse result
            parsed = ActionParser.parse(aid, text)
            
            # Record in history
            agent = self.agents[aid]
            agent.add_history_event("thought", {"content": parsed["thought"] or "(Silent thinking)"})
            
            for msg in parsed["private_msgs"]:
                agent.add_history_event("message_out", msg)
                # Record in Target history too? Yes.
                target_id = msg.get("target")
                if target_id in self.agents:
                    self.agents[target_id].add_history_event("message_in", {
                        "sender": aid,
                        "content": msg.get("content")
                    })
            
            if parsed["public_msg"]:
                agent.add_history_event("broadcast_out", {"content": parsed["public_msg"]})
            
            for act in parsed["actions"]:
                agent.add_history_event("action_intent", act.model_dump())
            
            # Execute actions via manager
            self.thoughts_data[aid] = parsed["thought"]
            
            # 1. Handle Chat Messages (Immediate broadcast & log to world)
            if parsed["public_msg"]:
                self.world_manager.add_log("public", aid, parsed["public_msg"])
                self.socketio.emit('chat_message', {
                    "sender": aid, "type": "public", "content": parsed["public_msg"]
                })
            
            for pmsg in parsed["private_msgs"]:
                 self.world_manager.add_log("private", aid, pmsg["content"], target=pmsg["target"])
                 self.socketio.emit('chat_message', {
                    "sender": aid, "type": "private", "target": pmsg["target"], "content": pmsg["content"]
                }, room=pmsg["target"])

            # 2. Execute actions or queue them
            # For robustness, we'll execute them and generate feedback immediately
            tick_results = []
            for action in parsed["actions"]:
                print(f"[ASYNC ACTION] {aid} -> {action.type}")
                res = self.world_manager.execute_action(action)
                tick_results.append(res)
            
            # Update feedback for their next thinking cycle
            self.feedbacks[aid] = self.world_manager.get_feedback(aid, tick_results)

        except Exception as e:
            print(f"[ERROR] Thinking routine failed for {aid}: {e}")
        finally:
            self.thinking_actors.remove(aid)
