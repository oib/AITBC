# Persistent Spending Tracker Contract

Persistent Spending Tracker - Database-Backed Security

## Implementation Details

- `SpendingRecord` — Database model for spending tracking
- `SpendingLimit` — Database model for spending limits
- `GuardianAuthorization` — Database model for guardian authorizations
- `SpendingCheckResult` — Result of spending limit check
- `PersistentSpendingTracker` — Database-backed spending tracker that survives restarts

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/persistent_spending_tracker.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/persistent_spending_tracker.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
