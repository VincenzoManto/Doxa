# NexusSimulationEnv & Geopolitical Simulator - Developer Notes

## 1. Error Handling & Robustness

### Configuration Validation
- The simulator now validates the YAML configuration at startup.
- Required keys: `global_rules`, `actors`.
- Each actor must have: `id`, `persona`, `initial_portfolio` (as dict).
- Raises `ValueError` with a clear message if validation fails.

### LLM Error Handling
- All LLM (language model) errors are logged via `RealtimeLogger`.
- If an LLM call fails, the agent receives a system broadcast action with the error.

### Action Validation
- Every action is checked before execution:
  - Must be a string.
  - Must start with `ACT:`.
- Raises `ValueError` if an agent returns an invalid action.

---

## 7. Scalability (Design Notes)

### Current State
- The simulator supports multiple agents and can be configured for several turns.
- Each agent/player is handled in a loop; the environment is designed for extension.

### Recommendations for Scalability
- **Optimize Data Structures**: Use efficient dict/list operations for large numbers of agents.
- **Parallel Execution**: For truly simultaneous turns, consider multiprocessing/threading for agent actions.
- **Batch LLM Calls**: If using cloud LLMs, batch requests where possible to reduce latency.
- **Resource Management**: Monitor memory and CPU usage if scaling to hundreds of agents.
- **Profiling**: Use Python profiling tools to identify bottlenecks.

---

## 9. Documentation

### How to Extend
- Add new actions by extending the parsing logic in `step_all`.
- Add new agent types by subclassing `Player`.
- Add new environment rules in the YAML config and handle them in `NexusSimulationEnv`.

### Example Config
See the bottom of `engine.py` for a YAML scenario example.

### Error Messages
- All validation and runtime errors are logged and surfaced to the user/console.

### Further Reading
- See docstrings in the code for method-level documentation.
- For advanced usage, consider adding more docstrings and usage examples.

---

_Last updated: 2026-03-24_
