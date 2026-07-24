# v0.15.1 — Compliance-Ready Modules (Phase 1: Policies, Encryption & Audit)

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Implement the compliance policy, data classification,
encryption, key management, and immutable audit-logging foundation for
Healthcare (HIPAA) and other regulated industries.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0–v0.14.2 planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/compliance/`, `aitbc/crypto/`, shared types | Policy framework, data classification, encryption/key management, audit log primitives |
| **Agent B** | `apps/coordinator-api` compliance/analytics domains | HIPAA module, coordinator-api analytics wiring |

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
  - ``TenantKeyPolicy``, ``TenantKey``, ``TenantKeyManager`` with PBKDF2 key
    derivation, Fernet encryption/decryption, and key rotation with re-encryption.
- File: `aitbc/crypto/key_recovery.py` (new)
  - ``KeyEscrow``, ``RecoveryShare``, ``KeyEscrowStatus``, and ``escrow_key`` /
    ``recover_key`` helpers for key escrow and recovery flows.

### A3: Audit log primitives (P1)

- File: `aitbc/compliance/audit.py` (new or update)
  - ``AuditLog`` with append-only, chain-hashed events and ``verify_audit_log``
    integrity helper.
- File: `aitbc/compliance/retention.py` (new)
  - ``RetentionSchedule``, ``RetentionEngine``, and ``apply_retention`` helpers
    for evaluating retention actions across data classifications.

### A4: Consent & right-to-access (P2)

- File: `aitbc/compliance/consent.py` (new)
  - Consent tracking and revocation abstractions.

---

## Agent B — Applications, CLI & Middleware

### B2: Healthcare HIPAA module (P1) — ✅ complete

- File: `apps/coordinator-api/src/coordinator_api/contexts/compliance/hipaa.py` (new)
  - `ConsentRecord` and `PHIAccessLog` SQLModels.
  - `HIPAAComplianceService` with `grant_consent`, `revoke_consent`, `access_phi`,
    and `right_to_delete` workflows.
- File: `apps/coordinator-api/src/coordinator_api/contexts/compliance/routers/hipaa.py` (new)
  - FastAPI endpoints for consent grant/revoke, PHI access, and right-to-delete.
- File: `apps/coordinator-api/alembic/versions/9b0d2e4a1f5c_create_consent_record_and_phi_access_log_.py` (new)
  - Creates `consent_record` and `phi_access_log` tables with indexes.
- File: `apps/coordinator-api/src/coordinator_api/main.py`
  - Imports SQLModels and mounts the HIPAA compliance router.

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
- Agent B owns `apps/coordinator-api` compliance domains and analytics wiring.
- Shared boundary: `aitbc/compliance/policies.py` is consumed by the
  `apps/coordinator-api` middleware; Agent A writes the policy primitives
  first, then Agent B wires the middleware and endpoints.
- Sequence: Agent A lands classification, policies, and audit primitives
  before Agent B begins the coordinator-api middleware.

## Release Gate

- [x] Compliance policy framework compiles and has unit tests.
- [x] Encryption and key management primitives are testable.
- [x] Immutable audit log primitives have unit tests.
- [x] HIPAA module has example policies and tests.
- [x] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
