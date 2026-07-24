# v0.14.2 — TEE-Backed Verification & Confidential Compute (Phase 2)

**Last Updated**: 2026-07-24
**Version**: 0.1 — Planned 🚧

**Release Theme**: Extend the TEE foundation with dual-verification policies,
confidential transactions, and healthcare/finance reference enclaves.

**Prerequisites**: v0.14.1 complete; v0.15.1–v0.15.2 planned.

---

## Task Split Overview

| Agent | Files | Tasks |
|---|---|---|
| **Agent A** | `aitbc/tee/`, `aitbc/wallet/`, `aitbc/agent_economics/` | ZK + TEE dual verification, confidential transactions, enclave-side payment validation |
| **Agent B** | `cli/`, `examples/tee/`, `apps/coordinator-api` tee domain | TEE CLI commands, reference enclaves, compliance mapping |

---

## Agent A — Shared Core & Types

### A1: ZK + TEE dual verification (P0)

- File: `aitbc/tee/verification.py` (new)
  - Policy for ZK-only, TEE-only, or combined verification.
- File: `aitbc/tee/benchmark.py` (new)
  - Latency/cost benchmarking utilities.

### A2: Confidential transactions (P0)

- File: `aitbc/wallet/confidential.py` (new)
  - TEE-signed transaction envelopes and balance proofs.
- File: `aitbc/agent_economics/confidential_payments.py` (new)
  - Enclave-side payment validation.

---

## Agent B — Applications, Orchestration & CLI

### B1: TEE CLI extensions (P1)

- File: `cli/aitbc_cli/commands/tee.py` (new)
  - `tee attest`, `tee launch`, `tee verify`.
- File: `cli/aitbc_cli/commands/confidential.py` (new)
  - `confidential send`, `confidential balance`.

### B2: Healthcare & finance reference enclaves (P1)

- File: `examples/tee/hipaa_enclave/` (new)
  - Reference SGX enclave for PHI processing.
- File: `examples/tee/finance_enclave/` (new)
  - Reference SGX enclave for PCI/GLBA workloads.

---

## Verification Commands

```bash
cd /opt/aitbc
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/
./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

## Coordination Protocol

- Agent A owns `aitbc/tee/verification.py`, confidential wallet primitives, and
  enclave-side payment validation.
- Agent B owns TEE CLI commands in `cli/aitbc_cli/commands/` and reference
  enclaves in `examples/tee/`.
- Shared boundary: `aitbc/tee/attestation.py` and `aitbc/wallet/confidential.py`
  are consumed by the CLI; Agent A lands them before Agent B wires the commands.
- Sequence: Agent A completes dual-verification and confidential payment
  primitives before Agent B adds CLI and reference enclaves.

## Release Gate

- [ ] ZK + TEE dual verification policy is selectable and benchmarked.
- [ ] TEE-signed confidential transaction flow is testable end-to-end.
- [ ] Healthcare and finance reference enclaves build and have example tests.
- [ ] TEE CLI commands are wired to local attestation and enclave orchestration.
- [ ] `ruff`, `mypy`, and `pytest tests/unit` pass.

*Generated with [Devin](https://devin.ai)*
