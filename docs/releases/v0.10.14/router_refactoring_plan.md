# Router Modularity Plan

**Date**: 2026-07-02
**Status**: Planning
**Target**: Split `apps/blockchain-node/src/aitbc_chain/rpc/router.py` (1599 lines) into domain-specific sub-routers

## Current State

`router.py` is a monolithic FastAPI router that aggregates all blockchain RPC endpoints. It has:

- 100+ route handlers
- 8 optional module imports (disputes, contracts, islands, bridge, staking, AI services, GPU, etc.)
- Repetitive try/except import blocks (lines 63-251)
- No clear separation between core and optional functionality

## Proposed Structure

```
apps/blockchain-node/src/aitbc_chain/rpc/
├── __init__.py
├── router.py (main aggregator, ~200 lines)
├── routers/
│   ├── __init__.py
│   ├── core.py (core blockchain endpoints, ~300 lines)
│   ├── disputes.py (dispute resolution, ~200 lines)
│   ├── contracts.py (smart contracts, ~150 lines)
│   ├── islands.py (island management, ~100 lines)
│   ├── bridge.py (bridge endpoints, ~250 lines)
│   ├── staking.py (staking/governance, ~150 lines)
│   ├── subscription.py (subscription/lease, ~100 lines)
│   ├── consensus.py (consensus, ~150 lines)
│   └── settlement.py (settlement, ~150 lines)
```

## Domain Breakdown

### Core (router_core.py)

- Genesis allocations, head, height, blocks-range
- Info, status, network-info
- Import block, submit transaction, mempool
- Query transactions, marketplace transactions
- Account endpoints (get_account, create_account, faucet, balance, reconcile)
- State snapshot/delta

### Disputes (router_disputes.py)

- File dispute, submit evidence, verify evidence
- Arbitration vote, authorize arbitrator
- Get active disputes, arbitrators, user disputes
- Get dispute details, evidence, votes

### Contracts (router_contracts.py)

- Deploy messaging contract, list contracts
- Deploy contract, call contract, verify contract
- Messaging contract state
- Forum topics, messages, search, reputation, moderation

### Islands (router_islands.py)

- Join/leave islands, list islands, get island details
- Request bridge

### Bridge (router_bridge.py)

- Lock, confirm, unlock, transfer status
- Pending transfers, bridge balance, health
- Batch lock/confirm, validators
- Security status, block headers, oracle status

### Staking (router_staking.py)

- Stake/unstake, get staking info
- Agent identity register/get/verify
- Governance proposal/vote, get proposal

### Subscription (router_subscription.py)

- Register subscription, heartbeat
- Lease status, revoke lease, subscribers

### Consensus (router_consensus.py)

- Consensus status, validators, slashing history

### Settlement (router_settlement.py)

- Create escrow, lock/verify/settle escrow
- Resolve dispute

## Implementation Order

1. **Create routers/ directory structure** ✓
2. **Extract router_disputes.py** (simplest domain, clear boundary) ✓
3. **Extract router_contracts.py** (contracts + messaging) ✓
4. **Extract router_islands.py** (smallest domain) ✓
5. **Extract router_subscription.py** (self-contained) ✓
6. **Extract router_core.py** (core endpoints) ✓
7. **Extract router_staking.py** (staking + identity + governance) ✓
8. **Extract router_consensus.py** (consensus only) ✓
9. **Extract router_settlement.py** (settlement only) ✓
10. **Extract router_bridge.py** (largest domain, last) ✓
11. **Clean up remaining duplicate routes in main router.py** ✓
12. **Update imports in **init**.py** ✓
13. **Run tests to verify refactoring** - TODO

## Notes

- Each sub-router will use the same rate_limiting, auth, and logging patterns
- Optional modules will still be conditionally imported (STRICT_IMPORTS env var)
- The main router will include sub-routers only if the module is available
- All route paths remain unchanged (no breaking API changes)
