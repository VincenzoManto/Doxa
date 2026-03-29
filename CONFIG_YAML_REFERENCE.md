# Configuration YAML Reference for NexusSimulationEnv

This document describes all the properties available in the configuration YAML used by the simulator.

---

## Top-Level Structure

```yaml
global_rules:
  ...
actors:
  - ...
```

---

## global_rules (object)
Defines the global simulation rules and parameters.

### Properties:
- **running_mode** (`string`, default: `'sequential'`)
  - How turns are executed. Supported: `'sequential'`, `'simultaneous'`.
- **max_history_context** (`integer`, default: `20`)
  - Maximum number of messages kept in each agent's history.
- **steps** (`integer`, default: `10`)
  - Number of turns/steps to run the simulation.
- **can_create_resources** (`boolean`, default: `false`)
  - If true, agents can create new resources (feature stub).
- **can_signal_relations** (`boolean`, default: `false`)
  - If true, agents can signal relationships (feature stub).
- **maintenance** (`object`, optional)
  - Defines maintenance costs and penalties for agents each turn.
    - **cost** (`object`): Resource costs per turn (e.g., `{energy: 2}`)
    - **penalty** (`object`): Penalties if cost can't be paid (e.g., `{credits: -150}`)
- **operations** (`object`, optional)
  - Global operations available to all agents. Each key is an operation name, value is an object:
    - **input** (`object`): Resources required to perform the operation.
    - **output** (`object`): Resources produced by the operation.

---

## actors (array of objects)
Defines the list of agent types/groups in the simulation.

### Each actor object must have:
- **id** (`string`)
  - Unique identifier for the agent/group.
- **persona** (`string`)
  - Description of the agent's role/behavior.
- **initial_portfolio** (`object`)
  - Starting resources for the agent (e.g., `{credits: 100, energy: 100}`)

### Optional properties for each actor:
- **replicas** (`integer`, default: `1`)
  - Number of identical agents to create from this definition.
- **propensities** (`object`, optional)
  - Weights for agent behavior (e.g., `{THINK: 100, TRADE: 80, MSG: 20}`)
- **operations** (`object`, optional)
  - Custom operations available only to this agent/group (same structure as global operations).
- **provider** (`string`, default: `'genai'`)
  - LLM provider for this agent (`'genai'`, `'openai'`, `'ollama'`).
- **model_name** (`string`, optional)
  - Model name for the LLM provider.
- **api_key** (`string`, optional)
  - API key for the LLM provider (if needed).
- **base_url** (`string`, optional)
  - Base URL for the LLM provider (for custom endpoints).

---

## Example

```yaml
global_rules:
  running_mode: 'simultaneous'
  max_history_context: 10
  steps: 5
  can_create_resources: false
  can_signal_relations: false
  maintenance:
    cost: {energy: 2}
    penalty: {credits: -150}

actors:
  - id: 'mindless_drone'
    replicas: 2
    persona: 'A simple worker bot. Does not think, just broadcasts status and seeking trade.'
    initial_portfolio: {credits: 100, energy: 100}
    propensities: {THINK: 0, BCAST: 100, TRADE: 60}
    operations:
      work:
        input: {energy: 5}
        output: {credits: 20}

  - id: 'strategist'
    persona: 'A deep thinker evaluating the market. Needs to hoard credits.'
    initial_portfolio: {credits: 1000, energy: 500}
    propensities: {THINK: 100, TRADE: 80, MSG: 20}
```

---

_Last updated: 2026-03-24_
