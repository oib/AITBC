# Job Submission with Payment Failure

**Level**: Intermediate
**Prerequisites**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Job Submission with Payment Failure

---

## See Also

- **Previous Scenario**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)
- **Next Scenario**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
- **Feature Documentation**: [Coordinator API Reference](../apps/coordinator-api/README.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

When a job is submitted with a payment that the coordinator cannot create, the job is still queued with `payment_status="skipped"` and `payment_id=null` (B12: rollback before marking skipped). Drive this with `aitbc ai submit --payment … --currency INVALID_CURRENCY`.

### Use Case

A client fat-fingers the currency. The job must still run unpaid; no orphaned payment row.

### What You'll Learn

- How to submit an unpaid and a bad-currency job through `aitbc ai`
- How to inspect `payment_status` with `aitbc ai status`

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A funded wallet (e.g. `customer-wallet`) and `aitbc auth login`

### Setup Required

- Coordinator API reachable (`aitbc config set coordinator_api_url http://127.0.0.1:8203` on the hub, or the public nginx path)

---

## Step-by-Step Workflow

Log in on the hub (do not scrape JWT secrets from env files):

```bash
# On the hub, with a funded customer wallet
aitbc auth login --wallet customer-wallet --coordinator-url http://127.0.0.1:8203
```

### Step 1: Submit a job with an invalid payment currency

```bash
aitbc --output json ai submit \
  --prompt "B12 payment-failure probe" \
  --payment 1.0 \
  --currency INVALID_CURRENCY \
  --coordinator-url http://127.0.0.1:8203
```

**Expected output:** HTTP 201 through the CLI: a `job_id`, `payment_status` of `skipped`, `payment_id` null. The job is queued even though payment failed.

### Step 2: Inspect the job

```bash
aitbc --output json ai status --job-id "$JOB_ID"
aitbc ai jobs --limit 5
```

**Expected output:** the same `job_id` with `payment_status: skipped`. State may move to `COMPLETED` if a miner picks it up (unpaid).

### Step 3: Contrast with a clean unpaid job

```bash
aitbc --output json ai submit \
  --prompt "unpaid control job" \
  --coordinator-url http://127.0.0.1:8203
```

**Expected output:** `payment_status` `none` (or omitted), no payment id.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Submit jobs with `aitbc ai submit`, including `--currency` overrides
- Confirm failed payments skip without orphaning a payment id
- List and inspect jobs with `aitbc ai jobs` / `status`

---

## Validation

```bash
# Coordinator log should mention payment creation failed / proceeding without
journalctl -u aitbc-coordinator-api --since "5 min ago" --no-pager | grep -i "Payment creation failed" || true
```

---

## Related Resources

- [Coordinator API Reference](../apps/coordinator-api/README.md)
- [Next Scenario: GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
