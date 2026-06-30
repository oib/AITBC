# v0.7.3 Governance — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create governance types, governance client, on-chain utilities, and unit tests.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/governance/ && ./venv/bin/python -m ruff check aitbc/governance/ tests/unit/test_governance_sdk.py && ./venv/bin/python -m pytest tests/unit/test_governance_sdk.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Governance types — GovernanceTxType enum, GovernanceConfig, ProposalData, VoteData, ParameterChangeSchema | 🔴 P0 | `aitbc/governance/types.py` (new) | ✅ |
| A2 | Governance client — GovernanceClient with async HTTP methods | 🔴 P0 | `aitbc/governance/client.py` (new) | ✅ |
| A3 | On-chain utilities — build_proposal_tx, build_vote_tx, build_execute_tx, validate_governance_payload | 🔴 P0 | `aitbc/governance/onchain.py` (new) | ✅ |
| A4 | Unit tests for A1-A3 | High | `tests/unit/test_governance_sdk.py` (new) | ✅ |

---

## A1: Governance Types

Create `aitbc/governance/types.py`:
- `GovernanceTxType` enum — PROPOSE, VOTE, EXECUTE
- `GovernanceConfig` dataclass — voting params, timelock, quorum
- `ProposalData` dataclass — on-chain tx payload for proposals
- `VoteData` dataclass — on-chain tx payload for votes
- `ParameterChangeSchema` dataclass — what params, which service, old→new

---

## A2: Governance Client

Create `aitbc/governance/client.py`:
- `GovernanceClient` — async HTTP client for governance service RPC
- `submit_proposal(proposal_data)` — submit proposal to governance service
- `submit_vote(vote_data)` — submit vote to governance service
- `execute_proposal(proposal_id)` — execute proposal via governance service
- `get_status(proposal_id)` — get proposal status from governance service

---

## A3: On-Chain Utilities

Create `aitbc/governance/onchain.py`:
- `build_proposal_tx(proposal_data)` — GOVERNANCE_PROPOSE tx payload
- `build_vote_tx(vote_data)` — GOVERNANCE_VOTE tx payload
- `build_execute_tx(proposal_id)` — GOVERNANCE_EXECUTE tx payload
- `validate_governance_payload(tx_type, payload)` — field validation

---

## A4: Unit Tests

`tests/unit/test_governance_sdk.py` — tests for:
- Governance types serialization
- Governance client HTTP methods (mocked httpx)
- On-chain utilities tx building
- Payload validation

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.3 — Governance
**Agent**: Agent A (Shared Core)
