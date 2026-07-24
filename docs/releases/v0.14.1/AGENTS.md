# v0.14.1 — TEE-Backed Verification & Confidential Compute (Phase 1)

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Supplement ZK-proofs with Trusted Execution Environments
(TEEs) to provide hardware-level privacy for agent messaging, sensitive data
processing, and confidential transactions.

**Prerequisites**: v0.10.18 complete; v0.11.0 in-flight, v0.12.0–v0.13.0
planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/tee/`, `aitbc/crypto/`, `aitbc/compute/` | TEE attestation, enclave identity, confidential messaging primitives, sealed storage |
| **Agent B** | `apps/coordinator-api` attestation/verification, `apps/gpu/`, `apps/edge/` | Remote attestation API, enclave orchestration, TEE compute tasks |

---

## Agent A — Shared Core & Types

### A1: TEE attestation & enclave lifecycle (P0)

- File: `aitbc/tee/attestation.py` (new)
  - Local and remote attestation quote generation/validation.
- File: `aitbc/tee/enclave.py` (new)
  - Enclave build, launch, and teardown abstractions.
- File: `aitbc/tee/identity.py` (new)
  - Enclave identity and key provisioning.

### A2: Confidential messaging (P1)

- File: `aitbc/tee/channel.py` (new)
  - Encrypted agent-to-agent channels bound to attested identities.
- File: `aitbc/tee/session.py` (new)
  - Key exchange with replay protection and forward secrecy.

### A3: TEE-backed data processing (P1)

- File: `aitbc/compute/tee_task.py` (new)
  - Confidential execution task abstractions.
- File: `aitbc/tee/sealed_storage.py` (new)
  - Sealed data-at-rest helpers.

---

## Agent B — Applications, Orchestration & CLI

### B1: Remote attestation service (P0)

- File: `apps/coordinator-api/src/coordinator_api/contexts/tee/attestation.py` (new)
  - Remote attestation verification API.
- File: `apps/coordinator-api/alembic/versions/` (new migration)
  - Create `tee_attestation` and `enclave_identity` tables.

### B2: GPU/edge enclave orchestration (P1)

- File: `apps/gpu/src/gpu_app/tee_runner.py` (TBD)
  - Launch confidential compute tasks on TEE-capable GPU nodes.
- File: `apps/edge/src/edge_app/tee_proxy.py` (TBD)
  - Edge proxy that routes messages into TEE-backed channels.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/tee/`, TEE-aware crypto primitives, and confidential
  compute task abstractions.
- Agent B owns `apps/coordinator-api` attestation verification and `apps/gpu/`
  and `apps/edge/` enclave orchestration.
- Shared boundary: `aitbc/tee/attestation.py` is consumed by the
  `apps/coordinator-api` attestation API; Agent A writes the primitives first,
  then Agent B wires the remote verification service.
- Sequence: Agent A lands attestation, identity, and channel primitives before
  Agent B begins orchestration integration.

## Release Gate

- [ ] TEE attestation primitives compile and have unit tests.
- [ ] Enclave lifecycle orchestration is testable on a local SGX/simulator.
- [ ] Confidential agent-to-agent messaging channel is established and
      stress-tested.
- [ ] TEE-backed data processing integrates with the memory layer.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
