# v0.7.4 Deferred v0.7.x Items — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Implement ExternalOracleClient, oracle fallback policy, cross-chain governance utilities (propagation, aggregation, execution), and parameter change execution helpers.

**Working directory**: `/opt/aitbc/aitbc/`

**Prerequisite**: v0.7.2 Agent A ✅, v0.7.3 Agent A ✅.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ aitbc/governance/ && ./venv/bin/python -m ruff check aitbc/bridge/ aitbc/governance/ tests/unit/test_v074_deferred.py && ./venv/bin/python -m pytest tests/unit/test_v074_deferred.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Implement `ExternalOracleClient` — replace NotImplementedError stubs with real oracle API calls | Medium | `aitbc/bridge/oracle.py` (extend) | ✅ |
| A2 | Add oracle fallback policy — in-process → oracle → in-process fallback logic | Medium | `aitbc/bridge/oracle.py` (extend), `aitbc/bridge/proof.py` (extend) | ✅ |
| A3 | Add cross-chain governance utilities — `propagate_proposal()`, `aggregate_votes()`, `execute_cross_chain()` | 🔴 P0 | `aitbc/governance/onchain.py` (extend), `aitbc/governance/client.py` (extend) | ✅ |
| A4 | Add parameter change execution helper — `build_parameter_apply_tx()` | Medium | `aitbc/governance/onchain.py` (extend) | ✅ (pre-existing) |
| A5 | Unit tests for A1-A4 | High | `tests/unit/test_v074_deferred.py` (new) | ✅ |

---

## A1: ExternalOracleClient

Extend `aitbc/bridge/oracle.py:228-262`:
- Replace `NotImplementedError` in `verify_proof()` with external oracle API call (httpx)
- Replace `NotImplementedError` in `check_finality()` with external oracle API call
- Add `__init__(endpoints: list[str], timeout: int = 30)` — takes oracle endpoints
- Add health check method: `is_healthy() -> bool`

---

## A2: Oracle Fallback Policy

Add to `aitbc/bridge/oracle.py` or `aitbc/bridge/proof.py`:
- `OracleFallbackPolicy` class — manages oracle → in-process fallback
- `verify_with_fallback()` — try oracle first, fall back to in-process on failure
- Health check loop — periodically check oracle health
- Recovery — attempt oracle reconnection every 60s

---

## A3: Cross-Chain Governance Utilities

Extend `aitbc/governance/onchain.py`:
- `build_proposal_propagation_tx(proposal_data, target_chain)` — bridge tx to propagate proposal
- `build_vote_aggregation_tx(votes, source_chain)` — bridge tx to aggregate votes

Extend `aitbc/governance/client.py`:
- `propagate_proposal(proposal_id, target_chains)` — propagate proposal to islands
- `aggregate_votes(proposal_id)` — aggregate votes from all chains
- `execute_cross_chain(proposal_id)` — execute on all chains after approval

---

## A4: Parameter Change Execution

Extend `aitbc/governance/onchain.py`:
- `build_parameter_apply_tx(parameter_change)` — tx to apply parameter change to target service
- `validate_parameter_change(parameter_change, target_service_config)` — validate before applying

---

## A5: Unit Tests

`tests/unit/test_v074_deferred.py` — tests for ExternalOracleClient (mocked httpx), fallback policy, cross-chain governance utilities, parameter change execution.

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.4 — Deferred v0.7.x Items
**Agent**: Agent A (Shared Core)
