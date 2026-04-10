# Doxa: A Multi-Agent Simulation Platform for Economic and Social Dynamics

### 2026

#### Vincenzo Manto, Riccardo Dal Cero

## Introduction

Multi-agent simulation is a cornerstone of computational social science,
economics, and artificial intelligence. Doxa addresses the need for a
flexible, reproducible, and extensible platform that enables researchers
to model complex agent interactions, market mechanisms, and world
events, leveraging modern AI models for agent reasoning. This paper
details the Doxa platform, its YAML-driven configuration, and its
application to economic and social simulation.

## Related Work

Agent-based modeling has a long tradition, with platforms such as
NetLogo, MASON, and Repast. Recent advances integrate AI and machine
learning for agent reasoning (e.g., OpenAI Gym, PettingZoo). Doxa
distinguishes itself by combining declarative scenario modeling,
generative AI integration, and a rich economic/market simulation
toolkit, all accessible via a modern API.

## System Overview

Doxa consists of a Python backend (DoxaEngine) and a web API server
(FastAPI), exposing REST and WebSocket endpoints. Scenarios are
specified in a single YAML file, which defines global rules, agent
types, resources, markets, and world events. The engine parses this
schema, instantiates agents, manages state, and orchestrates simulation
steps. Agents are parameterized by persona, resource portfolio,
behavioral rules, and can be linked to LLM providers (OpenAI, Google,
Ollama, etc.).

## YAML Scenario Schema {#sec:schema}

The scenario YAML file is the core of Doxa's reproducibility and
flexibility. It defines:

-   **global_rules**: Simulation-wide settings (timing, maintenance,
    kill/victory conditions, constraints, operations, markets,
    relations, dynamics).

-   **actors**: List of agent types, each with identity, persona,
    initial portfolio, constraints, operations, trading mode, and
    economic parameters.

-   **world_events**: Optional list of scheduled or conditional events
    that affect resources, markets, or trust.

See Section [10](#sec:case-study){reference-type="ref"
reference="sec:case-study"} for a concrete example (hormuz.yaml).

## Engine Architecture {#sec:engine}

The Doxa engine is organized into modular subsystems, each responsible
for a core aspect of the simulation. The main components are described
below, with references to the codebase (`server/engine/`) and YAML
schema fields.

### Economic Subsystem

The economic logic of each agent is governed by the `AgentEconomics`
module and the economic parameters defined in the YAML (e.g., utility
function, risk aversion, discount factor). Agents can be risk-neutral or
risk-averse (CRRA, CARA), and their decision-making incorporates
liquidity preferences and price expectations. The economic subsystem
ensures that agent actions (trades, operations) are consistent with
their economic profile, and computes utility and risk metrics for
analysis.

### Market Subsystem

Markets are managed by the `MarketEngine` and `Market` classes. Doxa
supports both over-the-counter (OTC) bilateral trades and centralized
limit order books (LOBs) for each resource. Market configuration is
fully declarative in YAML, including price bounds, clearing modes (per
step, on order, call auction), and synthetic market makers (with
configurable spread, depth, and inventory skew). The market subsystem
matches orders, applies price impact, and enforces slippage and
constraints, providing a realistic trading environment for agents.

### Relations Subsystem

Social and trust relations are modeled as a directed, weighted graph
managed by the `RelationGraph` and `RelationRecord` modules. Initial
trust levels and relation types (ally, neutral, rival, enemy) are seeded
from YAML. Trust dynamics are updated in response to agent actions
(successful/rejected trades, broadcasts) and world events, with support
for trust decay and contagion. Relations influence agent
decision-making, negotiation, and the spread of events (e.g., panic
contagion).

### Communication Subsystem

Agents interact via private messages, public broadcasts, and negotiation
protocols. The `DoxaAgent` class registers communication tools (send
message, broadcast, propose trade, accept/reject trade) based on agent
capabilities. Communication is event-driven and can trigger trust
updates or world events. The communication subsystem is extensible,
allowing custom tools to be defined in the YAML scenario.

### Resource Management

Resources are the fundamental quantities tracked in agent portfolios and
markets. The `SimulationEnvironment` maintains the state of all
resources, applies maintenance costs, and enforces constraints (min/max
bounds) at both global and agent levels. Resource transfers occur via
operations, trades, market transactions, and world events. The engine
ensures that all resource changes are validated and rolled back if
constraints are violated.

### Events Subsystem

World events are managed by the `WorldEventScheduler` and
`WorldEventEffect` modules. Events can be scheduled (shocks, trends) or
triggered by conditions (resource thresholds, agent states). Effects
include resource changes, market price shifts, trust updates, and
contagion. The event subsystem supports complex, multi-step event logic,
enabling rich scenario evolution and exogenous shocks.

### API and Integration

The API layer is implemented using FastAPI and exposes both REST and
WebSocket endpoints. The REST API provides scenario management,
simulation control, and data retrieval. The WebSocket endpoints
(`/ws/agents`, `/ws/resources`) enable real-time streaming of agent
actions, resource updates, and chat. The API is designed for integration
with custom frontends, dashboards, and external controllers, supporting
both synchronous and asynchronous workflows.

## Agent Model and Reasoning

Agents in Doxa are autonomous, configurable entities. Each agent is
defined by a persona, initial resources, constraints, and a set of
operations. Agents can communicate, negotiate, trade (OTC and LOB),
reason internally, and manage persistent vector memory (RAG via
ChromaDB). Hierarchical organization (leaders and sub-agents) is
supported. LLM integration enables advanced reasoning and language-based
interaction.

## Market and Economic Simulation

Doxa supports both OTC and limit order book (LOB) trading, with
configurable market parameters (price bounds, clearing modes, market
makers). Economic behavior is further shaped by agent-level utility
functions, risk aversion, and liquidity preferences. The engine enforces
constraints and rollbacks for infeasible operations.

## World Events and Dynamics

World events can be scheduled (shocks, trends) or triggered by
conditions (e.g., resource thresholds). Effects include resource
changes, market price shifts, trust updates, and contagion. The YAML
schema supports complex event logic, enabling rich scenario evolution.

## API and Integration

The backend exposes a REST API and two WebSocket endpoints: `/ws/agents`
for real-time agent actions, chat, and portfolio management;
`/ws/resources` for real-time resource updates. This enables integration
with custom frontends, dashboards, or external controllers.

## Scenario Design: Case Study {#sec:case-study}

As a concrete example,
Listing [\[lst:hormuz\]](#lst:hormuz){reference-type="ref"
reference="lst:hormuz"} shows the YAML for the "hormuz" scenario,
featuring two agent types (player, miners), two resources (gold, corn),
and a set of world events and market rules.

``` {#lst:hormuz .yaml language="yaml" caption="Excerpt from hormuz.yaml" label="lst:hormuz"}
global_rules:
  epochs: 1
  steps: 12
  execution_mode: sequential
  maintenance:
    corn: 2
  kill_conditions:
    - resource: corn
      threshold: 0
  victory_conditions:
    - resource: gold
      threshold: 34
  relation_dynamics:
    on_trade_success:
      trust_delta: 0.03
    on_trade_rejected:
      trust_delta: -0.02
    on_broadcast:
      trust_delta: 0.01
    trust_decay_rate: 0.01
    panic_decay_rate: 0.05
  relations:
    - source: player
      target: miners
      trust: 0.68
      type: neutral
    - source: miners
      target: player
      trust: 0.58
      type: neutral
  markets:
    - resource: gold
      currency: credits
      initial_price: 6.0
      min_price: 1.0
      max_price: 40.0
      clearing: per_step
    - resource: corn
      currency: credits
      initial_price: 2.4
      min_price: 0.5
      max_price: 15.0
      clearing: per_step
world_events:
  - name: gold_spike
    type: shock
    trigger:
      tick: 4
    effect:
      market: gold
      price_multiplier: 1.4
  - name: corn_shortage
    type: shock
    trigger:
      tick: 6
    effect:
      market: corn
      price_multiplier: 1.35
  - name: panic_wave
    type: trend
    trigger:
      tick: 2
    duration: 3
    effect:
      targets: all
      resource: panic
      rate: 0.08
  - name: food_relief
    type: conditional
    trigger:
      condition:
        resource: corn
        operator: lt
        threshold: 6
        scope: any_agent
    effect:
      targets: all
      resource: corn
      delta: 3
actors:
  - id: player
    provider: google
    model_name: gemini-2.5-pro
    persona: |
      Farmer-trader. Your core business is converting gold into corn. Keep enough corn to survive maintenance and monetize surplus.
    trading_mode: both
    initial_portfolio:
      credits: 45
      corn: 12
      gold: 5
      panic: 0.0
    constraints:
      gold:
        min: 0
      corn:
        min: 0
      credits:
        min: 0
      panic:
        min: 0
        max: 1
    operations:
      farm:
        input:
          gold: 1
        output:
          corn: 4
  - id: miners
    provider: google
    model_name: gemini-2.5-pro
    persona: |
      Miner-merchant. Your core business is converting corn into gold. Prefer the exchange over OTC: check the corn and gold books, post bids for corn before you run short, post asks for gold when inventory is ample, and use direct negotiation only when the book is empty or a bilateral trade is clearly better. Keep enough corn to continue mining.
    trading_mode: both
    initial_portfolio:
      credits: 55
      corn: 6
      gold: 16
      panic: 0.0
    constraints:
      gold:
        min: 0
      corn:
        min: 0
      credits:
        min: 0
      panic:
        min: 0
        max: 1
    operations:
      mine:
        input:
          corn: 2
        output:
          gold: 5
```

## Experiments and Results

## Discussion and Limitations

## Conclusion

Doxa provides a robust, extensible platform for multi-agent simulation,
integrating economic, social, and AI-driven reasoning. Its YAML-based
configuration, modular engine, and API make it suitable for a wide range
of research applications.

## References {#references .unnumbered}
