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

When a job is submitted with a payment the coordinator cannot settle — e.g. a currency outside `AITBC`/`ETH`/`USDT` — `POST /v1/jobs` rejects it with **422 at submit** and no job row is created. Drive this with `aitbc ai submit --payment … --currency INVALID_CURRENCY`.

> **Contract note (2026-09-15):** this scenario originally specified "queued with `payment_status=skipped`, job runs unpaid". That behavior was a freeloader hole — a priced job running without escrow means the provider burns GPU time unpaid — and is deliberately unreachable since the G4 dispatch gate (`_PAYMENT_DISPATCHABLE_STATES = {"escrowed"}`). The contract is now fail-fast: invalid currency ⇒ 422, nothing queued.

### Use Case

A client fat-fingers the currency. The submission is refused immediately with a clear error; no orphaned job or payment row.

### What You'll Learn

- How to submit an unpaid and a bad-currency job through `aitbc ai`
- How to inspect `payment_status` with `aitbc ai status`

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A funded wallet (e.g. `customer-wallet`) and `aitbc auth login`

### Setup Required

- Coordinator API reachable (`aitbc config set --key coordinator_api_url --value http://127.0.0.1:8203` on the hub, or the public nginx path)

---

## Step-by-Step Workflow

Log in on the hub (do not scrape JWT secrets from env files):

```bash
# On the hub, with a funded customer wallet (coordinator API)
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

**Expected output:** HTTP 422 — the CLI reports the validation detail (`payment_currency must be one of: ['AITBC', 'ETH', 'USDT']`). No `job_id` is returned and nothing is queued.

### Step 2: Confirm nothing was queued

```bash
aitbc ai jobs --limit 5
```

**Expected output:** no job with the "B12 payment-failure probe" prompt exists — the invalid currency never created one.

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
- Confirm unpayable submissions fail fast (422) without orphaning a job
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
