# Live two-node AI job validation summary

**Date:** 2026-08-20  
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)  
**Gitea `main` baseline:** `49b749cc0` — *fix escrow release signature, allow unsigned GPU_MARKETPLACE offers, and fix qa-cycle token source*

---

## What was validated end-to-end

### 1. Paid AI job with escrow and on-chain settlement

Run from `hub.aitbc`:

```bash
aitbc --api-key <client-jwt> ai submit --prompt "signature test 2" --payment 1.0 \
  --wallet genesis --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36
```

- Job `1966e9fa7eef43c094012cbe9372df3f` queued, assigned to `aitbc-miner-1`, completed.
- Payment `1.0 AITBC` was escrowed and auto-released on completion.
- Escrow release transaction `0x2e2bc040...` was signed by the genesis key, accepted by `POST /rpc/transactions/marketplace`, and applied in block `7423`.

Provider balance and transaction history:

```bash
aitbc wallet balance test-wallet-3
aitbc wallet transactions test-wallet-3
```

- Wallet balance: `0.9750 AIT`.
- Wallet transactions: 1 confirmed `ESCROW_RELEASE` from the genesis address.

### 2. GPU marketplace offer publication from `aitbc3`

Run from `aitbc3`:

```bash
aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0
```

- Software offer `ollama-llama3.2-3b` published on-chain as a `GPU_MARKETPLACE` transaction.
- Offer registered in the hub marketplace service.
- `aitbc market list --service-type ollama` shows the new offer.

### 3. Wallet / explorer 404 fix (gitea `main` `eec9f22ac`)

- `aitbc account get --address ait1fe2d63...` returns `200 OK`.
- `aitbc wallet transactions test-wallet-3` returns the confirmed `ESCROW_RELEASE` transaction.

---

## Gitea changes merged to `main`

1. **PR #275** (`b5b16a7ff`) — escrow release signature + transaction query chain default.
   - `_submit_payment_tx` signs `ESCROW_RELEASE` with `GENESIS_WALLET_PRIVATE_KEY`.
   - Provider account is created on-chain if missing.
   - `query_transactions` and `get_chain_id` default an empty/missing `chain_id` to the node's configured `chain_id`.

2. **Commit `0881916df`** — allow unsigned `GPU_MARKETPLACE` offer transactions.
   - Value-carrying transactions (`ESCROW_RELEASE`, `TRANSFER`) still require a valid signature.
   - Zero-amount marketplace offers are accepted without a secp256k1 signature, matching the CLI's current capabilities.

3. **Commit `5455f5c6b`** — fix `aitbc market offer` to use `/v1/marketplace/offer` (the previous `/v1/marketplace/software-services` path did not exist).

4. **Commit `49b749cc0`** — `qa-cycle.py` reads `GITEA_TOKEN` from `GITEA_TOKEN` env or `~/.gitea_token`, never from a repository file.

---

## What is still open

- Scrub the historical `.gitea_token.sh` from gitea history (`scripts/cleanup_token_history.sh` exists).
- Update documentation/scenarios to reflect the working paid-job + on-chain settlement flow.
- Update the release change log on `aitbc3` if the release process requires it.

---

## Next steps

**Agent A (live two-node / gitea work):**

- [x] Fix `escrow_routes.py::_submit_payment_tx` to sign the `ESCROW_RELEASE` marketplace transaction.
- [x] Restart `aitbc-blockchain-rpc` on `hub.aitbc` and `aitbc3`.
- [x] Re-test a paid AI job and confirm on-chain payment.
- [x] Continue GPU marketplace offer publication from `aitbc3`.

**Agent B (documentation / support):**

- [ ] Update scenario documentation with the new paid-job + on-chain settlement and GPU marketplace offer steps.
- [ ] Update the release change log if required.
