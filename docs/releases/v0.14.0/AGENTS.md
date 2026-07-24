# v0.14.0 — Platform Builder Tooling

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Improve the Platform Builder experience with SDKs, how-to
guides, a streamlined CLI configuration tool, and developer ecosystem/DAO
grants workflows.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0 and v0.13.0
planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/` shared types (agent identity, grants, developer registry) | Core types for SDK, developer profile, and grant data models |
| **Agent B** | `cli/`, `packages/py/aitbc-sdk/`, `docs/builders/`, `apps/coordinator-api` developer/grant domains, `scripts/dev/` | CLI config tool, SDK package, builder docs, developer registry API, local dev helpers |

---

## Agent A — Shared Core & Types

### A1: SDK shared types (P1)

- File: `aitbc/types/sdk.py` (new)
  - Lightweight request/response models for the SDK client.
- File: `aitbc/types/grant.py` (new or update)
  - `GrantProposal`, `GrantMilestone`, `DeveloperProfile` data classes.

### A2: Developer registry types (P2)

- File: `aitbc/types/developer.py` (new)
  - `DeveloperProfile`, `ProjectListing`, `ReputationScore`.

---

## Agent B — Applications, CLI, SDK & Docs

### B1: CLI configuration tool (P0)

- File: `cli/aitbc_cli/commands/config.py` (new or update)
  - `config check`, `config set`, `config unset`.
- File: `cli/aitbc_cli/commands/bootstrap.py` (new)
  - `bootstrap-env` to generate a starter `.env` and validate it.
- File: `cli/aitbc_cli/services/env_validator.py` (new)
  - Missing-key and secret-pattern validation.

### B2: SDK package (P1)

- File: `packages/py/aitbc-sdk/pyproject.toml` (new)
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/__init__.py` (new)
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/client.py` (new)
  - High-level coordinator-api, wallet, and registry clients.
- File: `packages/py/aitbc-sdk/src/aitbc_sdk/retry.py` (new)
  - Shared retry and circuit-breaker helpers.

### B3: Builder documentation (P1)

- File: `docs/builders/getting-started.md` (new)
- File: `docs/builders/sdk-reference.md` (new)
- File: `docs/builders/contributing.md` (new)
- File: `docs/builders/grants.md` (new)

### B4: Developer registry & DAO grants (P2)

- File: `apps/coordinator-api/src/coordinator_api/contexts/developer/` (new)
  - Developer registry domain and API.
- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/grant.py` (new or update)
  - `GrantProposal` and `GrantMilestone` SQLModels.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Create `developer`, `grant_proposal`, and `grant_milestone` tables.

### B5: Local development helpers (P2)

- File: `scripts/dev/start-local.sh` (new)
  - Spin up a minimal local node + coordinator + wallet.
- File: `examples/builder/hello-agent/` (new)
  - Minimal example agent project.
- File: `tests/integration/fixtures/builder.py` (new)
  - Reusable builder fixtures.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/types/sdk.py`, `aitbc/types/grant.py`, and
  `aitbc/types/developer.py`.
- Agent B owns the `packages/py/aitbc-sdk/` package, CLI commands,
  `apps/coordinator-api` developer/grant domains, and `docs/builders/`.
- Shared boundary: `aitbc/types/grant.py` and `aitbc/types/developer.py` are
  consumed by `apps/coordinator-api`; Agent A writes them first, then Agent B
  builds the SQLModels and API against them.
- Sequence: Agent A lands shared types before Agent B begins the SDK and
  coordinator-api implementation.

## Release Gate

- [ ] `aitbc config check` reports missing env keys correctly.
- [ ] `aitbc bootstrap-env` produces a valid starter `.env`.
- [ ] `aitbc-sdk` package installs and exposes a coordinator-api client.
- [ ] Builder docs cover getting started, SDK reference, contributing, and
      grants.
- [ ] Developer registry and grant proposal endpoints are testable.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
