# Bridge RPC Input Validation

**Level**: Intermediate
**Prerequisites**: [Scenario 21 Service Startup & Connectivity](./21_service_startup_connectivity.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.4

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Bridge RPC Input Validation

---

## See Also

- **Previous Scenario**: [Scenario 21 Service Startup & Connectivity](./21_service_startup_connectivity.md)
- **Next Scenario**: [Scenario 23 Mempool Eviction Order](./23_mempool_eviction_order.md)
- **Feature Documentation**: [Bridge Security Audit](../releases/AUDIT.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

Bridge lock/confirm requests with empty chains, zero amounts, or missing signatures must fail closed. The blockchain RPC returns HTTP 422 (Pydantic). Drive those checks through `aitbc bridge`, which posts to `/rpc/bridge/*` via `BridgeClient`.

This is the bridge RPC input validation operator play (B13).

### Use Case

An operator or customer CLI must not be able to submit a malformed lock. Structured errors should come back through the CLI, not a silent 200.

### What You'll Learn

- How to check bridge health with `aitbc bridge health`
- How `aitbc bridge lock` / `confirm` reject invalid input
- How the bridge rejects same-chain locks and amount limits
- How `aitbc bridge unlock` enforces a refund delay
- How pending/status queries work when the RPC is up

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Blockchain RPC reachable (default `http://localhost:8202/rpc`, which maps to `/rpc/bridge/...`)

---

## Step-by-Step Workflow

The CLI default `--rpc-url` is `http://localhost:8202/rpc`. Override it when talking to a remote hub RPC.

### Step 1: Health

```bash
aitbc bridge health
```

**Expected output:** `success: true`, `status: healthy`, `bridge_initialized: true`.

### Step 2: Reject a zero-amount lock

```bash
aitbc bridge lock \
  --target-chain chain2 \
  --sender 0xabc \
  --recipient 0xdef \
  --amount 0 \
  --signature 0x123
```

**Expected output:** CLI abort. Underlying RPC is HTTP 422 (`amount` must be greater than 0).

### Step 3: Reject an empty target chain

```bash
aitbc bridge lock \
  --target-chain "" \
  --sender 0xabc \
  --recipient 0xdef \
  --amount 10 \
  --signature 0x123
```

**Expected output:** CLI abort / Click usage error or HTTP 422 `string_too_short` on `target_chain`.

### Step 4: Reject confirm with an empty transfer id

`aitbc bridge confirm` requires `--transfer-id`, `--confirmer`, `--signature`, and a `--proof-file`. An empty transfer id or empty proof file must fail:

```bash
printf '%s\n' '{}' > /tmp/empty-bridge-proof.json
aitbc bridge confirm \
  --transfer-id "" \
  --confirmer 0xabc \
  --signature 0x123 \
  --proof-file /tmp/empty-bridge-proof.json
```

**Expected output:** CLI abort (empty `--transfer-id` and/or 422 from the RPC).

### Step 5: Reject a same-chain lock

```bash
aitbc bridge lock   --target-chain ait-hub.aitbc.bubuit.net   --sender 0xabc   --recipient 0xdef   --amount 10   --signature 0x123
```

**Expected output:** HTTP 400 with `Source and target chain must be different`.

### Step 6: Enforce maximum lock amount

If the node is configured with a `bridge_max_lock_amount`, a larger lock is rejected:

```bash
aitbc bridge lock   --target-chain chain2   --sender 0xabc   --recipient 0xdef   --amount 9999999999999   --signature 0x123
```

**Expected output:** HTTP 400 with `Amount ... exceeds bridge max lock amount ...` (when the max is set and the amount exceeds it).

### Step 7: Refund delay

After a successful lock, an immediate refund is rejected if the node has `bridge_refund_delay_seconds > 0`:

```bash
aitbc bridge unlock   --transfer-id <transfer-id>   --sender 0xabc   --signature 0x123
```

**Expected output:** HTTP 400 with `Refund not allowed yet: ...s since lock, minimum delay is ...s`.

### Step 8: List pending transfers (valid read path)

```bash
aitbc bridge pending
aitbc bridge security-status
```

**Expected output:** a (possibly empty) pending list and a security-status payload. Multi-sig may report disabled — that matches current production defaults (see DESIGN_CYCLE.md). The health/status output also shows `bridge_refund_delay_seconds` and `bridge_max_lock_amount`.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm bridge health through `aitbc bridge health`
- Prove malformed lock/confirm attempts fail closed
- Prove same-chain and over-limit locks fail closed
- Prove immediate refunds are delayed when configured
- Inspect pending transfers without crafting raw HTTP

---

## Validation

If you need to see the raw 422 body (not the play):

```bash
# validation only — the play is aitbc bridge lock
aitbc bridge health --rpc-url http://127.0.0.1:8202/rpc
```

---

## Related Resources

- [Bridge Security Audit](../releases/AUDIT.md)
- [Next Scenario: Mempool Eviction Order](./23_mempool_eviction_order.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
