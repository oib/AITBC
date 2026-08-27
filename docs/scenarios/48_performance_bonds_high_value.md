# Scenario 48: Performance bonds for high-value jobs

## Goal

Require an active provider performance bond for high-value AI jobs and verify that
only bonded miners are assigned. Show the bond lifecycle through the canonical
`aitbc` CLI.

## Preconditions

- Coordinator API running on the hub (`aitbc-coordinator-api.service`).
- Active `aitbc-miner` registered with a known `miner_id` (e.g. `aitbc-miner-1`).
- Customer wallet with enough AIT for the payment (e.g. `genesis`).
- A client JWT for coordinator authentication.

## Variables

```bash
CUSTOMER=0xFe2d63FE87Db282083b9159e5857Cac788af9E03
PROVIDER=0xA54B82312beb65D0E90c21717ea372396991Fa36
MINER_ID=aitbc-miner-1
```

## Step 1: Create a performance bond for the provider

```bash
export COORDINATOR_API_URL=http://127.0.0.1:8203
export WALLET=customer-wallet

# Log in once with a funded customer wallet; subsequent commands use the stored token.
aitbc auth login --wallet "$WALLET" --coordinator-url "$COORDINATOR_API_URL"

aitbc bond create "$MINER_ID" \
  --amount 10 \
  --required-amount 10
```

Expected output:

```json
{
  "provider_id": "aitbc-miner-1",
  "bond_id": "bond-aitbc-miner-1",
  "status": "active",
  "amount": "10.00000000",
  "required_amount": "10.00000000"
}
```

## Step 2: Check provider eligibility

```bash
aitbc bond status "$MINER_ID"
```

Expected output: `eligible: true`, `status: active`.

## Step 3: Submit a high-value job with explicit bond requirement

```bash
aitbc ai submit \
  --prompt "Bonded high-value job validation" \
  --payment 5 \
  --bond-required \
  --wallet genesis \
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

## Step 4: Submit a job above the default high-value threshold

The default `COORDINATOR_BOND_HIGH_VALUE_THRESHOLD` is 10 AIT. A job with
`payment 10` automatically requires a bond even without `--bond-required` (it
also triggers the default ZK and TEE gates from scenarios 46 and 47).

```bash
aitbc ai submit \
  --prompt "Automatic high-value bond validation" \
  --payment 10 \
  --wallet genesis \
  --buyer-address "$CUSTOMER" \
  --provider-address "$PROVIDER" \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 300
```

Expected result: `COMPLETED`, `payment_status: released`, `bond_required` is
implied by the payment amount and the job is only assigned because the provider
has an active bond.

## Step 5: Lock and release the bond (optional, governance/admin path)

A bond can be locked while a high-value job is in flight and released afterward:

```bash
aitbc bond lock "$MINER_ID"
aitbc bond release "$MINER_ID"
```

A bond can be slashed for misbehavior and then appealed:

```bash
aitbc bond slash "$MINER_ID" --reason "failed SLA"
aitbc bond appeal <bond-id> --reason "dispute"
```

## What the CLI actually does

- `aitbc bond create` `POST`s to `/v1/marketplace/providers/{provider_id}/bonds`
  and creates a `ProviderBond` record with `status: active`.
- `aitbc bond create` `POST`s to `/v1/marketplace/providers/{provider_id}/bonds`
  and creates a `ProviderBond` record. If the posted `amount` is below the
  global floor (`COORDINATOR_BOND_MIN_AMOUNT`, default 1 AIT) or the supplied
  `required_amount`, the bond is left in `PENDING` until it is topped up.
- `aitbc bond status` `GET`s `/v1/marketplace/providers/{provider_id}/eligibility`
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
- Live validation on `hub.aitbc` + `aitbc3`:
  - `aitbc bond create aitbc-miner-1 --amount 10 --required-amount 10` → active
    bond.
  - `aitbc bond status aitbc-miner-1` → `eligible: true`.
  - `aitbc ai submit --payment 5 --bond-required` → `COMPLETED`, `payment_status: released`,
    `bond_required: true` in receipt constraints.
  - `aitbc ai submit --payment 10` (above threshold) → `COMPLETED` and released.

## Notes

- On-chain bond locking, slashing, and release are not yet implemented in the
  current state transition layer; the `ProviderBond` record is the source of
  truth for eligibility in this slice. Escrowed payment and reputation still
  provide the economic deterrent.
- Set `COORDINATOR_BOND_HIGH_VALUE_THRESHOLD=0` to require a bond for every job,
  or `-1` to disable the automatic high-value gate.
- The `aitbc bond appeal` command posts to `/v1/governance/slash-appeals` and
  requires a governance review.
