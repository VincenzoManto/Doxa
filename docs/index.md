---
hide:
  - navigation
  - toc
---

<div class="hero">
  <div class="hero-inner">
    <h1 class="hero-title">Doxa</h1>
    <p class="hero-subtitle">
      A YAML-driven multi-agent simulation platform for economic and social dynamics.<br>
      Declare your world. Run your agents. Discover emergence.
    </p>
    <div class="hero-actions">
      <a href="quickstart/" class="md-button md-button--primary">Get Started</a>
      <a href="api/" class="md-button">API Reference</a>
      <a href="paper/" class="md-button">Read the Paper</a>
    </div>
  </div>
</div>

## Why Doxa?

Doxa combines LLM reasoning, limit-order-book microstructure, and social trust graphs into a
single declarative engine. Write one YAML file, hit run, and observe how macroeconomic structure
emerges from the decisions of heterogeneous, bounded-rational agents.

<div class="grid cards" markdown>

- :material-file-code-outline: **Declarative Scenarios**

    ---

    Define agents, markets, resources, operations, and world events in a single YAML file.
    No boilerplate, no setup code.

    [:octicons-arrow-right-24: YAML Reference](yaml-reference.md)

- :material-brain: **LLM-Powered Agents**

    ---

    OpenAI, Gemini, Grok, or Ollama. Each agent has a persona, hard constraints,
    tool access, and persistent RAG memory across epochs.

- :material-chart-candlestick: **Market Microstructure**

    ---

    Limit order books with FIFO matching, call auctions, and configurable synthetic
    market makers with inventory-skew quoting.

    [:octicons-arrow-right-24: Market config](yaml-reference.md)

- :material-graph: **Trust & Relation Graphs**

    ---

    Trust is a first-class primitive. It evolves via trades, broadcasts, and world
    events, then decays toward neutral each tick.

- :material-weather-lightning: **World Events**

    ---

    Schedule shocks, time-bound trends, and condition-triggered cascades that
    reshape prices, portfolios, and trust edges.

- :material-api: **REST + WebSocket API**

    ---

    Every simulation primitive is exposed. Poll via REST or stream a real-time
    event feed over WebSocket.

    [:octicons-arrow-right-24: API Reference](api.md)

</div>

---

## Quick Start

```bash
cp .env.example .env        # (1) add at least one provider key
docker compose up --build   # (2) backend :5000 · frontend :3000
```

1. Supported keys: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GROK_API_KEY`. Leave unused keys blank. For a fully local setup use Ollama — no key required.

See [Quick Start](quickstart.md) for local dev, Ollama-only, and bare-metal instructions.

### Additional: Pip installation & CLI

```bash
pip install doxa-ai
doxa run --help
```

---

## Example Scenarios

Six launch scenarios ship in `scenarios/`:

| Scenario | Domain | Agents | Markets |
|----------|--------|:------:|:-------:|
| [`hormuz.yaml`](scenarios.md#hormuz) | Economic / Market | 2 | gold, corn |
| [`financial-market.yaml`](scenarios.md#financial-market) | Finance / Microstructure | 6 | tech, bond |
| [`info-diffusion.yaml`](scenarios.md#info-diffusion) | Social / Information | 6 | — |
| [`resource-scarcity.yaml`](scenarios.md#resource-scarcity) | Conflict / Resources | 5 | — |
| [`policy-stress.yaml`](scenarios.md#policy-stress) | Macroeconomics / Policy | 7 | — |
| [`ai-negotiation.yaml`](scenarios.md#ai-negotiation) | Diplomacy / Strategic | 4 | — |

[:octicons-arrow-right-24: Browse all scenarios](scenarios.md)
