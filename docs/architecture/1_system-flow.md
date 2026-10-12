# AITBC System Flow: From CLI Prompt to On-Chain Settlement

> **Authoritative port configuration** is in [Service Ports Reference](../reference/SERVICE_PORTS.md). This document describes the current CLI-driven flow on the live hub/shop island as verified on 2026-10-13 (fleet commit `d09240101`). Port and unit names were checked against `systemctl cat` and `ss -tlnp` on hub and node2.

Chain facts (verified 2026-10-13): chain id `ait-hub.aitbc.bubuit.net`; 1 AIT = 36,000,000 compute-units; state-transition **v14 is armed for height 46,100** (not yet reached — blocks below 46,100 carry `state_transition_version 12` and no `aux_state_root`).

The canonical customer path is:

```text
aitbc wallet create --name <name> → aitbc auth login --wallet <name>
    → aitbc ai submit --wallet <name>            (signs ESCROW_LOCK locally)
    → coordinator 127.0.0.1:8203 (JWT) → POST /rpc/escrow/create (chain rpc 8202)
    → ESCROW_LOCK sealed → shop miner polls /v1/miners/poll
    → GPU service 8101 → Ollama 11434 / Whisper 8110 / ffmpeg binary
    → POST /v1/miners/{job_id}/result → coordinator
    → POST /rpc/escrow/{job_id}/release → signed ESCROW_RELEASE
    → provider paid minus 2.5 % platform fee
```

## Overview

```
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
│ Customer │ → │  aitbc   │ → │ Coordinator  │ ↔ │ Blockchain   │ ← │  Shop    │ → │  Ollama  │
│  wallet  │   │   CLI    │   │   8203       │   │  rpc 8202    │   │  miner   │   │  11434   │
└──────────┘   └──────────┘   └──────────────┘   └──────────────┘   └──────────┘   └──────────┘
                                                                  ↑
                                                           GPU service 8101
                                                           whisper     8110
                                                           ffmpeg      (binary)
                                                           market      8102
                                                           pool-hub    8210
```

Public customer access to hub services is through nginx (`https://hub.aitbc.bubuit.net/...`) because the coordinator, exchange, and wallet daemon bind `127.0.0.1`. The blockchain RPC binds `0.0.0.0:8202` (peer sync needs it; sensitive routes are API-key gated). The shop miner daemon runs on the follower node (node2) and polls the hub coordinator; it is not a public service.

## Step-by-step flow

### 1. Acquire AIT and authenticate

```bash
aitbc wallet create --name customer-wallet          # --name required; interactive password
aitbc wallet --wallet-name genesis send --to-address <customer-address> --amount <amount>
aitbc auth login --wallet customer-wallet            # wallet-signed JWT, stored for later commands
```

`aitbc auth login` signs with the local wallet and stores the JWT; `--api-key` / `AITBC_API_KEY` remain accepted fallbacks for a pre-made client JWT:

```bash
python3 -c "from aitbc.auth import create_access_token; print(create_access_token('customer-node-user', 'client', {'wallet_address': '<customer-address>'}))"
```

### 2. Discover compute

```bash
aitbc --api-key "$CLIENT_JWT" market list --service-type ollama
aitbc --api-key "$CLIENT_JWT" gpu list-gpus
```

A shop publishes a GPU software offer with:

```bash
aitbc market offer --service-type ollama --model-or-variant llama3.2:3b --price 0.001 --unit per_1k_tokens --gpu-device 0
```

The offer writes a `GPU_MARKET` transaction via `POST /rpc/transactions/market` and registers in the local market service (`http://localhost:8102/v1/market/offer`). The `aitbc-miner` service additionally publishes its own default offers at start-up for the service types it can execute (`ollama`, `whisper`, `ffmpeg`, `ipfs`) when it detects the matching worker is present.

### 3. Submit a paid job — the buyer signs the lock

```bash
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "What is machine learning?" \
  --model llama3.2:3b \
  --payment 1.0 \
  --wallet customer-wallet \
  --buyer-address <customer-0x-address> \
  --provider-address <provider-address>
```

`--wallet` is **required**: the CLI builds an `ESCROW_LOCK` transaction locally and signs it with the customer wallet (`create_signed_escrow_lock`), never sending the key. The `JobCreate` body posted to `POST /v1/jobs` is:

```json
{
  "payload": { "type": "inference", "prompt": "What is machine learning?", "model": "llama3.2:3b" },
  "constraints": {},
  "ttl_seconds": 900,
  "payment_amount": "1.0",
  "payment_currency": "AITBC",
  "buyer_address": "<customer-address>",
  "provider_address": "<provider-address>",
  "buyer_lock_signature": "<signed ESCROW_LOCK>",
  "buyer_lock_nonce": <n>,
  "buyer_lock_fee": <units>
}
```

Optional fields `offer_id` / `offer_quantity` attach the job to a published offer. The coordinator creates a `JobPayment` record and posts the signed lock to `POST /rpc/escrow/create` on the blockchain RPC (8202), which submits the `ESCROW_LOCK` to `POST /rpc/transactions/market`. A job is only dispatchable once the payment row reaches `payment_status: escrowed` — an escrow that never locked is never handed to a miner.

Use `aitbc ai submit --wait --timeout <seconds> --poll-interval <seconds>` to block until release and print the settlement transaction hash. `ai submit` also accepts `--offer-id`, `--offer-quantity`, `--acceptance-window`, `--min-reputation`, `--zk-proof-required`, and `--tee-attestation-required`.

Result-verification gates, marked per DESIGN_CYCLE §3/§4 — **partial, not fully live**: `--zk-proof-required` (the `receipt_model` circuit proves a *committed deterministic model* ran on committed input; it does not prove open-ended LLM correctness) and `--tee-attestation-required` (registered-enclave allowlist + identity pinning shipped, but no live miner has registered a stable enclave key — validation exercises the simulated/self-consistency paths).

### 4. Match and execute

The coordinator exposes `POST /v1/miners/poll` (8203). The shop's `aitbc-miner` service polls it with `{"max_wait_seconds": 5}`; it also heartbeats `POST /v1/miners/heartbeat` with live GPU stats and caps concurrent jobs locally. On a match it receives an `AssignedJob`:

```json
{
  "job_id": "<job-id>",
  "payload": { "type": "inference", "prompt": "...", "model": "llama3.2:3b" },
  "constraints": {}
}
```

The miner then:

1. Selects a device via the local GPU service (`http://localhost:8101`).
2. Dispatches by `service_type`:
   - `ollama` → `POST http://localhost:11434/api/generate`;
   - `whisper` → `POST $WHISPER_SERVICE_URL/transcribe` (default `http://127.0.0.1:8110`);
   - `ffmpeg` → the `ffmpeg` binary via subprocess (the `aitbc-ffmpeg` HTTP service on 8230 exists for direct API use; the miner itself shells out);
   - `ipfs` → the local IPFS path.
3. Returns the result, metrics, and a receipt via `POST /v1/miners/{job_id}/result`, or reports failure via `POST /v1/miners/{job_id}/fail`.

The dispatch model is pull-based with reputation preference: matching online miners are ranked by reputation, and `--min-reputation` on the job filters candidates.

### 5. Escrow release and settlement

When the coordinator accepts the miner's result:

1. It verifies the result and computes a receipt.
2. It calls `POST /rpc/escrow/{job_id}/release` on the blockchain RPC.
3. The node's `EscrowManager.release_payment` pays the escrow's recorded `agent_address` — the provider address fixed at lock time; the release call cannot redirect it — billing the job amount less `fee_rate` (default `0.025`, so 1.0 AIT pays 0.975 AIT to the provider).
4. The node builds, signs, and submits an `ESCROW_RELEASE` transaction to `POST /rpc/transactions/market`; it seals in a block.

The release is signed by the dedicated settlement key (`ESCROW_RELEASE_PRIVATE_KEY` / `ESCROW_RELEASE_ADDRESS` in `/etc/aitbc/blockchain-secrets.env`); genesis is only a logged fallback, and a key/address mismatch is refused before the escrow is touched.

### 6. Inspect results

```bash
aitbc --api-key "$CLIENT_JWT" ai status <job_id>
aitbc --api-key "$CLIENT_JWT" ai results <job_id>
aitbc wallet transactions <provider-wallet>
aitbc explorer chain-head
```

A completed, released job shows `state: COMPLETED` and `payment_status: released` (coordinator `JobState`: `QUEUED → RUNNING → COMPLETED|FAILED|CANCELED|EXPIRED`). The payment view `GET /v1/jobs/{job_id}/payment` contains the `ESCROW_RELEASE` `transaction_hash`. Note the market service's own job feed (`GET /v1/market/jobs`) reports settlement in a different vocabulary — `RELEASED`/`REFUNDED` as states — where the coordinator view says `COMPLETED`/`released`.

## Components and ports

Verified binds on hub (proposer) and node2 (shop follower), 2026-10-13:

| Component | Port | Unit / process | Responsibility |
|-----------|------|----------------|----------------|
| aitbc CLI | — | `aitbc` | User interface, credential store, ESCROW_LOCK signing |
| Coordinator API | 8203 (127.0.0.1) | `aitbc-coordinator-api` (uvicorn) | `POST /v1/jobs`, `/v1/miners/*`, payment records |
| Blockchain RPC | 8202 (0.0.0.0) | `aitbc-blockchain-rpc` | `/rpc/escrow/*`, `/rpc/transactions/market`, blocks, accounts |
| Blockchain node | p2p | `aitbc-blockchain-node` | Consensus, state transition, mempool |
| aitbc-miner | — (polls 8203) | `aitbc-miner` on node2 | Poll/execute/result; `MINER_ID=aitbc-miner-1` |
| GPU service | 8101 (127.0.0.1) | `aitbc-gpu` on node2 | Device discovery and selection |
| Market | 8102 (127.0.0.1) | `aitbc-market` | Offers, market job feed, escrow metadata |
| Wallet daemon | 8108 (127.0.0.1) | `aitbc-wallet` | Wallet ops for the CLI path |
| Agent-coordinator | 8107 (127.0.0.1) | `aitbc-agent-coordinator` | Agent messaging/orchestration (not the AI miner) |
| Exchange | 8106 (0.0.0.0) | `aitbc-exchange` | Simple on-island exchange |
| Trading / governance | 8104 / 8105 (127.0.0.1) | `aitbc-trading`, `aitbc-governance` | Platform services outside the job path |
| Pool hub | 8210 (127.0.0.1) | `aitbc-pool-hub` | Miner capacity, SLA, billing metrics |
| Ollama | 11434 (127.0.0.1) | `ollama` on node2 | AI model inference |
| Whisper | 8110 (127.0.0.1) | `aitbc-whisper` on node2 | Transcription (`WHISPER_SERVICE_URL`) |
| FFmpeg | 8230 | `aitbc-ffmpeg` on node2 | Media service; the miner uses the `ffmpeg` binary directly |
| Edge agent | 8111 | `aitbc-edge` on node2 | Edge runtime (`APP_PORT=8111`) |

## Trust boundaries and known gaps

- **Authentication:** `Authorization: Bearer <jwt>` is the working header. `X-Api-Key` is still accepted by some services (the chain RPC's keyed routes require it).
- **Escrow:** the buyer locks funds with a locally signed `ESCROW_LOCK`; the coordinator cannot lock funds itself. Release pays only the escrow's recorded `agent_address`. The release signer is `ESCROW_RELEASE_PRIVATE_KEY`; a key/address mismatch is refused.
- **Bridge:** unrelated to the AI-job escrow path. On the live hub `BRIDGE_MULTISIG_ENABLED=true` with a 2-of-2 threshold (env-verified 2026-10-13); see `docs/releases/STATUS.md` for the trust model.
- **Consensus:** MultiValidatorPoA (`MULTI_VALIDATOR_CONSENSUS_ENABLED=true`, `MIN_ATTESTATIONS=2`) with a 4-validator active set; PBFT is implemented but disabled (`PBFT_CONSENSUS_ENABLED=false`). Measured block interval ~65–70 s.
- **Dispatch:** reputation data ranks miners and `min_reputation` filters them (P1.1 shipped).

## Message flow timeline

Block sealing is the dominant latency (~65–70 s per block on the measured fleet): the `ESCROW_LOCK` must seal before the job is dispatchable, and `ESCROW_RELEASE` seals after the coordinator posts the release.

```
0s:    CLI signs ESCROW_LOCK locally; posts JobCreate to coordinator (8203)
1s:    Coordinator creates JobPayment, posts /rpc/escrow/create (8202)
~68s:  ESCROW_LOCK sealed → payment_status=escrowed → job dispatchable
+:     Miner poll returns an AssignedJob; state RUNNING
+:     Inference (Ollama/Whisper/FFmpeg); result posted to /v1/miners/{id}/result
+:     Coordinator posts /rpc/escrow/{job_id}/release (8202)
+~68s: ESCROW_RELEASE sealed; provider paid (amount − 2.5% fee)
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
   - A lost `/rpc/escrow/create` response is recovered by re-querying the escrow before retrying (the lock may already have submitted).

5. **Escrow release fails**
   - If the settlement key or blockchain node is unavailable, the job may show `COMPLETED` but `payment_status: escrowed`.
   - The operator investigates the blockchain node logs; the payment is not lost while it remains escrowed. A sweeper retries releases that completed without settling on-chain.

## Monitoring

- Coordinator logs: `journalctl -u aitbc-coordinator-api`
- Miner logs: `journalctl -u aitbc-miner` (node2)
- Blockchain logs: `journalctl -u aitbc-blockchain-node`, `journalctl -u aitbc-blockchain-rpc`
- Pool hub metrics: `journalctl -u aitbc-pool-hub`
- Prometheus metrics, where exposed, are on each service's `/metrics` path (e.g., the coordinator API at `http://localhost:8203/metrics`); the fleet Prometheus is on hub port 9090.

## See also

- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) for the current gap analysis and the P1 wish list
- [Scenario 34: Hub↔Customer Node End-to-End](../scenarios/34_hub_customer_node_e2e.md) for the live two-node play
