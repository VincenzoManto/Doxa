# Architecture

Doxa is composed of a **FastAPI backend** and a **React frontend**,
connected via REST and WebSocket. All simulation logic lives in `server/engine/`.

---

## System Overview

```mermaid
graph TD
    subgraph API["API Layer · port 5000"]
        A1[FastAPI Server]
        A2[REST Endpoints]
        A3[WebSocket /ws/events]
    end

    subgraph Engine["Engine · server/engine/"]
        B1[DoxaEngine]
        B2[SimulationEnvironment]
        B3[DoxaAgent]
        B4[MarketEngine]
        B5[RelationGraph]
        B6[WorldEventScheduler]
        B7[ConsoleLogger]
        B8[DoxaChatbot]
    end

    subgraph Modules["Sub-modules"]
        C1[AgentEconomics]
        C2[AgentState]
        C3[Market / Order]
        C4[WorldEventEffect]
        C5[RelationRecord]
    end

    subgraph External["Storage & External"]
        D1[ChromaDB<br>RAG Memory]
        D2[LLM Providers<br>OpenAI / Gemini / Grok / Ollama]
    end

    subgraph Frontend["Frontend · port 3000"]
        F1[React + Vite]
    end

    F1 -->|REST| A2
    F1 -->|WS| A3
    A1 --> A2
    A1 --> A3
    A2 --> B1
    A3 --> B1

    B1 --> B2
    B1 --> B3
    B1 --> B4
    B1 --> B5
    B1 --> B6
    B1 --> B7
    B1 --> B8

    B3 --> C1
    B3 --> C2
    B4 --> C3
    B5 --> C5
    B6 --> C4

    B3 --> D1
    B3 --> D2

    B2 -- manages --> B3
    B2 -- manages --> B4
    B2 -- manages --> B5
    B2 -- manages --> B6

    B6 -- triggers --> B3
    B6 -- triggers --> B4
    B6 -- triggers --> B5
```

---

## Simulation Loop

```mermaid
flowchart TD
    A[Load YAML Scenario] --> B[Validate Schema]
    B --> C[Initialize SimulationEnvironment]
    C --> D[Instantiate Agents + RAG Memory]
    D --> E[Initialize Markets & RelationGraph]
    E --> F{Epochs × Steps}

    F --> G[Apply Maintenance Costs]
    G --> H[Check Kill / Victory Conditions]
    H --> I[Agent Turns]
    I --> I1[LLM Reasoning + RAG Query]
    I1 --> I
    I --> J[Market Clearing]
    J --> K[Apply World Events]
    K --> K1[Shock / Trend / Conditional]
    K1 --> K
    K --> L[Update Trust & Relations]
    L --> M[Update Resource Portfolios]
    M --> N{More Steps?}
    N -- Yes --> G
    N -- No --> O{More Epochs?}
    O -- Yes --> F
    O -- No --> P[Collect Results & Logs]
    P --> Q[Expose via API / WebSocket]
```

---

## Module Responsibilities

| Module | Path | Responsibility |
|--------|------|----------------|
| **DoxaEngine** | `engine/DoxaEngine.py` | Top-level orchestrator. Owns all subsystems; validates config; drives the epoch/step loop. |
| **SimulationEnvironment** | `engine/SimulationEnvironment.py` | Tracks portfolios, pending trades, trade history, and RAG memory handles per agent. |
| **DoxaAgent** | `engine/agents/DoxaAgent.py` | Wraps AutoGen `ConversableAgent`. Registers tools, applies constraints, holds persona. |
| **AgentEconomics** | `engine/agents/AgentEconomics.py` | CRRA/CARA utility calculation, price-expectation EWA, liquidity-floor advisories. |
| **AgentState** | `engine/agents/AgentState.py` | Serialises agent state into the LLM context prompt. |
| **MarketEngine** | `engine/market/MarketEngine.py` | Manages all Market instances; routes orders; triggers clearing. |
| **Market** | `engine/market/Market.py` | Single LOB instrument: bid/ask book, FIFO matching, price history, market-maker quoting. |
| **Order** | `engine/market/Order.py` | Order dataclass (side, price, quantity, agent, status). |
| **RelationGraph** | `engine/relations/RelationGraph.py` | Directed weighted trust graph; updates, decay, reclassification, serialisation. |
| **RelationRecord** | `engine/relations/RelationRecord.py` | Single directed edge with trust score and label. |
| **WorldEventScheduler** | `engine/events/WorldEventScheduler.py` | Evaluates triggers each tick; dispatches effects via `WorldEventEffect`. |
| **WorldEventEffect** | `engine/events/WorldEventEffect.py` | Applies shock / trend / conditional effects to markets, portfolios, and trust. |
| **MacroTracker** | `engine/MacroTracker.py` | Computes Gini, HHI, price volatility, system panic; maintains history buffer. |
| **DoxaChatbot** | `engine/DoxaChatbot.py` | RAG-based Q&A assistant that queries the simulation's ChromaDB collections. |
| **ConsoleLogger** | `engine/utils/ConsoleLogger.py` | Structured in-process event bus; feeds the WebSocket event queue. |

---

## Data Flows

### Agent Decision Cycle

```
DoxaEngine.step()
  └─ DoxaAgent.run_turn()
       ├─ AgentState.build_prompt() → portfolio, prices, relations, tick
       ├─ LLM call (AutoGen)        → tool calls selected by the LLM
       └─ ToolDispatch
            ├─ place_buy_order / place_sell_order → MarketEngine
            ├─ make_trade_offer / accept / reject  → SimulationEnvironment
            ├─ operate (farm, mine …)              → SimulationEnvironment
            ├─ send_message / broadcast            → RelationGraph
            ├─ save_knowledge / query_knowledge    → ChromaDB
            └─ think / report                      → ConsoleLogger
```

### World Event Cascade

```
WorldEventScheduler.tick()
  └─ for each event:
       ├─ shock     → immediate one-time effect (price × multiplier, portfolio ± delta)
       ├─ trend     → repeated delta for N ticks
       └─ conditional → evaluates predicate; fires once when true
            └─ WorldEventEffect.apply()
                 ├─ market  → MarketEngine.set_price()
                 ├─ resource → SimulationEnvironment.portfolios[targets]
                 └─ trust    → RelationGraph.update()
```

---

## Directory Layout

```
server/
├── api.py                  FastAPI application + all endpoints
└── engine/
    ├── DoxaEngine.py       Orchestrator (≈1 200 lines)
    ├── SimulationEnvironment.py
    ├── MacroTracker.py
    ├── DoxaChatbot.py
    ├── agents/
    │   ├── DoxaAgent.py
    │   ├── AgentEconomics.py
    │   └── AgentState.py
    ├── market/
    │   ├── Market.py
    │   ├── MarketEngine.py
    │   └── Order.py
    ├── relations/
    │   ├── RelationGraph.py
    │   └── RelationRecord.py
    ├── events/
    │   ├── WorldEventScheduler.py
    │   └── WorldEventEffect.py
    └── utils/
        └── ConsoleLogger.py

client/
├── src/
│   ├── App.tsx
│   ├── api.ts              REST + WebSocket client helpers
│   ├── EventContext.tsx     Global event stream context
│   └── components/         Panel components
└── vite.config.ts
```
