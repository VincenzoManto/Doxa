# Doxa Simulation — Complete YAML Configuration Reference

This document describes **every field** that the Doxa engine recognises in a
simulation YAML file, including default values, allowed values, constraints,
and cross-field relationships.

---

## Top-Level Structure

```yaml
global_rules:   { ... }   # Required — simulation-wide settings
actors:         [ ... ]   # Required — list of agent type definitions
world_events:   [ ... ]   # Optional — scheduled / conditional shocks & trends
```

---

## 1. `global_rules` (object, required)

Simulation-wide settings that apply to every agent unless an actor-level
key overrides them.

### 1.1 Simulation timing

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `epochs` | integer | `1` | Number of independent epochs to run. Each epoch resets all agent state; RAG memories are preserved across epochs. |
| `steps` | integer | `5` | Number of simulation steps per epoch. Each step = one full round of agent turns + market clearing + world events. |
| `execution_mode` | string | `sequential` | How agent turns are run within a step. `sequential` = one at a time (random order); `parallel` = all agents run concurrently via a thread pool. |

### 1.2 Maintenance costs

```yaml
global_rules:
  maintenance:
    corn: 2        # deducted from every agent's portfolio each step
    energy: 1
```

| Key | Type | Description |
|-----|------|-------------|
| `maintenance` | object | Maps resource names to numeric amounts that are subtracted from **every** agent's portfolio at the start of each step, before agent turns. A missing resource is treated as 0 before deduction. |

### 1.3 Kill conditions

```yaml
global_rules:
  kill_conditions:
    - resource: corn
      threshold: 0
```

Each entry is a condition object tested **after** maintenance.  An agent is
eliminated the first time **any** kill condition is met.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `resource` | string | Yes | Resource name to monitor. |
| `threshold` | number | Yes | Elimination threshold. The agent is killed when `resource ≤ threshold` (implicit operator `le`). |

> **Note:** Individual actors may also declare their own `kill_conditions`
> list; they are merged with the global list at runtime.

### 1.4 Victory conditions

```yaml
global_rules:
  victory_conditions:
    - resource: gold
      threshold: 34
      scope: global        # optional; default = global
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `resource` | string | — | Resource name to monitor. |
| `threshold` | number | — | Victory threshold (implicit operator `ge`). |
| `scope` | string | `global` | `individual` — only the acting agent's own quantity is checked. `global` — the sum of all portfolios is checked (triggers a `"GLOBAL"` victory event). |

> **Feasibility guard:** the engine raises a `ValueError` at config-load
> time if a victory condition can never be reached (initial total below
> threshold, no operations / events can grow the resource).

### 1.5 Global constraints

```yaml
global_rules:
  constraints:
    panic:
      min: 0.0
      max: 1.0
```

Applies to **all** agents.  Per-actor `constraints` are *merged on top*,
so actors can tighten but not completely remove a global constraint.

| Key | Type | Description |
|-----|------|-------------|
| `constraints` | object | Maps resource names to `{min, max}` bound objects. Both `min` and `max` are optional (default `-∞` / `+∞`). Any operation or OTC trade that would violate a bound is rolled back. |

### 1.6 Global operations

```yaml
global_rules:
  operations:
    build:
      input:
        wood: 5
        stone: 3
      output:
        house: 1
      target_impact:        # optional — effect on a second agent
        morale: 0.1
```

| Sub-key | Type | Description |
|---------|------|-------------|
| `input` | object | Resources consumed (must be ≥ 0 per unit). |
| `output` | object | Resources produced (must be ≥ 0 per unit). |
| `target_impact` | object | Optional delta applied to a **target** agent's portfolio (can be negative). The agent providing `target` as an argument to the operation triggers this effect. |

> All operations support an `inputMultiplier` argument (default `1`);
> all amounts are multiplied by it.

### 1.7 Markets

```yaml
global_rules:
  markets:
    - resource: gold
      currency: credits
      initial_price: 6.0
      min_price: 1.0
      max_price: 40.0
      clearing: per_step
      execution_price_policy: resting    # optional
      impact_factor: 0.0                 # optional
      market_order_slip: 0.1             # optional
      market_maker:                      # optional
        spread: 0.04
        depth: 10
        inventory_limit: 200
        inventory_skew: 0.5
```

Each entry configures one LOB (limit order book) instrument.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `resource` | string | Yes | — | The commodity being traded (must be declared in at least one `initial_portfolio`). |
| `currency` | string | Yes | — | Pricing denomination (must be declared in at least one `initial_portfolio`). |
| `initial_price` | number | No | `1.0` | Starting last-trade price. Must satisfy `min_price ≤ initial_price ≤ max_price`. |
| `min_price` | number | No | `0` | Hard floor; orders below this price are rejected. |
| `max_price` | number | No | `∞` | Hard ceiling; orders above this price are rejected. |
| `clearing` | string | No | `per_step` | When the book is matched: `per_step` — once per simulation step after all agent turns; `on_order` — immediately after every order submission; `call_auction` — uniform-price call auction, executed once per step. |
| `execution_price_policy` | string | No | `resting` | Price at which a match executes: `resting` — price of the order that arrived first (maker); `midpoint` — arithmetic mean of bid and ask; `aggressive` — price of the order that arrived second (taker). |
| `impact_factor` | number | No | `0.0` | Permanent price-impact multiplier. After a fill, the price shifts by `fill_qty / (remaining_depth + fill_qty) × impact_factor` in the trade direction. 0 = no impact. |
| `market_order_slip` | number | No | `0.1` | Slippage factor for market orders. Bid market orders are priced at `current_price × (1 + slip)`; ask at `current_price × (1 − slip)`. |

#### 1.7.1 `market_maker` sub-object (optional)

Configures a synthetic algorithmic market-maker that re-quotes each tick.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `spread` | number | `0.04` | Full bid-ask spread as a fraction of mid-price (e.g. `0.04` = 4%). Half-spread applied to each side. |
| `depth` | number | `10` | Units posted at each quote level (bid and ask). |
| `inventory_limit` | number | `200` | Maximum absolute inventory the MM will hold. Used to compute the inventory-skew adjustment. |
| `inventory_skew` | number | `0.5` | Fraction of the spread used to skew quotes when MM inventory is at its limit. Higher values = more aggressive mean-reversion of MM quotes. |

### 1.8 Relations

```yaml
global_rules:
  relations:
    - source: player
      target: miners
      trust: 0.68
      type: neutral
    - source: miners
      target: player
      trust: 0.58
      type: neutral
```

Pre-seeds the directional trust graph.  Relations not declared here start
at the default neutral trust (0.5).

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `source` | string | Yes | ID of the trusting agent. Must match a declared actor `id` (or replica ID). |
| `target` | string | Yes | ID of the trusted agent. |
| `trust` | number | No (default `0.5`) | Initial trust level in `[0, 1]`. 0 = complete distrust / enemy; 1 = complete trust / ally. |
| `type` | string | No (default `neutral`) | Relation label: `ally` \| `neutral` \| `rival` \| `enemy`. The engine auto-reclassifies this on every trust update, so treat the initial value as decorative. |

### 1.9 Relation dynamics

```yaml
global_rules:
  relation_dynamics:
    on_trade_success:
      trust_delta: 0.03
    on_trade_rejected:
      trust_delta: -0.02
    on_broadcast:
      trust_delta: 0.01
    trust_decay_rate: 0.01
    panic_decay_rate: 0.05
    portfolio_distress_panic_rate: 0.0   # optional
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `on_trade_success.trust_delta` | number | `0.03` | Trust change applied **bidirectionally** when an OTC trade is accepted and executed. |
| `on_trade_rejected.trust_delta` | number | `-0.02` | Trust change applied from the **rejector toward the proposer** when a trade is rejected. |
| `on_broadcast.trust_delta` | number | `0.01` | Trust boost applied from the broadcasting agent to every agent that receives the broadcast. |
| `trust_decay_rate` | number | `0.0` | Per-step decay toward neutral (0.5) applied to **all** trust edges after maintenance. |
| `panic_decay_rate` | number | `0.0` | Per-step reduction of the `panic` resource toward 0 applied to every agent after maintenance. |
| `portfolio_distress_panic_rate` | number | `0.0` | When > 0, agents whose total portfolio value dropped compared to the previous step gain `drop_fraction × distress_rate` panic each step. |

---

## 2. `actors` (array, required)

Each entry describes one agent type.  Use `replicas` to spawn multiple
identical agents.

### 2.1 Identity & LLM

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique base identifier. Must be unique across all actor entries. Replica IDs are `<id>_1`, `<id>_2`, … |
| `replicas` | integer | No | `1` | Number of identical agents to create from this definition. |
| `provider` | string | No | `ollama` | LLM provider: `ollama` \| `claude` \| `openai` \| `google` \| `grok`. |
| `model_name` (or `model`) | string | No | `llama3.1:8b` | Model name. For Google: `gemini-2.5-pro`, etc. |
| `api_key` | string | No | `""` | Provider API key. If omitted, the engine looks for `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `GROK_API_KEY` / `ANTHROPIC_API_KEY` /  in env vars and then the `.env` file. |
| `OLLAMA_URL` *(env var)* | string | No | `http://localhost:11434` | Base URL for the Ollama server. Set this env var to point agents at a remote or non-default Ollama instance. The `/v1` path is appended automatically. |  
| `base_url` | string | No | provider default | Custom endpoint URL. Useful for self-hosted models or proxies. |
| `temperature` | number | No | `0.1` | Direct LLM temperature control in `[0, 2]`. Lower values make the agent more deterministic; higher values make it more exploratory and erratic. |
| `irrationality` | number | No | unset | High-level behavior knob in `[0, 1]`. Mapped internally to temperature `[0.1, 1.3]`. Use this when you want to express how "irrational" an agent should be without thinking in provider-specific temperature terms. If both are present, `temperature` wins. |

```yaml
actors:
  - id: trend_a
    provider: google
    model_name: gemini-2.5-pro
    irrationality: 0.15

  - id: contrarian_a
    provider: google
    model_name: gemini-2.5-pro
    temperature: 0.85
```

### 2.2 Persona

```yaml
actors:
  - id: player
    persona: |
      Farmer-trader. Your core business is converting gold into corn.
      Keep enough corn to survive maintenance and monetize surplus.
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `persona` | string | No | Free-form system-prompt text prepended to every LLM call for this agent. Define the agent's strategic goals, personality, and any hard rules here. |

### 2.3 Portfolio

```yaml
actors:
  - id: player
    initial_portfolio:
      credits: 45
      corn: 12
      gold: 5
      panic: 0.0
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `initial_portfolio` | object | Yes | Starting resource quantities. Every resource used anywhere in the simulation (constraints, operations, markets, kill/victory conditions) should appear in at least one actor's portfolio. |

### 2.4 Constraints

```yaml
actors:
  - id: player
    constraints:
      gold:
        min: 0
      corn:
        min: 0
      credits:
        min: 0
      panic:
        min: 0.0
        max: 1.0
```

Per-actor overrides merged on top of `global_rules.constraints`.

| Key | Type | Description |
|-----|------|-------------|
| `constraints` | object | Maps resource names to `{min?, max?}` bound dicts. Operations and OTC trades that would violate a bound are **rolled back**. LOB orders check bounds at the time the reservation is made. |

### 2.5 Operations

Same schema as `global_rules.operations` but scoped to this actor only.

```yaml
actors:
  - id: player
    operations:
      farm:
        input:
          gold: 1
        output:
          corn: 4
```

### 2.6 Trading mode

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `trading_mode` | string | `otc` | Which trading channels are available: `otc` — OTC bilateral trades only (`make_trade_offer`, `accept_trade`, `reject_trade`); `lob` — limit-order-book only (`place_buy_order`, `place_sell_order`, market orders, `cancel_order`, `get_market_price`, `get_order_book`); `both` — both channels available simultaneously. |

### 2.7 Capability flags

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `can_trade` | boolean | `true` | If `false`, all trade-related tools are withheld from the agent. |
| `can_think` | boolean | `true` | If `false`, the `think` tool is withheld (the agent cannot log explicit thoughts). |
| `can_chat` | boolean | `true` | If `false`, `send_message` and `broadcast` are withheld. |
| `can_rag` | boolean | `true` | If `false`, RAG memory tools (`save_knowledge`, `query_knowledge`) are withheld and no ChromaDB collection is created for this agent. |
| `leader` | boolean | `false` | If `true`, the `assign_task` tool is available and `sub_agents` is populated. |
| `sub_agents` | list of strings | `[]` | IDs of agents this leader can delegate to. If empty and `leader=true`, all other agents are treated as sub-agents. |

### 2.8 Kill & victory conditions (actor-level)

Same schema as the global equivalents but scoped to this particular agent.
They are merged with global conditions at runtime.

```yaml
actors:
  - id: player
    kill_conditions:
      - resource: health
        threshold: 0
    victory_conditions:
      - resource: gold
        threshold: 50
        scope: individual
```

### 2.9 Economics (optional)

```yaml
actors:
  - id: player
    economics:
      utility: crra          # linear | crra | cara
      risk_aversion: 0.4     # γ (CRRA) or α (CARA); 0 = risk-neutral
      discount_factor: 0.95  # β ∈ (0, 1]
      liquidity_floor:
        credits: 10.0        # advisory warning threshold per resource
      price_expectation_window: 5
      learning_rate: 0.1
```

If omitted, all defaults produce linear, risk-neutral, no-floor behaviour.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `utility` | string | `linear` | Utility function. `linear` = wealth (sum of positive resource values); `crra` = Constant Relative Risk Aversion `W^(1-γ)/(1-γ)`; `cara` = Constant Absolute Risk Aversion `-e^(-αW)/α`. |
| `risk_aversion` | number | `0.0` | Risk-aversion parameter. For CRRA: γ (higher = more conservative). For CARA: α. 0 = risk-neutral. |
| `discount_factor` | number | `0.95` | Intertemporal patience β ∈ (0, 1]. Currently used for display / advisory; not yet applied to action selection. |
| `liquidity_floor` | object | `{}` | Maps resource names to minimum desired holdings. Displayed in the agent state prompt as an advisory warning (does **not** enforce a hard constraint). |
| `price_expectation_window` | integer | `5` | Rolling window length (in ticks) for the Exponentially Weighted Average (EWA) price expectation. |
| `learning_rate` | number | `0.1` | EWA blending factor λ. `new_exp = (1-λ) × old_exp + λ × current_price`. Higher = faster adaptation. |

---

## 3. `world_events` (array, optional)

List of events that modify portfolios, market prices, or trust edges
according to a trigger.

### 3.1 Common fields

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | Yes | Unique identifier used in API event records. |
| `type` | string | Yes | `shock` \| `trend` \| `conditional`. |
| `trigger` | object | Yes | When the event fires (see §3.2). |
| `effect` | object | Yes | What happens when the event fires (see §3.3). |
| `duration` | integer | No (trends only) | Number of consecutive ticks a `trend` stays active (default `1`). |

### 3.2 `trigger` sub-object

#### Tick-based (shock / trend)

```yaml
trigger:
  tick: 4      # fire on or after simulation tick 4
```

| Key | Type | Description |
|-----|------|-------------|
| `tick` | integer | Simulation tick (1-based step index within the epoch) at which the event first triggers. |

#### Condition-based (conditional / condition-started trend)

```yaml
trigger:
  condition:
    resource: corn
    operator: lt        # lt | gt | le | ge | eq
    threshold: 6
    scope: any_agent    # any_agent | all_agents
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `resource` | string | — | Resource to test. |
| `operator` | string | `lt` | Comparison operator: `lt` (<), `gt` (>), `le` (≤), `ge` (≥), `eq` (=). |
| `threshold` | number | — | Value to compare against. |
| `scope` | string | `any_agent` | `any_agent` — fires if **any** agent meets the condition; `all_agents` — all agents must meet it. |

### 3.3 `effect` sub-object

All fields are optional; multiple can be combined in one event.

#### Portfolio resource effect

```yaml
effect:
  targets: all       # "all" | agent id string | list of agent ids
  resource: panic
  delta: 0.3         # one-time change (shock / conditional)
  rate: 0.08         # per-step change (trend)
```

| Key | Type | Description |
|-----|------|-------------|
| `targets` | string \| list | `"all"` applies to all live agents; a single agent ID string or a list of IDs restricts the effect. |
| `resource` | string | Resource name to modify. |
| `delta` | number | One-time additive change. Used by `shock` and `conditional` events. |
| `rate` | number | Per-step additive change. Used by `trend` events; applied once per active tick. |

#### Market price effect

```yaml
effect:
  market: gold
  price_multiplier: 1.4    # multiply current price by this factor
  price_set: 10.0          # OR set to an exact value
```

| Key | Type | Description |
|-----|------|-------------|
| `market` | string | Resource name of the market to affect. |
| `price_multiplier` | number | Multiplies `market.current_price`. Result is clamped to `[min_price, max_price]`. |
| `price_set` | number | Sets `market.current_price` to an exact value (overrides `price_multiplier` if both present). |

#### Trust effect

```yaml
effect:
  trust_source: player
  trust_delta: 0.1
  targets: all
```

| Key | Type | Description |
|-----|------|-------------|
| `trust_source` | string | Source agent ID. All agents in `targets` receive a trust update **toward** this source. |
| `trust_delta` | number | Trust change applied to each `target → trust_source` edge. |

#### Contagion

```yaml
effect:
  targets: player
  resource: panic
  delta: 0.2
  contagion_rate: 0.3
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `contagion_rate` | number | `0.0` | Fraction of `delta`/`rate` propagated to each **trusted neighbour** of a target agent that is not itself in `targets`. The spread per neighbour is `base_amount × contagion_rate × trust(target → neighbour)`. |

---

## 4. Complete Example

```yaml
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
      Farmer-trader. Your core business is converting gold into corn.
      Keep enough corn to survive maintenance and monetize surplus.
    trading_mode: both
    initial_portfolio:
      credits: 45
      corn: 12
      gold: 5
      panic: 0.0
    constraints:
      gold:   { min: 0 }
      corn:   { min: 0 }
      credits: { min: 0 }
      panic:  { min: 0.0, max: 1.0 }
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
      Miner-merchant. Your core business is converting corn into gold.
      Check the LOB before trading OTC. Keep enough corn to keep mining.
    trading_mode: both
    initial_portfolio:
      credits: 55
      corn: 6
      gold: 16
      panic: 0.0
    constraints:
      gold:   { min: 0 }
      corn:   { min: 0 }
      credits: { min: 0 }
      panic:  { min: 0.0, max: 1.0 }
    operations:
      mine:
        input:
          corn: 2
        output:
          gold: 5
```

---

## 5. Validation Rules Summary

The engine runs `DoxaEngine._validate_config_dict()` at every config load.
Key checks:

| Rule | What is checked |
|------|----------------|
| Actor IDs unique | No two actors share the same `id`. |
| Known resources | Every resource referenced in constraints, operations, kill/victory conditions, markets, and world events must appear in at least one `initial_portfolio`. |
| Market resources | Both `resource` and `currency` of a market must be declared resources; no duplicate resource markets. |
| Market price bounds | `min_price ≤ initial_price ≤ max_price`; all numeric. |
| Market clearing mode | One of `per_step` \| `on_order` \| `call_auction`. |
| `execution_price_policy` | One of `resting` \| `midpoint` \| `aggressive`. |
| `impact_factor`, `market_order_slip` | Non-negative numbers if present. |
| `market_maker.*` | Non-negative numbers for `spread`, `depth`, `inventory_limit`, `inventory_skew`. |
| Relation references | Both `source` and `target` must resolve to a known agent ID; `trust` ∈ [0, 1]. |
| Operation amounts | All `input` and `output` amounts must be ≥ 0; `target_impact` amounts may be negative. |
| `trading_mode` | One of `otc` \| `lob` \| `both`. |
| `economics.utility` | One of `linear` \| `crra` \| `cara`. |
| `economics.risk_aversion` | ≥ 0. |
| `economics.discount_factor` | ∈ (0, 1]. |
| World event type | One of `shock` \| `trend` \| `conditional`. |
| Trend `duration` | Positive integer. |
| Condition operator | One of `lt` \| `gt` \| `le` \| `ge` \| `eq`. |
| World event `targets` | Must be `"all"` or a list/string of known agent IDs. |
| World event `market` | Must refer to a declared market resource. |
| World event `trust_source` | Must be a known agent ID. |
| Victory feasibility | If a resource cannot grow (no producing operation or event), a victory condition requiring more than the initial total is rejected. |


---

_Last updated: 2026-03-24_
