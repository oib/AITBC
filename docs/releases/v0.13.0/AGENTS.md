# v0.13.0 — Compliance-Ready Modules

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Implement compliance-ready modules for Healthcare (HIPAA),
Financial services, and other regulated industries via compliance containers,
sub-networks, encryption, and immutable audit logging.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0 planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/compliance/`, `aitbc/crypto/`, shared types | Policy framework, data classification, encryption/key management, audit log primitives |
| **Agent B** | `apps/coordinator-api` compliance/analytics domains, `cli/`, `apps/edge/`, `apps/gpu/` | Compliance containers/sub-networks, middleware, CLI, industry modules, coordinator-api wiring |

---

## Agent A — Shared Core & Types

### A1: Compliance policy framework (P0)

- File: `aitbc/compliance/policies.py` (new or update)
  - HIPAA, SOC 2, GLBA, PCI-DSS, Manufacturing, Education, and Retail
    policy templates.
- File: `aitbc/compliance/classification.py` (new)
  - Data classification labels (PHI, PII, PCI, public, internal, restricted).

### A2: Encryption & key management (P1)

- File: `aitbc/crypto/tenant_keys.py` (new)
  - Per-tenant key derivation and rotation policies.
- File: `aitbc/crypto/key_recovery.py` (new)
  - Key escrow and recovery flows for regulated data.

### A3: Audit log primitives (P1)

- File: `aitbc/compliance/audit.py` (new or update)
  - Append-only, tamper-evident log entries.
- File: `aitbc/compliance/retention.py` (new)
  - Retention policy helpers.

### A4: Consent & right-to-access (P2)

- File: `aitbc/compliance/consent.py` (new)
  - Consent tracking and revocation abstractions.

---

## Agent B — Applications, CLI & Middleware

### B1: Compliance containers & sub-networks (P0)

- File: `apps/edge/src/edge_app/compliance_subnets.py` (TBD)
  - Segmented sub-networks for sensitive agent workloads.
- File: `apps/gpu/src/gpu_app/compliance_enclaves.py` (TBD)
  - TEE-backed GPU enclave support.

### B2: Healthcare HIPAA module (P1)

- File: `apps/coordinator-api/src/coordinator_api/contexts/compliance/hipaa.py` (new)
  - PHI access controls, consent, and right-to-delete workflows.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Create `consent_record` and `phi_access_log` tables.

### B3: Financial regulatory module (P2)

- File: `apps/coordinator-api/src/coordinator_api/contexts/compliance/finance.py` (new)
  - PCI/GLBA controls, transaction audit trails, and non-repudiation proofs.

### B4: Coordinator-api middleware & CLI (P2)

- File: `apps/coordinator-api/src/coordinator_api/middleware/compliance.py` (new)
  - Decorators/middleware enforcing data classification and consent.
- File: `cli/aitbc_cli/commands/compliance.py` (new)
  - `compliance check`, `compliance export-audit`, `compliance classify`.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/compliance/`, `aitbc/crypto/tenant_keys.py`, and audit
  log primitives.
- Agent B owns compliance containers in `apps/edge/` and `apps/gpu/`,
  `apps/coordinator-api` compliance domains, and CLI commands.
- Shared boundary: `aitbc/compliance/policies.py` is consumed by the
  `apps/coordinator-api` middleware; Agent A writes the policy primitives
  first, then Agent B wires the middleware and endpoints.
- Sequence: Agent A lands classification, policies, and audit primitives
  before Agent B begins the coordinator-api middleware.

## Release Gate

- [ ] Compliance policy framework compiles and has unit tests.
- [ ] Compliance container/sub-network design is documented and reviewed.
- [ ] Encryption and key management primitives are testable.
- [ ] Immutable audit log is wired to `coordinator-api` events.
- [ ] HIPAA and financial modules have example policies and tests.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
