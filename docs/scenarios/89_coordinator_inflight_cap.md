# Coordinator Inflight Cap

**Level**: Intermediate
**Prerequisites**: [Scenario 07 AI Job Submission](./07_ai_job_submission.md), [Scenario 25 Job Payment Failure](./25_job_payment_failure.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-11-15
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Coordinator Inflight Cap

---

## See Also

- **Related**: [Scenario 25 — Coordinator inflight cap (429)](./25_job_payment_failure.md#coordinator-inflight-cap-429)
- **Feature Documentation**: [Coordinator API Reference](../../apps/coordinator-api/README.md)

---

## Scenario Overview

The coordinator limits how many jobs a single authenticated client may hold in
`QUEUED` or `RUNNING` at once (`COORDINATOR_MAX_INFLIGHT_JOBS_PER_CLIENT`,
default 50). Additional `POST /v1/jobs` calls return **HTTP 429** with a clear
detail string — part of the #1948 resource-exhaustion policy; cap checks are
serialized per client (#2001).

This is a **read-only refusal play** on the live product path: authenticate on
the customer node (`node0`) or through the hub nginx coordinator gateway, inspect
existing jobs, and exercise one submit that surfaces 429 **only when** you are
already at the cap (do not flood production without operator approval).

### Live vs simulated

- **Live:** `aitbc ai submit` / `aitbc ai jobs` against the reachable coordinator
  (customer `node0` or hub gateway). 429 responses are labeled by the CLI from
  real coordinator HTTP status codes.
- **Simulated:** if the CLI cannot reach the coordinator, commands fail at
  connectivity — not a substitute for 429 behavior. Re-run on a node with a live
  coordinator URL in `aitbc config`.

### What You'll Learn

- How to authenticate with `aitbc auth login` for coordinator calls
- How to list active jobs and interpret queued/running counts
- How the inflight cap surfaces as HTTP 429 on submit
- Optional: corroborate refusal in `aitbc-coordinator-api` logs

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) on `$PATH`
- Customer wallet with coordinator access (`aitbc auth login --wallet <name>`)
- Coordinator URL configured (`aitbc config set --key coordinator_api_url …`
  or `--coordinator-url` on each command)

### Setup Required

- Run on **node0** (customer) or from a workstation tunneling to the hub
  coordinator via nginx — not from an unconfigured IDE host.

---

## Step-by-Step Workflow

### Step 1: Authenticate

```bash
aitbc auth login --wallet customer-wallet --coordinator-url https://hub.example.net/c/v1
```

### Step 2: Check active job count

```bash
aitbc ai jobs --limit 50 --format table
```

Note how many jobs are `pending`, `running`, or otherwise non-terminal. Compare
to `COORDINATOR_MAX_INFLIGHT_JOBS_PER_CLIENT` on the coordinator (default 50)
if you have read access to `/etc/aitbc/aitbc-coordinator-api.env`.

### Step 3: Submit at or above the cap

If you are already at the cap, a minimal unpaid probe submit should refuse:

```bash
aitbc --output json ai submit \
  --prompt "inflight-cap probe" \
  --coordinator-url https://hub.example.net/c/v1
```

**Expected output (at cap):** HTTP **429** — detail mentions
`client already holds N queued or running jobs (limit …)`. No new `job_id`.

If you are below the cap, document the configured limit instead of intentionally
filling the queue; or run this scenario in a dedicated test environment with a
low `COORDINATOR_MAX_INFLIGHT_JOBS_PER_CLIENT`.

### Step 4: List jobs again (read-only)

```bash
aitbc ai jobs --limit 5
```

Confirm the refused submit did not add a row when 429 was returned.

---

## Validation

Optional coordinator log line (hub only; requires service access):

```bash
journalctl -u aitbc-coordinator-api --since "10 min ago" --no-pager | grep -i "429\\|queued or running jobs" || true
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Recognize coordinator **429** responses as per-client inflight caps, not payment errors
- Use `aitbc ai jobs` before filing capacity-related incidents
- Point operators at #1948 / #2001 when cap behaviour regresses

---

## Related Resources

- [Scenario 25 — payment failure and cap cross-reference](./25_job_payment_failure.md)
- [Scenario 07 — AI job submission](./07_ai_job_submission.md)

---

*Last updated: 2026-11-15*
*Version: 1.0*
