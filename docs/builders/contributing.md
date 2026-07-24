# Contributing

Thank you for contributing to AITBC. This document describes the workflow for
platform builders.

## Local setup

1. Clone the repository.
2. Run `./venv/bin/python -m pytest tests/unit -q` to ensure a green baseline.
3. Use `./venv/bin/aitbc config set agent_coordinator_url <url>` to point the
   CLI at your coordinator.

## Making changes

- Follow the existing code style (ruff + mypy).
- Add or update unit tests in `tests/unit/`.
- Keep the release plan (`docs/releases/<version>/AGENTS.md`) up to date.

## Verification

Before submitting:

```bash
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Submitting a grant proposal

See `grants.md` for the DAO grant workflow.
