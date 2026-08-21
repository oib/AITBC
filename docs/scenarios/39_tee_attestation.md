# Scenario 39: Confidential job with TEE attestation

## Goal

Run an inference job that requires a verified TEE attestation and confirm
escrow is only released after the attestation is stored and verified.

## Preconditions

- Coordinator running with ZK and TEE enabled.
- Miner running with `aitbc-miner` service that can generate simulated TEE quotes.
- Customer wallet with sufficient balance.

## Steps

1. Submit a confidential job:
   ```bash
   export CUSTOMER_WALLET_ADDRESS=<customer>
   export SHOP_WALLET_ADDRESS=<shop>
   aitbc ai submit --payment 5 --tee-attestation-required \
     --tee-enclave-id aitbc-miner-tee \
     --prompt "what is a TEE in two sentences" --model llama3.2:3b
   ```

2. Poll for completion:
   ```bash
   aitbc ai status --job-id <job_id>
   ```

3. Expected result:
   - `state`: `COMPLETED`
   - `payment_status`: `released`
   - `tee_status`: `verified`
   - `tee_attestation_id` is set.

## Variation: ZK + TEE

Combine high-value payment with TEE:
```bash
aitbc ai submit --payment 10 --zk-proof-required --tee-attestation-required \
  --tee-enclave-id aitbc-miner-tee --prompt "what is a TEE" --model llama3.2:3b
```

Expected result: `zk_status: verified`, `tee_status: verified`, payment released.

## Manual attestation

A miner can also attest an enclave directly:
```bash
aitbc --api-key <miner-key> tee attest aitbc-miner-tee --measurement aitbc-miner-tee
aitbc --api-key <miner-key> tee verify --quote <quote-b64> --measurement aitbc-miner-tee
```
