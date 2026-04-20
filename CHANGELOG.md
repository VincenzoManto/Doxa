# Changelog

## [0.1.0]

- Initial public pre-launch baseline

## [0.2.0]

- Added market microstructure primitives: limit order books, call auctions, synthetic market makers
- Added trust and relation graphs with decay dynamics
- Added world event scheduling and triggering
- Exposed REST and WebSocket APIs for all simulation primitives

## [0.3.0]


- Added optional API key authentication (`DOXA_API_KEY`) covering all REST endpoints and the WebSocket stream
- Added configurable CORS origins via `DOXA_CORS_ORIGINS` (defaults to localhost dev ports instead of `*`)
- Added secret redaction for `api_key`, `token`, `secret`, and `password` fields in all config-bearing API responses
- Restricted `POST /api/config/load` to `.yaml`/`.yml` files inside the `scenarios/` directory, preventing path traversal
- Fixed thread-safety races on `event_history` and `resource_history`: all mutations and reads now hold `_state_lock`
- Fixed `godmode` portfolio and constraint mutations to hold `env._lock`, consistent with the rest of the engine
- Removed accidental LLM API key logging (`print(llm_config)`) from agent initialisation
- Added Docker packaging for backend and frontend
- Added environment template for provider credentials
- Added CI workflow for server tests
- Added contributor onboarding files