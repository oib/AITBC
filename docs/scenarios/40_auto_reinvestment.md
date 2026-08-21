# Scenario 40: Automatic reinvestment from released escrow

## Goal

Submit a paid AI job and, when the escrow is released, automatically stake a
configurable percentage of the provider's earnings. Verify the stake is created
on-chain and reported in the job status.

## Preconditions

- Coordinator, blockchain RPC, and a GPU miner are running.
- Customer wallet has balance; `SHOP_WALLET_ADDRESS` is the provider.

## Steps

1. Submit a job with a reinvestment percentage:
   ```bash
   export CUSTOMER_WALLET_ADDRESS=<customer>
   export SHOP_WALLET_ADDRESS=<shop>
   aitbc ai submit --payment 5 --auto-reinvest-pct 25 \
     --prompt "what is automatic reinvestment" --model llama3.2:3b
   ```

2. Wait for completion and status:
   ```bash
   aitbc ai status --job-id <job_id>
   ```

3. Expected result:
   - `state`: `COMPLETED`
   - `payment_status`: `released`
   - `auto_reinvest_pct`: `25.0`
   - `reinvest_status`: `staked`
   - `reinvest_stake_id`: a non-empty string

4. Verify the stake on-chain:
   ```bash
   curl -s http://<blockchain-rpc>/rpc/staking/<SHOP_WALLET_ADDRESS>
   ```
   The provider's `total_staked` includes the new stake and the stake's
   `amount` equals `payment * (pct / 100) * 3600` compute-seconds.

## Notes

- The reinvestment percentage must be between 0 and 100.
- The provider address is taken from `provider_address`; if omitted, no
  reinvestment occurs even if a percentage is set.
