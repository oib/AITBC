# Customer and Shop Dashboards

**Level**: Beginner
**Prerequisites**: [Scenario 07 AI Job Submission](./07_ai_job_submission.md), [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-23
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Customer and Shop Dashboards

---

## See Also

- **Previous Scenario**: [Scenario 52 Wallet Key Mismatch Recovery](./52_wallet_key_mismatch.md)
- **Feature Documentation**: [Dashboard CLI source](../../cli/aitbc_cli/commands/dashboard.py)
- **Closed cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) P1.2

---

## Scenario Overview

This scenario exercises the two operational dashboards that the CLI exposes through `aitbc dashboard`. Both views talk to live node services: the customer view reads the coordinator API for jobs and the wallet daemon for balances; the shop view reads the coordinator for monitoring metrics, miner jobs/earnings, and marketplace offers, the local GPU service for hardware, and the wallet daemon for balances.

> **Live vs. simulated:** The dashboards are **live** when the coordinator, wallet daemon, and (for the shop) GPU/marketplace services are reachable. If a service is down, the command logs a warning and omits that section; it does **not** fall back to simulated data.

### Use Case

A customer wants to see recent jobs, payment statuses, and wallet balances. A shop operator wants to see assigned jobs, published marketplace offers, local GPUs, and earnings. Both use the same `aitbc dashboard` group, authenticated with `aitbc auth login`.

### What You'll Learn

- How to authenticate for dashboard calls with `aitbc auth login`
- How to view the customer dashboard with `aitbc dashboard customer`
- How to view the shop dashboard with `aitbc dashboard shop`
- Which services each dashboard depends on
- What to check when a section is empty or missing

---

## Prerequisites

### Knowledge Required

- Hub vs shop roles
- `aitbc auth login` workflow

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- A funded wallet
- A customer role with `aitbc auth login --wallet customer-wallet`
- A shop role with `aitbc auth login --wallet shop-wallet`
- At least one submitted AI job and one published marketplace offer for meaningful output

---

## Step-by-Step Workflow

### Step 1: Customer dashboard

On the hub or a follower pointed at the hub:

```bash
aitbc auth login --wallet customer-wallet
aitbc dashboard customer
```

**Expected output:** a table or JSON summary with:

- `total_jobs`
- `job_states` breakdown (`pending`, `running`, `completed`, `failed`)
- `payment_statuses` breakdown (`escrowed`, `paid`, `released`, `skipped`)
- `recent_jobs` with `Job ID`, `State`, `Payment`, `Model`, and `Created`
- `wallets` with `Wallet`, `Address`, and `Balance`

If the output is empty, check:

```bash
aitbc auth status
aitbc ai jobs
aitbc wallet list
```

A 403 or empty `recent_jobs` usually means the client token is missing or the wallet has the wrong role.

### Step 2: Shop dashboard

On the shop node:

```bash
aitbc auth login --wallet shop-wallet
aitbc dashboard shop
```

**Expected output:** a table or JSON summary with:

- `miner_id` (defaults to `NODE_ID` or hostname)
- `network_jobs_total`, `network_jobs_completed`, `network_jobs_pending`, `network_jobs_failed`
- `miners_total`, `miners_online`
- `gpus_found`
- `offers_published`
- `shop_assigned_jobs`
- `marketplace_offers` with `Plugin ID`, `Model`, `Price`, `Status`, `Rating`
- `wallets` with `Wallet`, `Address`, `Balance`
- `earnings` with `total`, `paid`, `pending`

If `offers_published` or `marketplace_offers` is empty, check:

```bash
aitbc market list
aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0
```

If `gpus_found` is 0, check the `aitbc-gpu` service:

```bash
aitbc gpu discover
aitbc system status
```

### Step 3: JSON output for scripts

Both commands support `--output json`:

```bash
aitbc --output json dashboard customer
aitbc --output json dashboard shop
```

This is the recommended format for automated checks, e.g. verifying that `offers_published > 0` after a shop restart.

### Step 4: Dashboard validation after a service restart

After restarting the shop role, run:

```bash
aitbc system status
aitbc dashboard shop
```

The dashboard should recover its values as services come online. If a section is still empty after 30 seconds, check the relevant service logs:

```bash
journalctl -u aitbc-coordinator-api -u aitbc-marketplace -u aitbc-gpu -u aitbc-wallet-daemon -n 50
```

---

## Validation

- `aitbc dashboard customer` shows the authenticated customer's jobs and wallet balances.
- `aitbc dashboard shop` shows the authenticated shop's offers, GPUs, assigned jobs, and earnings.
- `--output json` returns a parseable object for both views.
- Restarting the shop services and re-running `aitbc dashboard shop` repopulates the dashboard without simulated data.

---

## Cleanup

- No cleanup required; dashboard commands are read-only.

---

## Important notes

- The customer view requires a client JWT with `role: client`; the shop view requires `role: miner`. Obtain these with `aitbc auth login --wallet <wallet>`.
- The dashboards do **not** use mock or simulated data. Empty sections indicate the backing service is unreachable or the wallet has no data, not a CLI fallback.
- P1.2 (customer/shop dashboards talking to live APIs) is satisfied by `aitbc dashboard customer` and `aitbc dashboard shop`. A separate web UI is outside the CLI repo.
