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
  - Append-only, tamper-evident log entries.
- File: `aitbc/compliance/retention.py` (new)
  - Retention policy helpers.

### A4: Consent & right-to-access (P2)

- File: `aitbc/compliance/consent.py` (new)
  - Consent tracking and revocation abstractions.

---

## Agent B — Applications, CLI & Middleware

### B2: Healthcare HIPAA module (P1)

- File: `apps/coordinator-api/src/coordinator_api/contexts/compliance/hipaa.py` (new)
  - PHI access controls, consent, and right-to-delete workflows.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Create `consent_record` and `phi_access_log` tables.

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

- [ ] Compliance policy framework compiles and has unit tests.
- [x] Encryption and key management primitives are testable.
- [ ] Immutable audit log is wired to `coordinator-api` events.
- [ ] HIPAA module has example policies and tests.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
