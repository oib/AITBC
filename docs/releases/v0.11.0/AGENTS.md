# v0.11.0 — Phase 4 & 2026 Roadmap Foundations

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Begin the 2026 product roadmap and Phase 4 success criteria:
OpenClaw autonomous economics, decentralized AI memory/storage, developer
ecosystem & DAO grants, and industry-specific compliance modules.

**Prerequisites**: v0.10.18 complete.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/agent_economics/`, `aitbc/agent_memory/`, `aitbc/compliance/`, shared types | Economic primitives, memory/storage types, compliance policy abstractions, Phase 4 gate definitions |
| **Agent B** | `apps/memory/`, `apps/coordinator-api` governance/developer domains, `cli/`, `scripts/security/` | Storage service, developer/grant APIs, CLI commands, cleanup verification |

---

## Agent A — Shared Core & Types

### A1: Phase 4 success criteria (P0)

- Document measurable Phase 4 gates in `docs/releases/v0.11.0/change.log`
  and the checklist below.
- Define baseline metrics in `docs/releases/v0.11.0/phase4_gates.yml` for:
  autonomous economic loop adoption, storage node coverage, grant disbursement
  correctness, compliance coverage, and test coverage.
- Add `scripts/ci/check_phase4_gates.py`; it reads the YAML gate definitions and
  exits non-zero if any P0 criterion is not met.

### A2: OpenClaw Autonomous Economics types (P0)

- File: `aitbc/agent_economics/__init__.py` (new)
- File: `aitbc/agent_economics/models.py` (new)
  - Budget, revenue route, pricing strategy, on-chain action data classes.
- File: `aitbc/agent_economics/errors.py` (new)
  - Domain exceptions for invalid budgets, routes, and strategies.

### A3: Decentralized AI Memory & Storage types (P1)

- File: `aitbc/agent_memory/__init__.py` (new)
- File: `aitbc/agent_memory/models.py` (new)
  - `ContentAddressedBlob`, `StorageLease`, `ReplicationProof`, and
    `EncryptionEnvelope` dataclasses.
- File: `aitbc/agent_memory/errors.py` (new)
  - Domain exceptions for missing or unauthorized blobs.

### A4: Industry-specific compliance abstractions (P2)

- File: `aitbc/compliance/__init__.py` (new)
- File: `aitbc/compliance/policies.py` (new)
  - `ComplianceFramework`, `DataClassification`, `Control`, and
    `CompliancePolicy` primitives plus `load_policy_template` for HIPAA,
    SOC2, GLBA, PCI-DSS, Manufacturing, Education, Retail, and Generic
    templates.
- File: `aitbc/compliance/audit.py` (new)
  - `ConsentRecord`, `RetentionPolicy`, `AuditEvent`, and helpers for
    classification sensitivity, retention expiry, and audit-event creation.
- File: `aitbc/compliance/errors.py` (new)
  - `ComplianceError`, `InvalidClassificationError`, `PolicyViolationError`.

---

## Agent B — Applications, CLI & Operations

### B1: `apps/memory` service skeleton (P1) — blocked pending Agent A A3

> `aitbc/agent_memory` shared models are not yet landed; B1 should start after A3.

- File: `apps/memory/src/memory_app/main.py` (new)
- File: `apps/memory/src/memory_app/api.py` (new)
  - `POST /store`, `GET /retrieve`, `GET /health`.
- File: `apps/memory/src/memory_app/config.py` (new)
  - Subclass `apps/shared-core/src/app/core/config.py` `ServiceSettings`.
- File: `apps/memory/src/memory_app/service.py` (new)
  - Content addressing, encryption-at-rest, and replication hooks.

### B2: Developer ecosystem & DAO grants (P1) — ✅ in progress / skeleton landed

- File: `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/grant.py` (new)
  - SQLModel `GrantProposal` and `GrantMilestone`.
- File: `apps/coordinator-api/src/coordinator_api/contexts/developer/` (new)
  - Developer registry domain and API.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Create `grant_proposal`, `grant_milestone`, and `developer` tables.

### B3: CLI extensions (P1) — ✅ in progress / commands landed

- File: `cli/aitbc_cli/commands/developer.py` (new)
  - `developer register`, `developer list`.
- File: `cli/aitbc_cli/commands/grant.py` (new)
  - `grant create`, `grant vote`, `grant disburse`, `grant list`.

### B4: Cleanup verification (P2)

- File: `scripts/security/scan_secrets.py` (new or update)
  - Enforce that no hardcoded API keys are added to the repo.
- File: `scripts/ci/check_deprecation_cleanup.sh` (new)
  - Grep for `AIPowerRental`, `light-theme`, and hardcoded API-key patterns.

### B5: Core capability verification (P1)

- File: `apps/edge/` (TBD)
  - Verify or complete Global Multi-Region Edge Nodes.
- File: `apps/gpu/` (TBD)
  - Verify or complete Dynamic GPU Priority Queuing.
- File: `aitbc/fusion/` (TBD)
  - Verify or complete Multi-Modal Fusion.
- Update core feature documentation with the "✅ COMPLETE" tag once verified.

### B6: API key onboarding & UI accessibility (P2)

- File: `cli/aitbc_cli/commands/config.py` (new or update)
  - `config check-keys` command that reports missing environment API keys.
- File: `docs/web/README.md` (TBD)
  - Document the dark-mode-only accessibility decision and any light-theme
    mitigation.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns the new `aitbc/` shared modules (`agent_economics`,
  `agent_memory`, `compliance`) and Phase 4 gate definitions.
- Agent B owns the new `apps/memory/` service, `apps/coordinator-api`
  developer/grant domains, CLI command groups, and cleanup scripts.
- Shared boundary: `aitbc/agent_memory/models.py` is consumed by
  `apps/memory`. Agent A writes the shared models first; Agent B builds the
  service against them.
- Sequence: Agent A lands shared types before Agent B begins service
  implementation.

## Release Gate

- [x] Phase 4 success criteria are defined and reviewed.
- [x] `aitbc/agent_economics` types compile and have unit tests.
- [x] `aitbc/agent_memory` models compile and have unit tests.
- [ ] `aitbc/agent_memory` models are consumed by `apps/memory`.
- [ ] `apps/memory` service starts and passes a health check.
- [ ] Developer registry and grant proposal SQLModels are created with a
      migration.
- [ ] CLI `developer` and `grant` commands are wired and smoke-tested.
- [x] Compliance policy helpers have unit coverage.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
