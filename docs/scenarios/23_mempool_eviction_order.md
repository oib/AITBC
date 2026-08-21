# Mempool Eviction Order

**Level**: Intermediate
**Prerequisites**: [Scenario 22 Bridge RPC Input Validation](./22_bridge_rpc_validation.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Mempool Eviction Order

---

## See Also

- **Previous Scenario**: [Scenario 22 Bridge RPC Input Validation](./22_bridge_rpc_validation.md)
- **Next Scenario**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)

---

## Scenario Overview

When the mempool is full, the **oldest** low-fee transaction is evicted first (B15: tie-break `(fee, received_at)`, not `(fee, -received_at)`). Operators exercise the mempool through `aitbc transactions pending` / `send`. Deterministic fee ordering can also be inspected with `aitbc simulate blockchain`.

### Use Case

A burst of cheap transactions must not starve an earlier cheap transaction by evicting the newest instead of the oldest.

### What You'll Learn

- How to list the live mempool with `aitbc transactions pending`
- How to submit and inspect transactions with `aitbc transactions send` / `status`
- How the in-process eviction unit test confirms oldest-first (validation)

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A funded wallet (Scenario 01 / 02) if you send live transactions

### Setup Required

- Blockchain RPC reachable via CLI config (`blockchain_rpc_url`)

---

## Step-by-Step Workflow

### Step 1: Inspect the live mempool

```bash
aitbc transactions pending
```

**Expected output:** pending txs (possibly empty) from the configured hub/local RPC — not a hardcoded `localhost:8202` on a follower (fixed in `5886697ac`).

### Step 2: Submit two transactions with different fees

Use a test wallet that can sign. Prefer tiny amounts on a non-production wallet.

```bash
aitbc transactions send --from <wallet> --to <addr> --amount 0.001 --fee 1
aitbc transactions send --from <wallet> --to <addr> --amount 0.001 --fee 2
aitbc transactions pending
aitbc transactions status <tx-hash>
```

**Expected output:** both hashes appear; higher fee is not evicted in favor of a newer low fee. Exact eviction is only visible when the mempool is at `max_size`.

### Step 3: Deterministic fee simulation (no chain required)

```bash
aitbc simulate blockchain --blocks 2 --transactions 3 --delay 0 --seed 123 --output json
```

**Expected output:** identical JSON on a second run with the same seed. This does not evict, but it is the CLI-safe way to reason about fee fields without Python snippets as the play.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- List and inspect the mempool through `aitbc transactions`
- Send transactions whose fees you can compare
- Reproduce deterministic fee-bearing simulated blocks

---

## Validation

The B15 unit check (not the operator play):

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
assert 'tx_oldest' not in remaining
assert 'tx_newest' in remaining
print('PASS: B15 eviction order verified')
"
```

---

## Related Resources

- [Next Scenario: Fire-and-Forget Task Error Logging](./24_task_error_logging.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
