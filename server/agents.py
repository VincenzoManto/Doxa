import httpx
import json
import asyncio
import time
from typing import List, Dict, Any, Optional
from models import ActorModel, FullConfigModel

# CrewAI & LangChain Imports
from crewai import Agent as CrewAgent, Task as CrewTask
from langchain_ollama import ChatOllama

class Agent:
    def __init__(self, actor: ActorModel, world_config: FullConfigModel):
        self.actor = actor
        self.world_config = world_config
        self.base_url = "http://localhost:11434"
        self.model = world_config.llm.model
        self.memory: List[str] = []
        self.history: List[Dict[str, Any]] = []
        
        # Initialize the actual CrewAI agent
        self.llm = ChatOllama(
            model=self.model,
            base_url=self.base_url,
            temperature=0.7,
            num_ctx=2048 # Explicit context for 0.5b/1.5b
        )
        
        self.crew_agent = CrewAgent(
            role=self.actor.role or self.actor.get_description(),
            goal=self.actor.goal or "Succeed in the simulation by following roles and constraints.",
            backstory=self.actor.backstory or "A specialized agent in the Doxa swarm intelligence simulation.",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            memory=False # We handle our own memory for now
        )

    def add_history_event(self, event_type: str, data: Any):
        self.history.append({
            "timestamp": time.time(),
            "type": event_type,
            "data": data
        })
        if len(self.history) > 100:
            self.history.pop(0)

    def _build_system_prompt(self, rooms: List[str], alliances: List[str]) -> str:
        # Note: CrewAI handles some of this via role/goal/backstory, 
        # but we still need the world-specific context and status.
        portfolio_str = ", ".join([f"{k}: {v}" for k, v in self.actor.portfolio.items()])
        target_ids = [a.id for a in self.world_config.actors if a.id != self.actor.id]
        
        return f"""
CONTEXT: {self.world_config.get_context}
MEMBERSHIPS: Rooms: {", ".join(rooms)}, Alliances: {", ".join(alliances)}
VALID TARGETS: {", ".join(target_ids)}
YOUR STATUS: {portfolio_str}
CONSTRAINTS: {", ".join(self.actor.constraints)}

### MANDATORY PROTOCOL:
1. LANGUAGE: ENGLISH ONLY.
2. FORMAT: YOU MUST USE XML TAGS. NO PREAMBLE.
3. OUTPUT EXAMPLE:
<THOUGHT>I need to cooperate.</THOUGHT>
<PUBLIC_MSG>Hello everyone.</PUBLIC_MSG>
<ACTION>TRADE(target, res, amt)</ACTION>
"""

    async def think(self, rooms: List[str], alliances: List[str], context: List[str], feedback: str = "") -> str:
        system_context = self._build_system_prompt(rooms, alliances)
        recent_logs = "\n".join(context) if context else "No recent events."
        
        # We wrap the thinking in a CrewAI Task
        task_description = f"""
{system_context}

RECENT WORLD EVENTS:
{recent_logs}

{f'FEEDBACK: {feedback}' if feedback else ''}

TASK: Analyze the situation and take your next turn.
Provide your response using the mandatory XML tags (<THOUGHT>, <PUBLIC_MSG>, <ACTION>).
"""
        
        task = CrewTask(
            description=task_description,
            agent=self.crew_agent,
            expected_output="An XML-tagged response containing thought, public_msg and action."
        )

        try:
            # CrewAI execute_task is sync, so we run in thread to keep things async
            output = await asyncio.to_thread(self.crew_agent.execute_task, task)
            
            # Store assistant response in history/memory
            self.memory.append(output)
            if len(self.memory) > 10: self.memory.pop(0)
            
            return output
        except Exception as e:
            print(f"[CREWAI ERROR] Agent {self.actor.id} failed task: {e}")
            return f"<THOUGHT>Error during CrewAI execution: {str(e)}</THOUGHT>"
