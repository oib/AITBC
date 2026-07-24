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

### A1: Phase 4 success criteria (P0) — ✅ defined

- File: `docs/releases/v0.11.0/phase4_gates.yml` (updated)
  - Baseline metrics defined for all five P0 gates.
  - `compliance_coverage` and `test_coverage` are `status: passed`
    (50.61% shared-core test coverage, 100% policy-template coverage).
  - Operational gates (`autonomous_economic_loop_adoption`,
    `storage_node_coverage`, `grant_disbursement_correctness`) are
    `status: pending` until network metrics are available.
- File: `scripts/ci/check_phase4_gates.py` (new)
  - Reads `phase4_gates.yml` and exits non-zero if any gate is not met.

### A2: OpenClaw Autonomous Economics types (P0) — ✅ complete

- File: `aitbc/agent_economics/__init__.py` (new)
- File: `aitbc/agent_economics/models.py` (new)
  - Budget, revenue route, pricing strategy, on-chain action data classes.
- File: `aitbc/agent_economics/errors.py` (new)
  - Domain exceptions for invalid budgets, routes, and strategies.

### A3: Decentralized AI Memory & Storage types (P1) — ✅ complete

- File: `aitbc/agent_memory/__init__.py` (new)
- File: `aitbc/agent_memory/models.py` (new)
  - `ContentAddressedBlob`, `StorageLease`, `ReplicationProof`, and
    `EncryptionEnvelope` dataclasses.
- File: `aitbc/agent_memory/errors.py` (new)
  - Domain exceptions for missing or unauthorized blobs.

### A4: Industry-specific compliance abstractions (P2) — ✅ complete

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

### B1: `apps/memory` service skeleton (P1) — ✅ skeleton landed

- File: `apps/memory/src/memory_app/main.py` (new)
- File: `apps/memory/src/memory_app/api.py` (new)
  - `POST /store`, `GET /retrieve`, `GET /health`.
- File: `apps/memory/src/memory_app/config.py` (new)
  - Subclass `aitbc_shared.ServiceSettings`.
- File: `apps/memory/src/memory_app/service.py` (new)
  - Content addressing, encryption-at-rest hook, and replication proof hook.

### B2: Developer ecosystem & DAO grants (P1) — ✅ skeleton landed

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

### B4: Cleanup verification (P2) — ✅ scripts landed

- File: `scripts/security/scan_secrets.py` (new or update)
  - Enforce that no hardcoded API keys are added to the repo.
  - Fixed `apps/wallet/.../manager.py` hardcoded `coordinator-key`.
- File: `scripts/ci/check_deprecation_cleanup.sh` (new)
  - Grep for `AIPowerRental`, `light-theme`, and hardcoded API-key patterns.
  - Fixed `apps/coordinator-api/.../analytics.py` default dashboard theme `light` -> `dark`.

### B5: Core capability verification (P1) — ✅ complete

- File: `apps/edge/` (updated)
  - Added `region` support to island memberships (`POST /api/v1/islands/join`,
    `GET /api/v1/islands/by-region/{region}`) for Global Multi-Region Edge Nodes.
- File: `apps/gpu/` (updated)
  - Implemented Dynamic GPU Priority Queuing via `gpu_job_queue` table and
    `POST/GET /v1/gpu/queue`, `POST /v1/gpu/queue/{gpu_id}/next`,
    `POST /v1/gpu/queue/{job_id}/complete` endpoints.
- File: `aitbc/fusion/` (new)
  - Shared `FusionInput`, `FusionOutput`, `FusionConfig`, `FusionStrategy` types.
- File: `docs/releases/v0.11.0/capability_verification.md` (new)
  - Core capability documentation with "✅ COMPLETE" tags.

### B6: API key onboarding & UI accessibility (P2) — ✅ complete

- File: `cli/aitbc_cli/commands/config.py` (updated)
  - Added `config check-keys` command that reports missing environment API keys
    for `AITBC_API_KEY`, `CLIENT_API_KEY`, `MINER_API_KEY`, `ADMIN_API_KEY`,
    `COORDINATOR_API_KEY`, and optional provider keys (OpenAI, Google
    Translate, DeepL, Exchange).
- File: `docs/web/README.md` (new)
  - Documents the dark-mode-only accessibility decision, high-contrast
    mitigation, and verification command.

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
- [x] `aitbc/agent_memory` models are consumed by `apps/memory`.
- [x] `apps/memory` service starts and passes a health check.
- [x] Developer registry and grant proposal SQLModels are created with a
      migration.
- [x] CLI `developer` and `grant` commands are wired and smoke-tested.
- [x] Compliance policy helpers have unit coverage (all 8 templates tested).
- [x] Cleanup verification scripts (`scan_secrets.py`, `check_deprecation_cleanup.sh`) pass.
- [x] Core capability verification (edge, GPU priority queue, fusion) complete.
- [x] `config check-keys` command reports missing environment API keys.
- [x] Dark-mode-only accessibility policy documented in `docs/web/README.md`.
- [x] `ruff` and `mypy` pass.
- [x] `pytest tests/unit` passes.
- [x] `alembic upgrade head` and `alembic check` pass for coordinator-api.
- [x] Installed `aitbc` package version aligned with `pyproject.toml` (0.10.18).
- [~] `scripts/ci/check_phase4_gates.py`: `compliance_coverage` (100%) and
      `test_coverage` (50.61%) pass; operational gates remain pending until
      network metrics are available.

*Generated with [Devin](https://devin.ai)*
