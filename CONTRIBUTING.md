# Contributing

Thanks for contributing to Doxa.

## Before You Start

- Read [CONFIG_YAML_REFERENCE.md](CONFIG_YAML_REFERENCE.md) before proposing new scenario fields.
- Keep changes focused. Avoid bundling unrelated refactors into the same pull request.
- If you add new YAML configuration properties, document them in `CONFIG_YAML_REFERENCE.md`.

## Reporting Bugs

When opening a bug report, include:

- A short summary of the problem
- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant YAML scenario
- Python version, Node version, and OS
- Logs or stack traces if available

## Proposing Features

For feature requests, describe:

- The use case
- Why the current behavior is insufficient
- The proposed API or YAML shape
- Alternatives you considered

## Development Setup

### Backend

```bash
cd server
pip install -r requirements-dev.txt
```

### Frontend

```bash
cd client
npm install
```

## Running Tests

```bash
cd server
pytest tests -v
```

## Code Style

- Python: prefer clear, typed code and keep modules cohesive.
- Frontend: follow the existing React and TypeScript patterns in `client/src`.
- Preserve public API behavior unless the change explicitly requires it.
- Add tests for bug fixes and new behavior whenever practical.

## Pull Requests

Before opening a PR:

1. Rebase or merge from the target branch.
2. Run the relevant tests locally.
3. Update docs when behavior or configuration changes.
4. Keep the PR description specific about the problem and the fix.

By contributing, you agree that your contributions are compatible with the repository license in [LICENSE](LICENSE).