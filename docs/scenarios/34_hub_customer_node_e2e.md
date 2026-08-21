# Hub↔Customer Node End-to-End

**Level**: Intermediate
**Prerequisites**: [Scenario 33 Exchange Financial Correctness](./33_exchange_financial_correctness.md), [Scenario 07 AI Job Submission](./07_ai_job_submission.md)
**Estimated Time**: 25 minutes
**Last Updated**: 2026-08-21
**Version**: 1.4

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Hub↔Customer Node End-to-End

---

## See Also

- **Previous Scenario**: [Scenario 33 Exchange Financial Correctness](./33_exchange_financial_correctness.md)
- **Next Scenario**: [Scenario 35 Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md)
- **Closed cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md)
- **Feature Documentation**: [Service Ports Reference](../reference/SERVICE_PORTS.md)

---

## Scenario Overview

This is the product path: a customer CLI on the hub (or a follower pointed at the hub) pays a shop miner for an Ollama job; escrow releases on-chain; the shop republishes a GPU software offer.

Hub RPC/coordinator/exchange often bind `127.0.0.1`. Public access is nginx (`https://hub.aitbc.bubuit.net/…`) or an SSH tunnel — not raw LAN `:8202`. The CLI should use configured hub URLs (`HUB_DISCOVERY_URL` / `HUB_P2P_HOST` / `HUB_RPC_URL`), not hardcoded localhost (A6).

### Use Case

Prove tokens → job → GPU → `ESCROW_RELEASE` → marketplace offer on the live two-node island.

### What You'll Learn

- How to point `aitbc` at the hub
- How to submit unpaid and paid jobs with `aitbc ai`
- How to check escrow with `aitbc wallet` / `aitbc account`
- How to publish and list GPU offers with `aitbc market`
- How to health-check the bridge and exchange from the CLI

---

## Prerequisites

### Tools Required

- `aitbc` on both hub and shop
- A funded customer wallet and a way to log in (`aitbc auth login`) or an existing JWT for `--api-key`

### Setup Required

- Hub: coordinator, wallet, exchange, explorer
- Hub blockchain RPC: `ESCROW_RELEASE_PRIVATE_KEY` and `ESCROW_RELEASE_ADDRESS` in `/etc/aitbc/node.env` (or `/etc/aitbc/blockchain.env`), or fallback to `GENESIS_WALLET_PRIVATE_KEY`
- Shop: miner, GPU, Ollama `llama3.2:3b`, funded provider wallet (e.g. `test-wallet-3`)
- Buyer: genesis or another funded wallet

---

## Step-by-Step Workflow

### Step 1: Identify the hub

On the hub:

```bash
hostname
aitbc version
aitbc explorer chain-head
```

**Expected output (live):** hostname `hub.aitbc.bubuit.net`, CLI `0.10.18`, a chain height that the shop will match.

### Step 2: Know the bind / public path

Hub `8202/8203/8106/8107` are typically `127.0.0.1`. Options:

1. Run customer CLI **on the hub** (this play).
2. SSH tunnel: `ssh -L 8202:localhost:8202 -L 8203:localhost:8203 -L 8106:localhost:8106 user@hub.aitbc.bubuit.net`
3. nginx public URLs for marketplace / miner callbacks.

Do not assume shop can `curl` hub LAN ports.

### Step 3: Configure the customer CLI

```bash
aitbc config show
aitbc config set coordinator_api_url http://127.0.0.1:8203
```

On a follower, set hub discovery in `/etc/aitbc/node.env` (`HUB_DISCOVERY_URL`, `HUB_RPC_URL`, `HUB_P2P_HOST`). `aitbc config set` currently knows `coordinator_api_url`, `agent_coordinator_url`, `api_key`, `timeout` — other URLs come from those env files.

### Step 4: Connectivity through CLI (not a port loop)

```bash
aitbc explorer chain-head
aitbc bridge health
aitbc wallet list
aitbc exchange-island rates
```

**Expected output:** chain head, bridge healthy, wallets listed, exchange rates or a labeled simulated fallback.

### Step 5: Unpaid job

```bash
aitbc --api-key "$CLIENT_JWT" --output json ai submit \
  --prompt "Cross-node unpaid job" \
  --coordinator-url http://127.0.0.1:8203
aitbc --api-key "$CLIENT_JWT" ai status --job-id "$JOB_ID"
aitbc --api-key "$CLIENT_JWT" ai jobs --limit 5
```

**Expected output:** `QUEUED` then `COMPLETED` on `aitbc-miner-1` with `payment_status` none/skipped.

### Step 6: Bridge validation from CLI

```bash
aitbc bridge health
aitbc bridge lock --target-chain "" --sender 0xabc --recipient 0xdef --amount 10 --signature 0x123
```

**Expected output:** health OK; lock aborted / 422 (empty chain). Same B13 check as scenario 22.

### Step 7: Exchange from CLI

```bash
aitbc exchange-island orderbook AIT/ETH --limit 10
aitbc exchange-island orders --status open
```

**Expected output:** book/orders. Do not POST `/v1/exchange/orders`.

### Step 8: Paid job + escrow + on-chain settlement

The release transaction is signed by the key in `ESCROW_RELEASE_PRIVATE_KEY` (set in `/etc/aitbc/node.env` on the hub). If the variable is not configured, the node falls back to `GENESIS_WALLET_PRIVATE_KEY`. The settlement address is derived from the release key unless `ESCROW_RELEASE_ADDRESS` is set explicitly.

On the hub:

```bash
aitbc --api-key "$CLIENT_JWT" --output json ai submit \
  --prompt "Cross-node paid job test" \
  --payment 1.0 \
  --wallet genesis \
  --buyer-address <customer-ait1-or-aitbc1> \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203
```

**Expected output:** `payment_status: escrowed`, a `payment_id`.

Wait, then:

```bash
aitbc --api-key "$CLIENT_JWT" --output json ai status --job-id "$JOB_ID"
aitbc --api-key "$CLIENT_JWT" ai results --job-id "$JOB_ID"
```

**Expected output:** `COMPLETED`, `payment_status: released`.

On the shop (or any CLI that talks to the hub wallet/RPC):

```bash
aitbc wallet balance test-wallet-3
aitbc wallet transactions test-wallet-3
aitbc account get --address aitbc1a54b82312beb65d0e90c21717ea372396991fa36
```

**Expected output:** provider balance includes the 0.9750 AIT release (1.0 minus fee); an `ESCROW_RELEASE` tx; `account get` shows compute-seconds (3510 per 0.975 AIT).

Live replay 2026-08-20: job `4ad8e281871640fa8b1b25716c92c2c8`, release `0xa6dab9b7…` in hub block **7548**, `test-wallet-3` **1.9500 AIT** after two releases.

### Step 9: GPU marketplace offer from the shop

On `aitbc3` as the `aitbc` user (island credentials are `aitbc:aitbc` mode 600; `blockchain-secrets.env` is root:600 — do not chown as a workaround):

```bash
aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0
```

On the hub/customer:

```bash
aitbc market list --service-type ollama
```

**Expected output:** `llama3.2:3b` @ `0.00100000 per_1k_tokens`, Node ID `aitbc3`, plus an on-chain `GPU_MARKETPLACE` hash.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run the inner loop with `aitbc` only (config, ai, wallet, account, market, bridge, exchange-island)
- See `ESCROW_RELEASE` in the provider wallet
- List the shop GPU offer from the hub
- Explain why raw hub LAN ports time out

---

## Validation

```bash
# Logs only — not the play
journalctl -u aitbc-coordinator-api --since "10 min ago" --no-pager | grep -c job_id || true
journalctl -u aitbc-miner --since "10 min ago" --no-pager | grep -i completed || true
```

Authenticate the CLI customer (hub):

```bash
aitbc auth login --wallet customer-wallet --password <password>
# or with a raw key in a CI context:
# aitbc auth login --wallet-address 0xCustomer1 --private-key-file /run/secrets/customer.key
```

---

## Related Resources

- [DESIGN_CYCLE.md](../DESIGN_CYCLE.md)
- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [Next Scenario: Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md)

---

*Last updated: 2026-08-21*
*Version: 1.4*
