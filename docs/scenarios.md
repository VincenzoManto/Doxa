# Scenarios

Doxa ships with six pre-built scenarios in the `scenarios/` directory.
Each is a self-contained YAML file you can load via the UI or the API.

---

## hormuz { #hormuz }

<span class="tag tag-economic">Economic</span>
<span class="tag tag-market">Market</span>

**File:** `scenarios/hormuz.yaml` · **Agents:** 2 · **Markets:** gold, corn

A bilateral farmer-miner economy. The farmer converts gold into corn; the miner converts corn
into gold. Both agents have access to the LOB and to OTC negotiation.

World shocks stress-test market resilience and trust dynamics:

- `gold_spike` — price multiplier shock at tick 4  
- `corn_shortage` — supply shock at tick 6  
- `panic_wave` — 3-tick panic trend starting tick 2  
- `food_relief` — conditional corn injection when any agent drops below 6 corn  

**Good for:** price discovery, bilateral OTC vs. LOB comparison, trust-and-trade coupling.

---

## financial-market { #financial-market }

<span class="tag tag-market">Market</span>
<span class="tag tag-economic">Finance</span>

**File:** `scenarios/financial-market.yaml` · **Agents:** 6 · **Markets:** tech, bond

Six traders — two trend-followers, two contrarians, two arbitrageurs — compete across two
correlated LOB markets.

This scenario is also a good baseline for tuning agent rationality: lower `irrationality`
keeps an actor more disciplined, while higher values make quotes and choices noisier.

**Good for:** price discovery dynamics, spread formation, emergent order-flow imbalance,
cross-market arbitrage.

---

## info-diffusion { #info-diffusion }

<span class="tag tag-social">Social</span>

**File:** `scenarios/info-diffusion.yaml` · **Agents:** 6 · **Markets:** none

A misinformation propagation scenario. An influencer broadcasts false information; a journalist
investigates; a fact-checker corrects; a regulator intervenes. Retail agents A and B receive
mixed signals.

**Resources:** `panic`, `credibility` (no trading).

**Good for:** trust decay and recovery under information shocks, regulatory intervention
modelling, social contagion dynamics.

---

## resource-scarcity { #resource-scarcity }

<span class="tag tag-conflict">Conflict</span>

**File:** `scenarios/resource-scarcity.yaml` · **Agents:** 5 · **Markets:** none  
**Kill conditions:** `water < 0`, `food < 0`

Two villages, a farming collective, an engineering group, and a militia compete over water and
food during a progressive drought. The militia can enforce or disrupt resource distribution.

Kill conditions make this scenario high-stakes: any agent that runs out of water or food is
eliminated.

**Good for:** cooperation vs. defection under scarcity, power-asymmetry modelling, conflict onset.

---

## policy-stress { #policy-stress }

<span class="tag tag-policy">Policy</span>

**File:** `scenarios/policy-stress.yaml` · **Agents:** 7 · **Markets:** none  
**Trading:** OTC only (`can_trade: false` on LOB)

A central bank, three commercial banks, and three firms face a sudden liquidity shock. The
central bank issues emergency liquidity; banks must decide how to transmit it to firms.

**Good for:** monetary policy transmission, hoarding and fragility under stress, systemic risk.

---

## ai-negotiation { #ai-negotiation }

<span class="tag tag-diplomacy">Diplomacy</span>

**File:** `scenarios/ai-negotiation.yaml` · **Agents:** 4 · **Markets:** none  
**Resources:** `security`, `diplomatic_capital`

Four state-like agents (Aurora, Borealis, Cygnus, Draco) manage security and diplomatic capital.
A border-incident shock destabilises trust. Agents must negotiate treaties and signal deterrence.

**Good for:** coalition formation, deterrence modelling, equilibrium emergence from language-mediated
strategic interaction.

---

## Loading a Scenario

=== "Via UI"

    Open `http://localhost:3000`, click **Load Scenario**, and pick a file from the
    `scenarios/` directory.

=== "Via API — load from path"

    ```bash
    curl -X POST http://localhost:5000/api/config/load \
      -H "Content-Type: application/json" \
      -d '{"path": "/absolute/path/to/scenarios/hormuz.yaml"}'
    ```

=== "Via API — validate first"

    ```bash
    YAML=$(cat scenarios/hormuz.yaml)
    curl -X POST http://localhost:5000/api/config/validate \
      -H "Content-Type: application/json" \
      -d "{\"yaml_text\": $(echo "$YAML" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}"
    ```

---

## Writing Your Own

Create a `.yaml` file anywhere and load it via the API or UI.
See the [YAML Reference](yaml-reference.md) for all available fields and defaults.

!!! tip "Start from a template"
    Copy `scenarios/hormuz.yaml` as a baseline. It exercises every major feature:
    markets, relations, world events, operations, kill conditions, and victory conditions.
