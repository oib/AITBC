# Scenario 48: Performance bonds for high-value jobs

> **Post-v18 coverage note (31 Oct):** the bond record types this scenario exercises are sealed on bc-2 — `BOND_LOCK` @9816 (+9822), `BOND_RELEASE` @9820, `BOND_SLASH` @9825 and again @12856 (bonded-job failure path, stress-3). Coverage folded per #665.

> **v0.14.4+ behavior.** Only `linear-1` is registered in `MODEL_CIRCUITS`;
> any other model (e.g. `llama3.2:3b`) yields `zk_status: unsupported_model`
> → `computation_correct=False` → escrow blocked/refunded. The `verified`/
> `released` expectations below are pre-v0.14.4 — see scenario 34 for the
> corrected refund flow.

> Payment ≥10 fires the default ZK+TEE gates — the shop model is unregistered → refund, not release.

## Goal

Require an active provider performance bond for high-value AI jobs and verify that
only bonded miners are assigned. Show the bond lifecycle through the canonical
`aitbc` CLI.

## Preconditions

- Coordinator API running on the hub (`aitbc-coordinator-api.service`).
- Active `aitbc-miner` registered with a known `miner_id` (e.g. `aitbc-miner-1`).
- A funded customer file wallet on the submit host (there is **no**
  `genesis` wallet — resolve the live name, e.g. `default`).
- A client JWT for coordinator authentication.

## Variables

```bash
# No `genesis` wallet exists — resolve live. CUSTOMER is the buyer's 0x
# address; PROVIDER must be the live miner payout wallet (verify — it
# changes with miner re-provisioning; node2's `default` wallet as of
# 21 Nov). MINER_ID must be re-resolved per Step 1.
CUSTOMER=<customer-0x-address>
PROVIDER=0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2   # node2 `default` — live miner wallet, verify
CUSTOMER_WALLET=default   # funded file wallet on the submit host
MINER_ID=aitbc-miner-1   # must be the *registered* Miner.id — see Step 1
BOND_ID=bond-s48-1       # chosen bond_id for the on-chain BOND_LOCK
BOND_ESCROW_ADDRESS=<node BOND_ESCROW_ADDRESS>  # chain env config, not on RPC
```

## Step 1: Resolve the live miner id

Bond eligibility is keyed on the coordinator's `Miner.id`, **not** on the
provider wallet address. A bond placed on a stale or ghost `provider_id`
does not make the live miner eligible — bonded jobs stay `QUEUED` even
though a miner with the same wallet is online and polling (observed live:
bond on `miner-747ba6e6…` left `aitbc-miner-1` ineligible, #2296).

Confirm the id the miner actually registered with before bonding:

```bash
# on the miner host — the registration log prints the live id:
journalctl -u aitbc-miner --no-pager | grep "registered miner"

# or via the coordinator (admin auth):
curl -s "$COORDINATOR_API_URL/v1/miners" -H "Authorization: Bearer $ADMIN_JWT" | jq '.[].id'
```

Set `MINER_ID` to that value — for the current shop deployment it is
`aitbc-miner-1`.

## Step 2: Lock the bond on-chain, then record it coordinator-side

`bond create`/`bond top-up` now **require** `--bond-id` naming an
*active* on-chain `BOND_LOCK` — a bare `bond create` is refused with
HTTP 400 (`bond_id is required: bonds activate only from a verified
on-chain BOND_LOCK record`). The missing leg is `bond lock-onchain`,
which submits the signed `BOND_LOCK` escrow transaction. Run it on the
provider's host (node2) where the provider file wallet lives — the tx
pays `--escrow-address` (the node's `BOND_ESCROW_ADDRESS` chain env
config) with payload `{bond_id, provider, lock_days}` and the chain
refuses any signer other than `provider`:

```bash
# on node2 — submit the on-chain BOND_LOCK first:
aitbc bond lock-onchain --bond-id "$BOND_ID" \
  --escrow-address "$BOND_ESCROW_ADDRESS" \
  --amount 10 --wallet <provider-file-wallet>   # e.g. default on node2

# then record the bond coordinator-side against that bond_id:
export COORDINATOR_API_URL=http://127.0.0.1:8203
export WALLET="$CUSTOMER_WALLET"

# Log in once with a funded customer wallet; subsequent commands use the stored token.
aitbc auth login --wallet "$WALLET" --coordinator-url "$COORDINATOR_API_URL"

aitbc bond create --provider-id "$MINER_ID" \
  --bond-id "$BOND_ID" \
  --amount 10 \
  --required-amount 10
```

Non-admin callers must also prove control of the provider's registered
wallet on create/top-up (#1967): pass `--wallet`/`--private-key`/
`--private-key-file` and the CLI signs the `bonds/challenge` proof
automatically; an admin JWT passes unsigned.

Expected output:

```json
{
  "provider_id": "aitbc-miner-1",
  "bond_id": "bond-s48-1",
  "status": "active",
  "amount": "10.00000000",
  "required_amount": "10.00000000"
}
```

## Step 3: Check provider eligibility

```bash
aitbc bond status --provider-id "$MINER_ID"
```

Expected output: `eligible: true`, `status: active`.

## Step 4: Submit a high-value job with explicit bond requirement

```bash
aitbc ai submit \
  --prompt "Bonded high-value job validation" \
  --payment 5 \
  --bond-required \
  --wallet "$CUSTOMER_WALLET" \
  --buyer-address "$CUSTOMER" \
  --provider-address "$PROVIDER" \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 240
```

Expected result:

```json
{
  "job_id": "<job_id>",
  "state": "COMPLETED",
  "payment_status": "released",
  "escrow_tx_hash": "0x...",
  "status": {
    "assigned_miner_id": "aitbc-miner-1",
    "payment_status": "released"
  },
  "receipt": {
    "metadata": {
      "job_constraints": {
        "bond_required": true,
        "min_bond_amount": null,
        ...
      }
    }
  }
}
```

## Step 5: Submit a job above the default high-value threshold

The default `COORDINATOR_BOND_HIGH_VALUE_THRESHOLD` is 10 AIT. A job with
`payment 10` automatically requires a bond even without `--bond-required` (it
also triggers the default ZK and TEE gates from scenarios 46 and 47).

```bash
aitbc ai submit \
  --prompt "Automatic high-value bond validation" \
  --payment 10 \
  --wallet "$CUSTOMER_WALLET" \
  --buyer-address "$CUSTOMER" \
  --provider-address "$PROVIDER" \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 300
```

Expected result: `COMPLETED`, `payment_status: released`, `bond_required` is
implied by the payment amount and the job is only assigned because the provider
has an active bond.

## Step 6: Lock and release the bond (optional, governance/admin path)

A bond can be locked while a high-value job is in flight and released afterward:

```bash
aitbc bond lock --provider-id "$MINER_ID"
aitbc bond release --provider-id "$MINER_ID"
```

> **No withdrawal path:** `bond release` only un-locks a LOCKED bond back
> to `active` — the bonded amount stays posted. There is no endpoint that
> frees bond funds; only `slash` (with a governance appeal path) moves
> them.

A bond can be slashed for misbehavior and then appealed:

```bash
aitbc bond slash --provider-id "$MINER_ID" --reason "failed SLA"
aitbc bond appeal --bond-id <bond-id> --reason "dispute"
```


---

<!-- PLAY3 coverage extension: uncovered CLI leaves folded into this scenario (issue #438) -->

## Step 7: Top up a performance bond

Adds funds to an existing provider bond. Like `create`, `top-up` requires
`--bond-id` of an active on-chain `BOND_LOCK` (HTTP 400 otherwise).

Cost: 10 AIT locked (`--amount` is a free-form decimal string, AIT-denominated).

```bash
aitbc bond top-up --provider-id "$MINER_ID" --bond-id "$BOND_ID" --amount 10
```

---

## What the CLI actually does

- `aitbc bond lock-onchain --bond-id … --escrow-address … --amount …
  --wallet …` submits the on-chain `BOND_LOCK` escrow transaction
  (`provider` = the signing wallet's own address; the chain refuses any
  other signer). It must run and seal **before** `bond create`/`top-up`,
  which verify the `bond_id` against chain state and refuse (HTTP 400)
  when it is missing, not this provider's, or not `active`.
- `aitbc bond create` `POST`s to `/v1/market/providers/{provider_id}/bonds`
  and creates a `ProviderBond` record with `status: active` — only when
  `--bond-id` names that verified on-chain bond.
- Since #1967, non-admin callers must prove control of the provider's
  registered wallet: pass `--wallet`/`--private-key`/`--private-key-file`
  and the CLI fetches a single-use challenge from
  `POST .../bonds/challenge`, signs the returned message (EIP-191), and
  posts `challenge_nonce` + `wallet_signature` with the create. A chain
  `bond_id` may back exactly one provider — a second provider binding the
  same `bond_id` gets 409.
- `aitbc bond create` `POST`s to `/v1/market/providers/{provider_id}/bonds`
  and creates a `ProviderBond` record. If the posted `amount` is below the
  global floor (`COORDINATOR_BOND_MIN_AMOUNT`, default 1 AIT) or the supplied
  `required_amount`, the bond is left in `PENDING` until it is topped up.
- `aitbc bond status` `GET`s `/v1/market/providers/{provider_id}/eligibility`
  and returns `eligible: true` only when the bond is `active` or `locked` and
  its `amount` is at least the required floor.
- `aitbc ai submit --bond-required` sets `job.constraints.bond_required = true`.
- `aitbc ai submit --min-bond-amount` sets `job.constraints.min_bond_amount`.
- The coordinator's `JobService._satisfies_constraints` checks
  `is_provider_eligible(session, miner.id, min_amount=...)` for any job that
  either:
  - has `bond_required: true`,
  - is above `COORDINATOR_BOND_HIGH_VALUE_THRESHOLD` (default 10 AIT), or
  - has `COORDINATOR_BOND_REQUIRE=true`.
- The `min_amount` passed to `is_provider_eligible` is
  `job.constraints.min_bond_amount` when set, otherwise the global
  `COORDINATOR_BOND_MIN_AMOUNT` floor.
- If the miner's bond is below the floor, the job is skipped and stays in the
  queue until a bonded provider with enough stake comes online.

## Validation

- `cli/tests/test_bond.py` — 5 tests covering `bond create`, `status`, `top-up`,
  `lock`, `release`, and `slash`.
- `cli/tests/test_cli_comprehensive.py` + `test_cli_basic.py` — 33 passed
  (regression).
- Live validation on `<hub-node>` + `<node2>`:
  - `aitbc bond lock-onchain --bond-id bond-s48-1 --escrow-address "$BOND_ESCROW_ADDRESS" --amount 10 --wallet default` → sealed `BOND_LOCK`.
  - `aitbc bond create --provider-id aitbc-miner-1 --bond-id bond-s48-1 --amount 10 --required-amount 10` → active
    bond.
  - `aitbc bond status --provider-id aitbc-miner-1` → `eligible: true`.
  - `aitbc ai submit --payment 5 --bond-required` → `COMPLETED`, `payment_status: released`,
    `bond_required: true` in receipt constraints.
  - `aitbc ai submit --payment 10` (above threshold) → `COMPLETED` and released.

## Notes

- On-chain bond locking, slashing, and release are handled in the state
  transition layer (`BOND_LOCK`/`BOND_RELEASE`/`BOND_SLASH` via
  `_handle_bond_transaction`); the `ProviderBond` record tracks eligibility
  for this slice. Escrowed payment and reputation still provide the
  economic deterrent.
- `provider_id` must equal the registered `Miner.id` (Step 1). Two miners
  may share a payout wallet — eligibility does **not** follow the wallet,
  so a bond on a stale/ghost `provider_id` leaves the live miner
  ineligible and bonded jobs queue forever (#2296).
- Settlement proven 20 Nov 2026: acceptance-window auto-release produced
  an on-chain `ESCROW_RELEASE` (bond `bond-s48-2`, 1.5 AIT on
  `aitbc-miner-1`; job `1b3c6f2b…` COMPLETED → release `0x28329bbc…`).
  Always verify `payment_status=released` **and** the release tx hash
  before claiming a paid leg.
- Set `COORDINATOR_BOND_HIGH_VALUE_THRESHOLD=0` to require a bond for every job,
  or `-1` to disable the automatic high-value gate.
- The `aitbc bond appeal` command posts to `/v1/governance/slash-appeals` and
  requires a governance review.
