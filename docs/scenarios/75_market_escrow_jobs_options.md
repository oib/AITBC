# Market Escrow & Jobs Listing Options

**Level**: Intermediate
**Prerequisites**: Scenario 07 AI Job Submission (for job IDs and offers)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-27
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Market Escrow & Jobs Options

---

## Scenario Overview

> **Option-coverage scenario (ESCROW-OPTS-1).** This play walks the filter
> and formatting flags of `aitbc market jobs` and the optional flags of
> `aitbc market escrow create`. The `jobs` lines are read-only. The
> `escrow create` lines move funds — run them only against a deliberately
> unknown wallet name (as below) so the CLI refuses before any signing,
> or on a funded test wallet under the SCENARIO-PLAY-3 spend caps.

### What You'll Learn

- How to filter market job listings by service type, state, buyer and offer
- How to switch the CLI output renderer (`--output` / `--format`)
- Which optional flags `market escrow create` accepts on top of the
  required `--job-id` / `--buyer` / `--provider`

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A configured hub (the jobs listing calls `GET /v1/market/jobs` on the hub)

---

## Steps

### Step 1: List market jobs with filters (read-only)

```bash
aitbc market jobs --service-type ipfs --state active --limit 50
```

Filter by buyer and by offer:

```bash
aitbc market jobs --buyer-address 0x0000000000000000000000000000000000000001 --offer-id sw_offer_20261023093833_0ad81bde
```

### Step 2: Change the output renderer (read-only)

```bash
aitbc market jobs --limit 10 --output json
```

```bash
aitbc market jobs --state active --format json
```

### Step 3: Escrow create optional flags (money-path — refusal play)

`escrow create` requires `--job-id`, `--buyer` and `--provider`; `--amount`
and `--wallet` are the optional flags under test. Passing a wallet name
that does not exist makes the CLI refuse at wallet resolution — before
any signing or network submission — so the flags are exercised for free:

```bash
aitbc market escrow create --job-id escopts1-probe --buyer 0x0000000000000000000000000000000000000001 --provider 0x0000000000000000000000000000000000000002 --amount 0.5 --wallet nosuch-escopts1
```

**Expected output:** `Error creating escrow: Wallet 'nosuch-escopts1' not
found as a file wallet.` (non-zero exit; nothing signed, nothing spent).

> **Known drift (recorded under ESCROW-OPTS-1):** `aitbc market jobs`
> currently aborts with an uncaught `TypeError` — `GET /v1/market/jobs`
> returns a JSON array while `_market_client().get()` expects a JSON
> object. The filter flags above still reach the request path (the params
> dict is built before the call); the crash is in response handling and
> needs a client-side fix.
>
> **Known drift 2:** `--amount` values that are not numbers are silently
> coerced to `0` by `wallet_amount()` instead of being refused at
> arg-parse time; the command then aborts later on the wallet or the
> positivity check rather than on the bad input.

---

## See Also

- **Scenario 34**: [Hub–Customer E2E](./34_hub_customer_node_e2e.md) — live paid job + escrow release
- **Scenario 44**: [Refund a Failed TEE Job Escrow](./44_stuck_tee_refund.md)

---

*Last updated: 2026-10-27 (ESCROW-OPTS-1 option coverage)*
*Version: 1.0*
