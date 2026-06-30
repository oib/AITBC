# v0.7.3 Governance — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add governance config, blockchain client, on-chain proposals/votes, timelock execution, tests, governance tx types, governance tx payload validation, and CLI commands.

**Working directory**: `/opt/aitbc/apps/`, `/opt/aitbc/cli/`

**Prerequisite**: Agent A A1-A3 complete. v0.7.2 Agent B in progress.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/governance/src/ apps/blockchain-node/src/aitbc_chain/consensus/ cli/aitbc_cli/commands/governance.py
cd /opt/aitbc && PYTHONPATH=apps/governance/src:aitbc ./venv/bin/python -m pytest apps/governance/tests/test_v073_governance.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Governance config — Settings class with blockchain_rpc_url (8202), default_chain_id, voting params | 🔴 P0 | `apps/governance/src/governance_service/config.py` (new) | ✅ |
| B2 | Blockchain client — AITBCHTTPClient → query balance, submit GOVERNANCE_* txs | 🔴 P0 | `apps/governance/src/governance_service/services/blockchain_client.py` (new) | ✅ |
| B3 | On-chain proposals — Proposal → GOVERNANCE_PROPOSE tx, store tx_hash, block_height | 🔴 P0 | `apps/governance/src/governance_service/services/governance_service.py` (extend) | ✅ |
| B4 | On-chain voting — Vote → GOVERNANCE_VOTE tx, vote weight = on-chain balance at snapshot block | 🔴 P0 | `apps/governance/src/governance_service/services/governance_service.py` (extend) | ✅ |
| B5 | Timelock execution — Execute → GOVERNANCE_EXECUTE tx after timelock expires, record tx_hash | 🔴 P0 | `apps/governance/src/governance_service/services/governance_service.py` (extend) | ✅ |
| B6 | Tests — proposal → vote → execute flow | High | `apps/governance/tests/test_v073_governance.py` (new) | ✅ |
| B7 | Governance tx types — add GOVERNANCE_PROPOSE, GOVERNANCE_VOTE, GOVERNANCE_EXECUTE to tx type handling in poa.py | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` (extend) | ✅ |
| B8 | Governance tx payload validation — use A3 validate_governance_payload | Medium | `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` (extend) | ✅ |
| B9 | CLI commands — governance propose, vote, list, execute, status | Medium | `cli/aitbc_cli/commands/governance.py` (new) | ✅ |

---

## B1: Governance Config

Create `apps/governance/src/governance_service/config.py`:
- `Settings` class with `blockchain_rpc_url: str = "http://localhost:8202"`
- `default_chain_id: str = "ait-hub"`
- Voting params: `voting_quorum_threshold: float = 0.5`, `timelock_hours: int = 24`

---

## B2: Blockchain Client

Create `apps/governance/src/governance_service/services/blockchain_client.py`:
- `BlockchainClient` — wraps `AITBCHTTPClient` from `aitbc.blockchain.blockchain_service`
- `get_account_balance(address)` — query balance for vote weight snapshot
- `submit_transaction(tx_data)` — submit GOVERNANCE_* txs to blockchain-node

---

## B3: On-Chain Proposals

Extend `apps/governance/src/governance_service/services/governance_service.py`:
- `create_proposal_on_chain(proposal_data)` — create proposal + submit GOVERNANCE_PROPOSE tx
- Store `tx_hash`, `block_height` in Proposal model
- Use Agent A's `build_proposal_tx()` from A3

---

## B4: On-Chain Voting

Extend `apps/governance/src/governance_service/services/governance_service.py`:
- `cast_vote_on_chain(vote_data)` — cast vote + submit GOVERNANCE_VOTE tx
- Vote weight = on-chain balance at snapshot block (query via B2)
- Store `tx_hash`, `block_height` in Vote model
- Use Agent A's `build_vote_tx()` from A3

---

## B5: Timelock Execution

Extend `apps/governance/src/governance_service/services/governance_service.py`:
- `execute_proposal_on_chain(proposal_id)` — execute after timelock expires
- Submit GOVERNANCE_EXECUTE tx
- Record `tx_hash` in ProposalExecutionLog
- Use Agent A's `build_execute_tx()` from A3

---

## B6: Tests

`apps/governance/tests/test_v073_governance.py` — tests for:
- Proposal → vote → execute flow
- On-chain balance snapshot for vote weight
- Timelock enforcement
- Governance tx submission

---

## B7: Governance Tx Types

Extend `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`:
- Add GOVERNANCE_PROPOSE, GOVERNANCE_VOTE, GOVERNANCE_EXECUTE to tx type handling
- Store tx type in block (already handled by existing code)
- Add governance-specific state transitions

---

## B8: Governance Tx Payload Validation

Extend `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`:
- Use Agent A's `validate_governance_payload()` from A3
- Validate governance tx payloads before processing

---

## B9: CLI Commands

Create `cli/aitbc_cli/commands/governance.py`:
- `aitbc governance propose` — submit proposal
- `aitbc governance vote` — cast vote
- `aitbc governance list` — list proposals
- `aitbc governance execute` — execute proposal
- `aitbc governance status` — show proposal status

Use Agent A's `GovernanceClient` from A2.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.3 — Governance
**Agent**: Agent B (Apps & Infrastructure)
