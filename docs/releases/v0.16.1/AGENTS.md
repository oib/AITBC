# v0.16.1 — Platform Builder Tooling (Phase 1: CLI, Registry & Grants)

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Improve the Platform Builder experience with a streamlined
CLI configuration tool, developer registry, DAO grants workflows, local
development helpers, and introductory builder documentation.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0–v0.15.2
planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/types/` (grants, developer registry) | Core types for developer profile and grant data models |
| **Agent B** | `cli/`, `docs/builders/`, `apps/coordinator-api` developer/grant domains, `scripts/dev/` | CLI config tool, builder docs, developer registry API, local dev helpers |

---

## Agent A — Shared Core & Types

### A1: Developer registry & grant types (P1)

- File: `aitbc/types/developer.py` (new)
  - `DeveloperProfile`, `ProjectListing`, `ReputationScore`.
- File: `aitbc/types/grant.py` (new or update)
  - `GrantProposal`, `GrantMilestone`, `DeveloperProfile` data classes.

---

## Agent B — Applications, CLI & Docs

### B1: CLI configuration tool (P0) — ✅ complete

- File: `cli/aitbc_cli/commands/config.py` (updated)
  - Added `config check` (reports missing env keys), `config set`, `config unset`.
- File: `cli/aitbc_cli/commands/bootstrap.py` (new)
  - `bootstrap-env` generates a starter `.env` and validates it with
    `cli/aitbc_cli/services/env_validator.py`.
- File: `cli/aitbc_cli/services/env_validator.py` (new)
  - Missing-key and secret-pattern validation.

### B2: Builder documentation (P1) — ✅ complete

- File: `docs/builders/getting-started.md` (new)
  - Install the CLI, configure the environment, register as a developer.
- File: `docs/builders/contributing.md` (new)
  - Local setup, code style, and verification commands.
- File: `docs/builders/grants.md` (new)
  - DAO grant workflow and milestone lifecycle.

### B3: Developer registry & DAO grants (P1) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/developer/` (new)
  - Developer registry domain, service, schemas, and API router.
- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/grant.py` (updated)
  - `GrantProposal` and `GrantMilestone` SQLModels with voting and disbursement.
- File: `apps/coordinator-api/alembic/versions/e8cc4d5738ef_add_grant_and_developer_tables.py` (existing)
  - Creates `developer`, `grant_proposal`, and `grant_milestone` tables.
- `tests/unit/test_v161_agent_b.py` covers developer registration and grant creation.

### B4: Local development helpers (P1) — ✅ complete

- File: `scripts/dev/start-local.sh` (new)
  - Spins up a minimal local coordinator with environment-driven config.
- File: `examples/builder/hello-agent/` (new)
  - Minimal example agent project (`main.py`, `README.md`).
- File: `tests/integration/fixtures/builder.py` (new)
  - Reusable `client`, `developer_payload`, and `grant_payload` fixtures.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/types/grant.py` and `aitbc/types/developer.py`.
- Agent B owns CLI commands, `apps/coordinator-api` developer/grant domains,
  and `docs/builders/`.
- Shared boundary: `aitbc/types/grant.py` and `aitbc/types/developer.py` are
  consumed by `apps/coordinator-api`; Agent A writes them first, then Agent B
  builds the SQLModels and API against them.
- Sequence: Agent A lands shared types before Agent B begins the coordinator-api
  implementation.

## Release Gate

- [x] `aitbc config check` reports missing env keys correctly.
- [x] `aitbc bootstrap-env` produces a valid starter `.env`.
- [x] Builder docs cover getting started, contributing, and grants.
- [x] Developer registry and grant proposal endpoints are testable.
- [x] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
