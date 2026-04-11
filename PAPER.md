# **Doxa: A Formal Multi-Agent Simulation Framework for Economic and Strategic Interaction**

## **Abstract**


We introduce **Doxa**, a formal computational framework for simulating decentralized economic systems populated by heterogeneous, AI-driven agents. The platform integrates **agent-based modeling**, **market microstructure**, and **dynamic game theory**, enabling the study of strategic interaction under bounded rationality.

Doxa is defined by a **declarative configuration language**, a deterministic simulation engine, and a modular architecture supporting endogenous communication, trust dynamics, and exogenous shocks. Agents are powered by large language models, enabling adaptive reasoning and negotiation in natural language.

We formalize the system as a **discrete-time stochastic game with endogenous network formation**, and demonstrate how equilibrium-like structures emerge from decentralized interactions rather than being imposed ex ante. The framework enables controlled experimentation in computational economics, mechanism design, and AI-driven markets.


---

## **1. Introduction**

The study of decentralized economic systems requires tools capable of modeling **heterogeneous agents**, **strategic interaction**, and **non-equilibrium dynamics**. Traditional frameworks in computational economics lack:

* flexible scenario specification
* endogenous communication and trust dynamics
* integration of modern AI reasoning capabilities

Doxa addresses these limitations by introducing a unified architecture where:

* agents are **strategic decision-makers**
* markets implement **explicit clearing mechanisms**
* interactions generate **emergent macro-level phenomena**

The system can be interpreted as a **computable economy** where agents solve constrained optimization problems under uncertainty, with incomplete information and evolving beliefs.

Classical approaches impose equilibrium assumptions. However, real systems operate **out of equilibrium**, with continuous adjustment driven by local decisions.

Doxa takes a different stance:

> Economic structure is not assumed. It is *generated*.

The framework enables simulation of:

* endogenous price formation
* trust-based coordination
* strategic negotiation under uncertainty

The key innovation is combining:

* formal economic structure
* programmable environments
* LLM-based agent cognition

---

## **2. Formal Model **


### **2.1 System Definition**

A Doxa simulation is defined as:

$$
\mathcal{D} = (\mathcal{A}, \mathcal{R}, \mathcal{M}, \mathcal{E}, \mathcal{T})
$$

where:

* ( $\mathcal{A}$ ): set of agents
* ( $\mathcal{R}$ ): resource space
* ( $\mathcal{M}$ ): markets
* ( $\mathcal{E}$ ): event processes
* ( $\mathcal{T}$ ): transition operator

Time is discrete: ( $t = 0,1,\dots,T$ )

---

### **2.2 Agent Structure**

Each agent ( $a \in \mathcal{A}$ ) is defined by:

$$
a = (P_a^t, U_a, \Sigma_a, \mathcal{B}_a^t, \Theta_a)
$$

where:

* ( $P_a^t \in \mathbb{R}_+^{|\mathcal{R}|}$ ): portfolio
* ( $U_a$ ): utility function
* ( $\Sigma_a$ ): strategy space
* ( $\mathcal{B}_a^t$ ): belief state
* ( $\Theta_a$ ): behavioral parameters

Agents, emergently, try to solve:

$$
\max_{\sigma_a \in \Sigma_a} \mathbb{E}\left[\sum_{t=0}^T \beta_a^t U_a(P_a^t)\right]
$$

subject to feasibility constraints. Agents are not guaranteed to solve this problem optimally, but it serves as a normative benchmark for their behavior. Their actions and thoughts are indeed emergent from their interactions with the environment and other agents, but constraints and incentives are designed to encourage them to approximate this optimization process.

The agent acts based on its current portfolio, beliefs, and the context of the environment, which includes market conditions and the actions of other agents. The strategy space ( $\Sigma_a$ ) encompasses all possible actions, including trading, communication, and resource transformation.

It is important to note that while agents are designed to be utility-maximizing, their actual behavior may deviate from this ideal due to bounded rationality, limited information, and the complexity of the environment or, more technically, based on inhereted stochastic elements of LLMs reasoning. This is where the integration of LLMs comes into play, allowing agents to use grasp the environment and make decisions in a more human-like, sometimes suboptimal way or apparently irrational, but still strategically coherent manner.

---

### **2.3 Bounded Rationality via LLMs**

Agents do not solve the optimization problem exactly.

Instead, decisions are approximated by:

$$
\sigma_a^t \sim \pi_{\theta}(P_a^t, \mathcal{B}_a^t, \text{context})
$$

where ( $\pi_{\theta}$ ) is an LLM-induced policy.

Implications:

* non-stationary strategies
* heuristic reasoning
* path dependence

This places Doxa in the class of **behavioral computational economies**.

---

### **2.4 Market Model**

Markets ( $m \in \mathcal{M}$ ) are defined as tuples:

$$
m = (r, c, \pi, \Pi, \kappa)
$$

where:

* ( $r$ ): traded resource
* ( $c$ ): numeraire (currency)
* ( $\pi$ ): price
* ( $\Pi$ ): price bounds
* ( $\kappa$ ): clearing mechanism

Supported mechanisms:

* continuous double auction (LOB)
* periodic clearing
* call auctions

Market makers implement:

$$
q^{bid/ask} = \pi \pm s + \kappa \cdot inventory
$$

introducing liquidity and stabilizing price dynamics.


#### **Clearing Mechanisms**

1. Continuous double auction
2. Batch clearing
3. Call auction

Matching function:

$$
\mathcal{M}: \mathcal{O}_t \rightarrow \text{Trades}_t
$$

where ( $\mathcal{O}_t$ ) is the set of orders at time ( $t$ ).



#### Production and Transformation**

Agents have production functions:

$$
f_a: \mathbb{R}_{*+}^{|\mathcal{R}|} \rightarrow \mathbb{R}_{*+}^{|\mathcal{R}|}
$$

Example:

$$
f_{farmer}(gold) = 4 \cdot corn
$$

This introduces:

* endogenous supply
* interdependence across agents

---

### **2.5 Game-Theoretic Interpretation**

The system defines a **dynamic stochastic game**:

* players: agents
* actions: trade, communicate, transform resources
* payoffs: utility over portfolios

At each timestep:

$$
G_t = (\mathcal{A}, \Sigma, U, T)
$$

where ( $T$ ) is the transition function induced by:

* market clearing
* agent actions
* world events

Equilibria are not imposed but **emerge dynamically**, allowing study of:

* bounded rational equilibria
* coordination failures
* market inefficiencies


#### **Event Process**

Events are stochastic processes:

$$
E_t \sim \mathcal{P}(E \mid S_t)
$$

State transition:

$$
S_{t+1} = \mathcal{T}(S_t, A_t, E_t)
$$

Events introduce:

* non-stationarity
* regime shifts
* exogenous shocks


#### **Equilibrium Concept**

Classical Nash equilibrium is intractable.

Instead, Doxa approximates:

* **behavioral equilibrium**
* **empirical stationary distributions**
* **policy convergence states**

---

### **2.6 Social and Trust Dynamics**

Relations form a weighted directed graph:

$$
G = (V, E), \quad E = \{(i,j,t_{ij})\}
$$

Trust evolves as:

$$
t_{ij}^{t+1} = (1 - \delta)t_{ij}^t + \Delta_{ij}
$$

where:

* ( $\delta$ ): decay rate
* ( $\Delta_{ij}$ ): event-driven update

Trust affects:

* probability of trade acceptance
* negotiation outcomes
* coalition formation


#### **Trust Network**

Define a directed weighted graph:

$$
G_t = (\mathcal{A}, E_t)
$$

with weights:

$$
t_{ij}^t \in [0,1]
$$

Update rule:

$$
t_{ij}^{t+1} = (1 - \delta)t_{ij}^t + \phi(\text{interaction})
$$

where ( $\delta$ ) is a decay factor and ( $\phi$ ) captures the impact of interactions (e.g., successful trade increases trust, failed negotiation decreases it).

Trust affects:

* probability of trade
* negotiation outcomes
* coalition formation

---

## **3. System Architecture**

Doxa implements a modular architecture:

### **Core Components**

* **Engine**: deterministic orchestrator of simulation dynamics
* **Environment**: state container (agents, portfolios, markets)
* **Agents**: decision units with LLM-based reasoning
* **Market Engine**: order matching and price formation
* **Event Scheduler**: exogenous shocks and trends
* **Relation Graph**: social structure

### **Execution Loop**

At each timestep:

1. Maintenance and constraint enforcement
2. Agent decision phase
3. Market clearing
4. Event execution
5. State update and logging

This defines a **discrete-time dynamical system**.

### **3.1 Engine Implementation**

The engine implements:

$$
S_{t+1} = \mathcal{T}(S_t)
$$

via the loop:

1. maintenance constraints
2. agent decisions
3. market clearing
4. event execution
5. belief update

### **Determinism**

Given:

* fixed YAML
* fixed seeds

the system is reproducible.

### **3.1 Declarative Scenario Specification**

Doxa uses a **YAML-based domain-specific language** enabling full reproducibility.

#### **Formal Structure**

A scenario is defined as:

$$
\mathcal{S} = (\mathcal{R}, \mathcal{A}, \mathcal{M}, \mathcal{E})
$$

where:

* ( $\mathcal{R}$ ): resources
* ( $\mathcal{A}$ ): agents
* ( $\mathcal{M}$ ): markets
* ( $\mathcal{E}$ ): events

This allows:

* deterministic replay
* parameter sweeps
* comparative statics

---

### **3.2 Event Dynamics and Exogenous Shocks**

Events introduce non-stationarity:

### Types:

* **Shock**: instantaneous perturbation
* **Trend**: persistent drift
* **Conditional**: state-triggered

Formally:

$$
P_{t+1} = f(P_t, A_t, E_t)
$$

where ( $E_t$ ) modifies transition dynamics.

This enables modeling of:

* supply shocks
* crises and panic
* policy interventions

---

### **3.3 Communication and Strategic Interaction**

Agents exchange structured messages:

$$
m = (i, j, \tau, payload)
$$

Protocols include:

* propose
* accept
* reject

This introduces:

* incomplete information
* signaling games
* negotiation equilibria

LLMs approximate reasoning under **bounded rationality**, enabling natural-language strategy formation.

---


## **4. Analytical Properties**

### **4.1 Existence of Feasible Paths**

Given constraint validation, there exists at least one feasible trajectory:

$$
\exists {S_t}_{t=0}^T
$$

---

### **4.2 Non-Equilibrium Dynamics**

The system does not guarantee convergence:

* cycles may emerge
* chaotic dynamics possible
* path dependence dominates

---

### **4.3 Emergent Price Formation**

Prices evolve as:

$$
\pi_{t+1} = \pi_t + \Delta(\text{order flow})
$$

No Walrasian auctioneer is assumed.

---

## **5. Experimental Design Framework**

Doxa enables controlled experiments:

### **Independent Variables**

* agent preferences
* market structure
* event processes

### **Dependent Variables**

* price volatility
* allocation efficiency
* network structure

### **Metrics**

* allocative efficiency
* Gini coefficient
* trade volume
* convergence speed

---

## **6. Case Study: Bilateral Production Economy**

Two-agent system:

* Agent A: transforms gold → corn
* Agent B: transforms corn → gold

### **Structure**

$$
A \leftrightarrow B
$$

This creates:

* mutual dependence
* endogenous trade necessity

### **Dynamics**

* shocks → price spikes
* scarcity → bargaining power shifts
* trust → trade friction

Equivalent to:

* a minimal general equilibrium model
* with production and strategic interaction

---

## **7. Applications**

### **Economic Research**

* market efficiency under bounded rationality
* liquidity crises
* price discovery

### **Game Theory**

* repeated games with communication
* endogenous coalition formation

### **AI Systems**

* emergent coordination
* language-mediated strategy

### **Policy**

* intervention testing
* systemic risk

---

## **8. Validation and Consistency Guarantees**

The system enforces:

* feasibility of constraints
* resource conservation
* market consistency
* reachability of objectives

This ensures simulations are:

* internally coherent
* economically meaningful
* reproducible

---


## **9. Limitations**

* no formal equilibrium guarantees
* scalability constraints
* dependence on LLM quality

Agents are:

* not fully rational
* not stationary
* sensitive to prompting

--- 

## **10. Conclusion**

Doxa reframes economic modeling as:

> a programmable, dynamic system of interacting agents

It eliminates:

* static equilibrium assumptions
* rigid analytical constraints

and replaces them with:

* simulation-based inference
* emergent structure
* adaptive behavior

This positions Doxa as a foundational tool for:

* computational economics
* AI-driven market design
* next-generation economic experimentation

Doxa represents a shift toward **programmable economic systems**, where:

* agents are autonomous and adaptive
* markets are explicitly modeled
* dynamics emerge from interaction

It bridges:

* agent-based modeling
* computational economics
* modern AI

The framework provides a foundation for studying **complex adaptive systems** where equilibrium is not assumed but **constructed through interaction**.

---

## **11. Future Works**

Critical directions:

### **1. Learning Agents**

Hybrid LLM + reinforcement learning:

$$
\pi_a = \lambda \pi_{LLM} + (1-\lambda)\pi_{RL}
$$

### **2. Mechanism Design Layer**

Design optimal markets:

$$
\max_{\kappa} ; \text{Efficiency}(\kappa)
$$

### **3. Distributed Simulation**

Scaling to ( $ 10^5+ $ ) agents

### **4. Formal Analysis**

* convergence proofs
* stability conditions
* equilibrium approximation bounds
* distributed simulation architecture
* endogenous learning (RL + LLM hybrid)
* mechanism design modules
* formal equilibrium analysis tools


