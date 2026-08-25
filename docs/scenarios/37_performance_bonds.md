# Scenario 37: On-Chain Performance Bonds

**Level**: Intermediate
**Prerequisites**: Scenario 01 Wallet Basics, Scenario 07 AI Job Submission
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Performance Bonds

---

## See Also

- **Previous Scenario**: [Scenario 36 Pool Hub SLA](./36_pool_hub_sla_e2e.md)
- **Feature Documentation**: [Bond CLI](../../cli/aitbc_cli/commands/bond.py)

---

## Scenario Overview

This scenario demonstrates how a provider locks an on-chain performance bond,
queries it, releases it after the lock period, and why marketplace offers are
rejected without an active bond.

### Use Case

Providers need a stake that can be slashed if they fail to deliver on a job.
The bond lives on-chain in a dedicated escrow account and is enforced by the
blockchain node.

### What You'll Learn

- Lock a bond with `aitbc bond create`
- Query bond status with `aitbc bond status`
- Release a matured bond with `aitbc bond release`
- See the marketplace offer admission fail without an active bond

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A wallet with a non-zero balance on the hub chain

### Setup Required

- `BLOCKCHAIN_MODE`/`MARKET_ROLE` configured as shop or customer
- `HUB_RPC_URL` or `blockchain_rpc_url` points to the hub blockchain RPC

---

## Step-by-Step Workflow

### Step 1: Create a performance bond

```bash
aitbc bond create --wallet devin-test 0.001
```

**Expected output:**

```json
{
  "bond_id": "bond_0x28241C034aDF9ca346BE0C3596FF30e4905bD940_1787312221",
  "provider": "0x28241C034aDF9ca346BE0C3596FF30e4905bD940",
  "amount": "0.001",
  "lock_days": 30,
  "tx_hash": "0x..."
}
```

### Step 2: Query the bond

```bash
aitbc bond status --bond-id bond_0x28241C034aDF9ca346BE0C3596FF30e4905bD940_1787312221
```

**Expected output:**

```json
{
  "success": true,
  "bond_id": "...",
  "status": "active",
  "amount": 3,
  "locked_until": "..."
}
```

### Step 3: Create a short-term bond and release it

```bash
aitbc bond create --wallet devin-test --lock-days 0 0.001
# wait until the block is confirmed
aitbc bond release --wallet devin-test <bond-id>
aitbc bond status --bond-id <bond-id>
```

**Expected output for the released bond:**

```json
{
  "success": true,
  "status": "released",
  "amount": 0,
  "released_tx_hash": "0x..."
}
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Lock and release on-chain bonds using the `aitbc` CLI
- Query bond state by ID or provider
- Understand why marketplace offers require an active bond

---

## Validation

### Bond state is on-chain

```bash
aitbc bond status --provider 0x28241C034aDF9ca346BE0C3596FF30e4905bD940
```

### Marketplace offer admission is gated

```bash
curl -s -X POST https://hub.aitbc.bubuit.net/rpc/transactions/marketplace \
  -H "Content-Type: application/json" \
  -d '{"type":"GPU_MARKETPLACE","from":"0x1111111111111111111111111111111111111111","to":"0x0000000000000000000000000000000000000000","amount":0,"fee":36,"nonce":0,"chain_id":"ait-hub.aitbc.bubuit.net","payload":{"action":"software_offer","offer_id":"test","service_type":"whisper","price":0.1,"price_unit":"per_audio_min","provider_address":"0x1111111111111111111111111111111111111111","status":"active"}}'
```

**Expected output (when `MARKET_BOND_MIN_AMOUNT` > 0):**

```json
{"detail":"Failed to submit marketplace transaction: 403: Active bond of at least 1 compute-seconds required to list"}
```

### Unit tests

```bash
ssh aitbc3
cd /opt/aitbc
python3 -m pytest apps/blockchain-node/tests/test_bond.py -q -o addopts=""
```

---

## Related Resources

- [State transition code](../../apps/blockchain-node/src/aitbc_chain/state/state_transition.py)
- [Bond CLI](../../cli/aitbc_cli/commands/bond.py)

---

*Last updated: 2026-08-21*
*Version: 1.0*
