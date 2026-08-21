# Scenario 44 — Refund a failed TEE job escrow

**Level**: Intermediate
**Prerequisites**: Scenario 39 (TEE attestation), a failed TEE job with `payment_status=escrowed`
**Estimated Time**: 5 minutes
**Last Updated**: 2026-08-21
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Refund a failed TEE job escrow

---

## See Also

- **Previous Scenario**: [39 TEE Attestation](./39_tee_attestation.md)
- **Next Scenario**: [43 Compliance, Plugins and White-Label](./43_compliance_plugins_white_label.md)
- **Design Cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md)
- **Live Validation**: [LIVE_VALIDATION_SUMMARY.md](../../../LIVE_VALIDATION_SUMMARY.md)

---

## Scenario Overview

A confidential (TEE) job may fail because the provider cannot produce valid attestation. When that happens, the customer should be able to reclaim the escrowed payment through the canonical `aitbc` CLI. This scenario walks through refunding a failed TEE job end-to-end.

### Use Case

A customer submits a TEE job and escrow is created. The shop/miner executes the job but the TEE attestation is rejected, so the coordinator marks the job `COMPLETED` with `payment_status=escrowed` and an error. The customer wants the funds back.

### What You'll Learn

- How to refund a failed job with `aitbc market escrow refund`
- How to refund a failed job with the full-cycle `aitbc ai refund`
- How to verify the on-chain escrow and coordinator payment states agree

---

## Prerequisites

### Knowledge Required

- How TEE attestation affects escrow release (Scenario 39)
- How `aitbc ai submit` creates and funds an escrow (Scenario 34)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Access to the hub node blockchain RPC (port 8202) and coordinator API (port 8203)

### Setup Required

- A failed TEE job with:
  - `state = COMPLETED`
  - `payment_status = escrowed`
  - `error` containing `TEE attestation required before escrow release (status: attestation_rejected)`

---

## Step-by-Step Workflow

Every operator step uses the `aitbc` CLI. Curl, `journalctl`, and `pytest` belong only under **Validation**.

### Step 1: Check the escrow state

```bash
aitbc market escrow status <job_id>
```

**Expected output:**

```json
{
  "job_id": "<job_id>",
  "state": "funded",
  "amount": "5",
  "refunded_amount": "0"
}
```

### Step 2: Refund through the coordinator (full cycle)

If you have a client token (from `aitbc auth login` or `--api-key`), use the coordinator-aware command:

```bash
aitbc ai refund <job_id> --reason "TEE attestation rejected"
```

**Expected output:**

```json
{
  "status": "refunded",
  "payment_id": "<payment_id>"
}
```

This updates the coordinator `JobPayment` and the on-chain escrow in one call.

### Step 3: Refund through the blockchain directly (fallback)

If you do not have a client token, refund the on-chain escrow directly:

```bash
aitbc market escrow refund <job_id> --reason "TEE attestation rejected"
```

**Expected output:**

```json
{
  "success": true,
  "contract_id": "escrow_...",
  "job_id": "<job_id>",
  "message": "Contract refunded successfully",
  "refund_tx_hash": "0x..."
}
```

If the escrow was already refunded, the CLI returns success with the stored `refund_tx_hash`.

---

## Expected Outcomes

After completing this scenario, the customer should:

- See `payment_status = refunded` for the job in the coordinator.
- See `state = refunded` and `refunded_amount = amount` on-chain.
- Have the refund transaction hash recorded in both the coordinator and the chain DB.

---

## Validation

### Validate the on-chain escrow

```bash
curl -s http://localhost:8202/rpc/escrow/<job_id>
```

**Expected JSON:**

```json
{
  "job_id": "<job_id>",
  "state": "refunded",
  "refunded_amount": "5",
  "refund_tx_hash": "0x..."
}
```

### Validate the coordinator payment

```bash
sqlite3 /var/lib/aitbc/data/coordinator.db
SELECT id, payment_id, state, payment_status, error FROM job WHERE id='<job_id>';
SELECT id, status, refund_transaction_hash, refunded_at FROM job_payments WHERE id='<payment_id>';
```

**Expected rows:**

```text
<job_id>|<payment_id>|COMPLETED|refunded|TEE attestation required before escrow release (status: attestation_rejected)
<payment_id>|refunded|0x...|<timestamp>
```

---

## Related Resources

- [LIVE_VALIDATION_SUMMARY.md](../../../LIVE_VALIDATION_SUMMARY.md)
- [Scenario 39 — TEE Attestation](./39_tee_attestation.md)
- [Scenario 34 — Hub Customer Node E2E](./34_hub_customer_node_e2e.md)
- [DESIGN_CYCLE.md](../DESIGN_CYCLE.md)

---

*Last updated: 2026-08-21*
*Version: 1.0*
