# Mempool Eviction Order

**Level**: Intermediate
**Prerequisites**: [Scenario 22 Bridge RPC Input Validation](./22_bridge_rpc_validation.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Mempool Eviction Order

---

## See Also

- **Previous Scenario**: [Scenario 22 Bridge RPC Input Validation](./22_bridge_rpc_validation.md)
- **Next Scenario**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)
- **Feature Documentation**: Blockchain Node Architecture

---

## Scenario Overview

This scenario verifies that the mempool evicts the **oldest** low-fee transaction first when at capacity, not the newest. This covers the B15 fix: the eviction tie-breaker was changed from `(fee, -received_at)` (evict newest) to `(fee, received_at)` (evict oldest).

### Use Case

When the mempool is full and a new transaction arrives, the system must evict the oldest low-fee transaction to make room. The old behavior evicted the newest low-fee transaction, which was unfair to users who submitted early and could cause transaction starvation.

### What You'll Learn

- How the mempool eviction logic works
- How to test eviction order with a small mempool
- How to verify that the oldest low-fee transaction is evicted first

---

## Prerequisites

### Knowledge Required

- Understanding of mempool concepts (pending transactions, fees, eviction)
- Basic Python familiarity

### Tools Required

- Python 3.13 with access to the `aitbc_chain` package

### Setup Required

- AITBC blockchain-node source code at `/opt/aitbc/apps/blockchain-node/src`

---

## Step-by-Step Workflow

### Step 1: Create a Small Mempool for Testing

```python
import sys
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
from aitbc_chain.mempool import InMemoryMempool, PendingTransaction

# Create a small mempool (max_size=5)
mp = InMemoryMempool(max_size=5, chain_id='test')
chain_txs = mp._get_chain_transactions('test')
```

### Step 2: Add Low-Fee Transactions at Different Times

Add 3 low-fee transactions with increasing `received_at` timestamps, then fill to capacity with high-fee transactions:

```python
# Add 3 low-fee transactions at different times
for name, ts in [('tx_oldest', 100.0), ('tx_middle', 200.0), ('tx_newest', 300.0)]:
    tx = PendingTransaction(tx_hash=name, fee=1, received_at=ts, content={'hash': name})
    chain_txs[name] = tx
    print(f'  {name}: received_at={ts}')

# Add 2 more to fill to capacity (5)
for name in ['tx_fill1', 'tx_fill2']:
    tx = PendingTransaction(tx_hash=name, fee=100, received_at=400.0, content={'hash': name})
    chain_txs[name] = tx
print(f'Mempool now at capacity: {len(chain_txs)} txs')
```

### Step 3: Trigger Eviction and Check Which Transaction Was Evicted

```python
print('Triggering eviction...')
mp._evict_lowest_fee('test')

remaining = set(chain_txs.keys())
print(f'Remaining txs: {remaining}')

if 'tx_oldest' not in remaining:
    print('PASS: tx_oldest (received_at=100.0) was evicted — oldest low-fee tx evicted first (B15 fix)')
elif 'tx_newest' not in remaining:
    print('FAIL: tx_newest was evicted — this is the OLD buggy behavior (evicted newest)')
```

**Expected output:**

```
  tx_oldest: received_at=100.0
  tx_middle: received_at=200.0
  tx_newest: received_at=300.0
Mempool now at capacity: 5 txs
Triggering eviction...
Remaining txs: {'tx_fill2', 'tx_middle', 'tx_fill1', 'tx_newest'}
PASS: tx_oldest (received_at=100.0) was evicted — oldest low-fee tx evicted first (B15 fix)
```

---

## Code Examples

### Eviction Logic (B15 Fix)

The fix changed the tie-breaker from `-received_at` (newest first) to `received_at` (oldest first):

```python
# apps/blockchain-node/src/aitbc_chain/mempool.py
def _evict_lowest_fee(self, chain_id: str) -> None:
    """Evict the lowest-fee transaction to make room."""
    chain_transactions = self._get_chain_transactions(chain_id)
    if not chain_transactions:
        return
    # B15 fix: use (fee, received_at) ascending — evict oldest low-fee tx
    # OLD (buggy): min(..., key=lambda t: (t.fee, -t.received_at)) — evicted newest
    lowest = min(chain_transactions.values(), key=lambda t: (t.fee, t.received_at))
    del chain_transactions[lowest.tx_hash]
    metrics_registry.increment(f"mempool_evictions_total_{chain_id}")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Understand how mempool eviction prioritizes transactions by fee and age
- Verify that the oldest low-fee transaction is evicted first (not the newest)
- Reproduce the eviction scenario with a controlled test mempool

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys
sys.path.insert(0, 'apps/blockchain-node/src')
from aitbc_chain.mempool import InMemoryMempool, PendingTransaction

mp = InMemoryMempool(max_size=5, chain_id='test')
chain_txs = mp._get_chain_transactions('test')

for name, ts in [('tx_oldest', 100.0), ('tx_middle', 200.0), ('tx_newest', 300.0)]:
    chain_txs[name] = PendingTransaction(tx_hash=name, fee=1, received_at=ts, content={'hash': name})
for name in ['tx_fill1', 'tx_fill2']:
    chain_txs[name] = PendingTransaction(tx_hash=name, fee=100, received_at=400.0, content={'hash': name})

mp._evict_lowest_fee('test')
remaining = set(chain_txs.keys())
assert 'tx_oldest' not in remaining, 'FAIL: oldest was not evicted'
assert 'tx_newest' in remaining, 'FAIL: newest was evicted (old bug)'
print('PASS: B15 eviction order verified')
"
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- Test-suite hardening is still in progress; the targeted scenarios here are green, but the full project suite still has a small number of unrelated failures.


## Related Resources

- Blockchain Node Architecture
- [Next Scenario: Fire-and-Forget Task Error Logging](./24_task_error_logging.md)

---

*Last updated: 2026-08-19*
*Version: 1.1*
