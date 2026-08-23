# AITBC System Flow: From CLI Prompt to On-Chain Settlement

> **Authoritative port configuration** is in [Service Ports Reference](../reference/SERVICE_PORTS.md). This document describes the current CLI-driven flow on the live hub/shop island, not the historical `aitbc-cli.sh` wrapper or the old `cli/client.py`.

The canonical customer path on AITBC v0.10.18 is:

```text
aitbc wallet create → aitbc wallet fund <address> → aitbc --api-key <jwt> ai submit
     → coordinator (8203) → escrow on blockchain (8202)
     → shop miner polls coordinator → GPU service (8101) → Ollama (11434)
     → result → coordinator → POST /rpc/escrow/{job_id}/release
     → ESCROW_RELEASE transaction on blockchain
     → aitbc ai status, aitbc ai results, aitbc wallet transactions
```

## Overview

```
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
│ Customer │ → │  aitbc   │ → │ Coordinator  │ ↔ │ Blockchain   │ ← │  Shop    │ → │  Ollama  │
│  wallet  │   │   CLI    │   │   8203       │   │   8202       │   │  miner   │   │  11434   │
└──────────┘   └──────────┘   └──────────────┘   └──────────────┘   └──────────┘   └──────────┘
                                                                  ↑
                                                           GPU service 8101
                                                           marketplace 8102
                                                           pool-hub    8210
```

Public customer access to hub services is through nginx (`https://hub.aitbc.bubuit.net/...`) because the coordinator, exchange, and wallet daemon bind `127.0.0.1` by default. The shop miner daemon runs on the follower node and polls the hub coordinator; it is not a public service.

## Step-by-step flow

### 1. Acquire AIT and authenticate

```bash
aitbc wallet create customer-wallet standard
aitbc wallet fund <customer-address>
```

The CLI authenticates with the coordinator using a JWT passed via `--api-key` or the `AITBC_API_KEY` environment variable. If not using `aitbc auth login`, generate a client JWT locally:

```bash
python3 -c "from aitbc.auth import create_access_token; print(create_access_token('customer-node-user', 'client', {'wallet_address': '<customer-address>'}))"
```

`aitbc auth login` generates a wallet-signed JWT and stores it for subsequent commands; `--api-key` is still accepted as a fallback.

### 2. Discover compute

```bash
aitbc --api-key "$CLIENT_JWT" market list --service-type ollama
aitbc --api-key "$CLIENT_JWT" gpu list-gpus
```

A shop publishes a GPU software offer with:

```bash
aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0
```

This first writes a `GPU_MARKETPLACE` transaction to the hub blockchain via `POST /rpc/transactions/marketplace`, then registers the offer in the local marketplace service (`http://localhost:8102/v1/marketplace/offer`) so it is discoverable from the hub.

### 3. Submit a paid job

```bash
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "What is machine learning?" \
  --model llama3.2:3b \
  --payment 1.0 \
  --wallet customer-wallet \
  --buyer-address <customer-ait1-or-aitbc1> \
  --provider-address <provider-address>
```

The CLI builds a `JobCreate` payload and posts it to `POST /v1/jobs` on the coordinator. The current payload shape is:

```json
{
  "payload": {
    "type": "inference",
    "prompt": "What is machine learning?",
    "model": "llama3.2:3b"
  },
  "constraints": {},
  "ttl_seconds": 900,
  "payment_amount": "1.0",
  "payment_currency": "AITBC",
  "buyer_address": "<customer-address>",
  "provider_address": "<provider-address>"
}
```

The coordinator creates a `JobPayment` record and calls `POST /rpc/escrow/create` on the blockchain node (port 8202) to escrow the buyer's funds. The job is then queued for a miner.

Use `aitbc ai submit --wait --timeout <seconds> --poll-interval <seconds>` to block, poll until the job is `released`, and print the escrow transaction hash.

### 4. Match and execute

The coordinator exposes `POST /v1/miners/poll` on port 8203. The shop's `aitbc-miner` service polls this endpoint and, when a queued job matches its advertised capabilities, receives an `AssignedJob`:

```json
{
  "job_id": "<job-id>",
  "payload": { "type": "inference", "prompt": "...", "model": "llama3.2:3b" },
  "constraints": {}
}
```

The miner then:

1. Updates the job state to `RUNNING` via the coordinator.
2. Calls the local GPU service (`http://localhost:8101`) to select a device.
3. Runs inference against the local Ollama server (`http://localhost:11434/api/generate`).
4. Returns the result, metrics, and a receipt to the coordinator via `POST /v1/miners/{job_id}/result`.

The dispatch model is pull-based with reputation preference: matching online miners are polled, and `min_reputation` plus higher reputation scores are used to select the assignment. (P1.1 shipped.)

### 5. Escrow release and settlement

When the coordinator receives the miner's result:

1. It verifies the result and computes a receipt.
2. It calls `POST /rpc/escrow/{job_id}/release` on the blockchain node.
3. The blockchain node builds and signs an `ESCROW_RELEASE` transaction and submits it to `POST /rpc/transactions/marketplace`.
4. The transaction is included in a block, transferring compute-seconds from the escrow to the provider.

The release is signed by the dedicated settlement key (`ESCROW_RELEASE_PRIVATE_KEY` / `ESCROW_RELEASE_ADDRESS` in `/etc/aitbc/blockchain-secrets.env`); genesis is only a logged fallback and a key/address mismatch is refused before the escrow is touched. A 1.0 AIT job currently pays approximately 0.975 AIT to the provider after the network fee.

### 6. Inspect results

```bash
aitbc --api-key "$CLIENT_JWT" ai status <job_id>
aitbc --api-key "$CLIENT_JWT" ai results <job_id>
aitbc wallet transactions <provider-wallet>
aitbc explorer chain-head
```

A completed, released job shows `state: COMPLETED` and `payment_status: released`; the payment view (`GET /v1/jobs/{job_id}/payment`) contains the `ESCROW_RELEASE` `transaction_hash`.

## Components and ports

| Component | Port | CLI group | Responsibility |
|-----------|------|-----------|----------------|
| aitbc CLI | — | — | User interface, credential store, job formatting |
| aitbc auth | — | `aitbc auth login` | Wallet-signed JWT generation for coordinator access |
| Blockchain node RPC | 8202 | `aitbc chain`, `aitbc explorer`, `aitbc transactions` | Blocks, accounts, transactions, `/escrow/*`, `/transactions/marketplace` |
| Coordinator API | 8203 | `aitbc ai`, `aitbc auth` (JWT via `--api-key` only) | Job submission, assignment, result collection, payment records |
| Agent-coordinator | 8107 | `aitbc agent-comm`, `aitbc agent` | Agent messaging and orchestration (not the AI job miner) |
| Wallet daemon | 8108 | `aitbc wallet`, `aitbc account` | Wallet operations and balance queries |
| GPU service | 8101 | `aitbc gpu` | Local GPU discovery and resource management |
| Marketplace | 8102 | `aitbc market`, `aitbc marketplace` | `market` = GPU/software offers; `marketplace` = chain listings |
| Exchange | 8106 | `aitbc exchange-island` | Simple on-island exchange |
| Pool hub | 8210 | `aitbc pool-hub` | Miner capacity, SLA, billing metrics |
| Ollama | 11434 | — | AI model inference |

## Trust boundaries and known gaps

- **Authentication:** `Authorization: Bearer <jwt>` is the working header. The `X-Api-Key` legacy header is still accepted by some services but the CLI uses the bearer token.
- **Escrow:** The live path creates an on-chain escrow and releases it with a signed `ESCROW_RELEASE`. The release signer is the dedicated `ESCROW_RELEASE_PRIVATE_KEY`; genesis is only a logged fallback. The bridge is not involved in AI job escrow.
- **Bridge:** Cross-chain bridge code exists but `bridge_multisig_enabled` and `bridge_require_merkle_proof` are `False` by default. See `docs/releases/STATUS.md` and P1.3 for the current trust model.
- **Consensus:** The live hub currently runs single-validator Proof-of-Authority. MultiValidatorPoA/PBFT is behind the `multi_validator_consensus_enabled` flag; see P1.4.
- **Dispatch:** Reputation data is exposed via `aitbc reputation` and used to satisfy `min_reputation` and prefer higher-reputation miners during dispatch. (P1.1 shipped.)

## Message flow timeline

```
0s:  Customer submits CLI command (or `aitbc ai submit --wait`)
1s:  CLI posts JobCreate to coordinator (8203)
2s:  Coordinator creates JobPayment and posts /rpc/escrow/create (8202)
3s:  Job queued in coordinator database
5s:  Shop miner polls /v1/miners/poll and receives assignment
6s:  Miner updates job to RUNNING
7s:  Miner calls GPU service (8101) and Ollama (11434)
15s: Inference completes
16s: Miner posts result to coordinator
17s: Coordinator posts /rpc/escrow/{job_id}/release (8202)
18s: Blockchain includes ESCROW_RELEASE transaction
30s: Customer polls `aitbc ai status` and sees `COMPLETED + released`, or `aitbc ai submit --wait` exits with the escrow transaction hash
```

## Error handling paths

1. **Invalid prompt or missing wallet**
   - Coordinator returns 400/422.
   - CLI displays the validation error.

2. **Miner unavailable**
   - Job stays `QUEUED` until `ttl_seconds` expires, then `EXPIRED`.
   - Payment remains escrowed and can be refunded.

3. **Ollama error**
   - Miner posts failure to `POST /v1/miners/{job_id}/fail`.
   - Coordinator marks the job `FAILED` and does not release escrow.

4. **Network error**
   - CLI retries with exponential backoff and finally aborts.
   - Customer can re-run `aitbc ai status` once connectivity returns.

5. **Escrow release fails**
   - If the settlement key, genesis key, or blockchain node is unavailable, the job may show `COMPLETED` but `payment_status: escrowed`.
   - The operator must investigate the blockchain node logs; the payment is not lost while it remains escrowed.

## Monitoring

- Coordinator logs: `journalctl -u aitbc-coordinator-api`
- Miner logs: `journalctl -u aitbc-miner`
- Blockchain logs: `journalctl -u aitbc-blockchain-node`
- Pool hub metrics: `journalctl -u aitbc-pool-hub`
- Prometheus metrics, where exposed, are on each service's `/metrics` path (e.g., `http://localhost:8203/metrics` for the coordinator).

## See also

- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) for the current gap analysis and the P1 wish list
- [Scenario 34: Hub↔Customer Node End-to-End](../scenarios/34_hub_customer_node_e2e.md) for the live two-node play
