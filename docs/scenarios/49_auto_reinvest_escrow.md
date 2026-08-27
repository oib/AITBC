# Scenario 49: Auto-reinvest from released escrow

## Goal

When a paid AI job completes and escrow is released, automatically stake a
configured percentage of the provider's earnings on-chain.

## Preconditions

- Coordinator API and blockchain RPC/nodes running on the hub.
- Registered `aitbc-miner` with an on-chain `Account` that has enough spendable
  balance to absorb the timing between escrow release and auto-stake (the
  protocol stakes from the provider's current balance; the just-released
  transaction is credited in the same block).
- Customer wallet with enough AIT for the job payment.

## Variables

```bash
CUSTOMER=0xFe2d63FE87Db282083b9159e5857Cac788af9E03
PROVIDER=0xA54B82312beb65D0E90c21717ea372396991Fa36
WALLET=genesis
```

## Step 0: Log in

```bash
aitbc auth login --wallet "$WALLET"
```

## Step 1: Submit a paid job with auto-reinvest

```bash
aitbc ai submit \
  --prompt "Auto reinvest validation" \
  --payment 5 \
  --auto-reinvest-pct 50 \
  --wallet "$WALLET" \
  --buyer-address "$CUSTOMER" \
  --provider-address "$PROVIDER" \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 240
```

The `--auto-reinvest-pct 50` flag is stored in `job.constraints.auto_reinvest_pct`
and is passed through `JobPaymentCreate` into the payment's `meta_data`.

## Step 2: Verify the job result/receipt

Expected result fields:

```json
{
  "job_id": "84de66093d0647f7b4a4d35bbda44bd0",
  "state": "COMPLETED",
  "payment_status": "released",
  "escrow_tx_hash": "0xef05c4bf6351d8ec480eca9dcef21528034907eff980823eb920d3b9d65bf8f7",
  "receipt": {
    "reinvest_status": "staked",
    "reinvest_stake_id": "8",
    "reinvest_amount": "2.43750000",
    "metadata": {
      "job_constraints": {
        "auto_reinvest_pct": "50.0",
        ...
      }
    }
  },
  "status": {
    "reinvest_status": "staked",
    "reinvest_stake_id": "8",
    "auto_reinvest_pct": "50.0"
  }
}
```

## Step 3: Confirm the on-chain stake

On the blockchain node, the `stake` table now contains an active stake for the
provider:

```bash
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
  "SELECT id, address, amount, locked_until, status FROM stake WHERE id=8;"
```

Example output:

```text
8|0xa54b82312beb65d0e90c21717ea372396991fa36|8775|2026-09-20 21:16:41.185874|active
```

`8775` compute-seconds is `2.4375 AIT * 3600`. The `locked_until` date is 30 days
from the release.

## What the CLI and pipeline do

1. `aitbc ai submit --auto-reinvest-pct 50` sets
   `job_data["constraints"]["auto_reinvest_pct"] = 50.0`.
2. The coordinator's `POST /v1/jobs` handler passes the percentage into
   `JobPaymentCreate(auto_reinvest_pct=...)`.
3. `PaymentService.create_payment` stores it in `payment.meta_data`.
4. When the miner completes the job, `PaymentService.release_payment` reads the
   percentage (falling back to `job.constraints` if needed) and includes it in
   the blockchain escrow release call:
   `POST /rpc/escrow/{job_id}/release` with `auto_reinvest_pct` and
   `auto_reinvest_address`.
5. The blockchain `release_escrow` endpoint releases the payment, computes
   `reinvest_amount = released_amount * pct / 100`, and calls `_auto_stake`.
6. `_auto_stake` canonicalizes the provider address, finds the on-chain
   `Account`, debits the stake amount, and inserts an active `Stake` record.
7. The blockchain release response returns `reinvest_stake_id` and
   `reinvest_amount`.
8. `PaymentService.release_payment` stores these in `payment.meta_data`.
9. The miner result router attaches `reinvest_status`, `reinvest_stake_id` and
   `reinvest_amount` to the job receipt so the CLI can display them.

## Validation

- `cli/tests/test_cli_comprehensive.py` + `test_cli_basic.py` — 33 passed.
- Live on `hub.aitbc` + `aitbc3`:
  - `aitbc ai submit --payment 5 --auto-reinvest-pct 50 --wait` → `COMPLETED`,
    `payment_status: released`, `reinvest_status: staked`, `reinvest_stake_id: 8`,
    `reinvest_amount: 2.43750000`.
  - On-chain `stake` record `8` is `active` with `amount: 8775` compute-seconds.

## Notes

- The auto-stake currently debits the provider's existing spendable balance; the
  released escrow transaction is applied in the same block, so the provider's
  final spendable balance is `old_balance + released - fee - reinvested`. For a
  brand-new provider with zero balance, the first auto-reinvest may be skipped
  because the balance is not yet available at the moment `_auto_stake` runs.
- `locked_until` is set to 30 days from release, matching the default staking
  lock period.
- The stake amount is net of the platform fee: for a 5 AIT payment with a 2.5 %
  platform fee and 50 % reinvestment, the staked amount is 2.4375 AIT.
