# v0.15.2 — Compliance-Ready Modules (Phase 2: Containers, Finance & Middleware)

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Add runtime isolation, financial-regulatory controls, and
middleware/CLI integration on top of the v0.15.1 compliance policy foundation.

**Prerequisites**: v0.15.1 complete; v0.16.1–v0.16.2 planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/compliance/` | Shared retention/consent helpers consumed by middleware |
| **Agent B** | `apps/edge/`, `apps/gpu/`, `apps/coordinator-api`, `cli/` | Compliance containers, financial module, middleware, CLI |

---

## Agent A — Shared Core & Types

### A1: Consent & right-to-access helpers (P1)

- File: `aitbc/compliance/consent.py` (new or update)
  - Consent tracking and revocation abstractions used by middleware.

---

## Agent B — Applications, CLI & Middleware

### B1: Compliance containers & sub-networks (P0) — ✅ complete

- File: `apps/edge/src/edge_app/compliance_subnets.py` (new)
  - `ComplianceSubnet` and `SubnetRegistry` assign workloads to segmented
    sub-networks filtered by compliance framework and data classification.
- File: `apps/gpu/src/gpu_app/compliance_enclaves.py` (new)
  - `ComplianceGPUEnclave` wraps a TEE enclave, requires attestation, and only
    runs workloads matching allowed classifications.

### B2: Financial regulatory module (P0) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/compliance/finance.py` (new)
  - `TransactionAuditRecord` and `NonRepudiationProof` SQLModels with PCI/GLBA
    classification, consent checks, and audit trail fields.
  - `FinancialComplianceService` creates regulated transactions, authorizes them
    against a policy, and produces/verifies non-repudiation proofs.
- File: `apps/coordinator-api/alembic/versions/1a7d8e9b0c2f_create_financial_compliance_tables.py` (new)
  - Creates `transaction_audit_record` and `non_repudiation_proof` tables with
    indexes.
- File: `apps/coordinator-api/src/coordinator_api/main.py`
  - Imports the new SQLModels so `alembic`/`SQLModel.metadata` sees them.
- `tests/unit/test_v152_agent_b.py` covers transaction creation, consent-gated
  authorization, and non-repudiation proof verification for PCI and GLBA
  policies.

### B3: Coordinator-api middleware & CLI (P1) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/middleware/compliance.py` (new)
  - `ComplianceMiddleware` inspects `X-Data-Classification`,
    `X-Consent-Subject`, and `X-Consent-Purpose` headers and blocks sensitive
    requests without active consent.
- File: `cli/aitbc_cli/commands/compliance.py` (new)
  - `compliance check` (verify a classification against a policy),
    `compliance classify` (normalize a label), and
    `compliance export-audit` (export a simulated audit trail).
- `tests/unit/test_v152_b1_b3.py` covers subnets, GPU enclaves, consent
  tracking, middleware, and CLI commands.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/compliance/consent.py` shared helpers.
- Agent B owns compliance containers in `apps/edge/` and `apps/gpu/`, the
  financial module, `apps/coordinator-api` middleware, and the compliance CLI.
- Shared boundary: `aitbc/compliance/policies.py` and
  `aitbc/compliance/consent.py` are consumed by the middleware; Agent A's work
  is in v0.15.1, so Agent B can proceed once v0.15.1 is merged.
- Sequence: Agent B begins after v0.15.1 release gate passes.

## Release Gate

- [x] Compliance container/sub-network design is documented and reviewed.
- [x] Financial regulatory module has example policies and tests.
- [x] Compliance middleware enforces classification and consent in coordinator-api.
- [x] `compliance` CLI commands are wired to policy checks and audit export.
- [x] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
