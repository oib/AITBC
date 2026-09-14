# Scenario 54: Paid agent-to-agent task delegation

## Goal

A buyer agent hires a provider agent for a paid task without going through the
marketplace job flow: negotiation travels over `agent-msg` envelopes, payment
locks on-chain through the same `/rpc/escrow/*` routes the marketplace uses,
and the provider executes against its local services.

Loop:

```text
buyer agent ── TaskRequest ──▶ provider agent
            ◀─ TaskQuote/TaskReject ──
buyer      ── TaskAccept ──▶
            (escrow already locked on-chain at submit)
provider   ── executes locally (whisper/ffmpeg/ollama/ipfs)
           ── TaskResult {result_ref: CID} ──▶
           ── POST /v1/tasks/{id}/complete → ESCROW_RELEASE
           ── TaskPaid {tx_hash} ──▶
```

The buyer locks `max_price`; the provider bills its quoted price; the chain
refunds the unbilled remainder to the buyer automatically. If the provider
never answers, the coordinator's `escrow_expiry_sweeper` refunds the lock
after `timeout_seconds`.

## Preconditions

- Hub: `aitbc-agent-coordinator` running with `TASK_PAYMENT_ESCROW_ENABLED=true`
  and `BLOCKCHAIN_RPC_API_KEY` set (env: `/etc/aitbc/aitbc-agent-coordinator.env`
  + `blockchain-secrets.env`). Nginx exposes `/api/v1/agent/messages/` and
  `/v1/` to the coordinator.
- Provider node (`<node2>`): `aitbc-miner` running with `AGENT_EXECUTOR_ENABLED=true`
  (`/etc/aitbc/aitbc-miner.env`), `MINER_ID`/`MINER_WALLET_ADDRESS` set, and the
  local services healthy (whisper :8110, ffmpeg :8230, ollama :11434, island
  IPFS :5002).
- Buyer node: `aitbc` CLI, a funded non-node-wallet wallet, and a reachable
  island IPFS daemon (`aitbc-island-ipfs`, API :5002) for payload upload and
  result download.

## Live validation (2026-09-13)

Run `<replica-node>` (buyer) → `<node2>` (provider `aitbc-miner-1`), whisper, tone WAV:

- Payload `QmT2mAeBmYXtkdm5hZapZNhkhQJd4SNusJW6bun9L18ZpJ` on buyer daemon.
- Escrow `a5888284` locked on-chain, `lock_tx 0xc367b881…` (job
  `atask_20260913215708_e29a183e`, contract `c4dbb1d83b74627c`).
- Provider quoted `0.02 AIT` (`offer whisper-base`), executed in ~52 s.
- Result CID `QmWGEpHDhksjk8SZoXnwzm5gzDVYAwUNDdYXHnPDzUzmwV` fetched
  byte-identical; sha256 matched the `TaskResult` message.
- Settlement: released `0.0195` AIT to provider (`0x62da8d19…`), remainder
  `0.03` AIT auto-refunded to buyer (`0x0c115986…`).
- Timeout path: `ghost-provider` (registered, no executor) hired with
  `--timeout 120` → sweeper refunded on-chain (`refund_tx 0xaa79867f…`).

## Steps

### 1. Provider registers and listens

The miner loop on the provider registers its agent on the coordinator each
sweep (30 s) — visible via discovery:

```bash
curl -s -X POST https://hub.aitbc.bubuit.net/v1/agents/discover \
  -H 'Content-Type: application/json' -d '{}'
```

Expect an agent `aitbc-miner-1` with `services: [whisper, ffmpeg, ollama, ipfs]`
and `metadata.wallet` = the provider wallet.

### 2. Buyer hires

```bash
aitbc agent-task hire \
  --to-agent aitbc-miner-1 \
  --service-type whisper \
  --payload ./audio.wav \
  --max-price 0.05 \
  --wallet <buyer-wallet> \
  --wait
```

The command uploads the payload to the buyer's island daemon, reads the
settlement wallet from `GET /v1/tasks/escrow-config` (the coordinator's own
settlement node — correct on any node, no `HUB_PROPOSER_ID` needed), signs the
`ESCROW_LOCK` with the buyer wallet, submits `POST /v1/tasks/submit`, sends the
`TaskRequest`, waits for the quote, auto-accepts when `quote <= max_price`,
and prints the result CID + payment tx.

### 3. Inspect status / fetch result

```bash
aitbc agent-task status --task-id <task_id>
aitbc agent-task result --task-id <task_id> --out result.json
```

`status` shows the escrow row (status, lock/release/refund tx hashes,
contract id) plus the negotiation messages found in the buyer inbox.
`result` pulls `result_ref` from the buyer's local island daemon and verifies
`result_hash` (sha256).

### 4. Timeout / refund path

Point `--to-agent` at an agent with no executor (or stop the miner). The
escrow locks, no quote arrives, and after `--timeout` seconds the
coordinator's sweeper refunds the lock on-chain:

```bash
aitbc agent-task status --task-id <task_id>
# escrow_status: refunded, tx_hash_refund: 0x…
```

## Notes / limits

- Agent messaging is unauthenticated at the coordinator (`/v1/*` and
  `/api/v1/agent/messages/*` are public through the hub proxy, same trust
  level as the rest of the coordinator REST surface). The escrow check is
  what gates execution — a `TaskRequest` without a real locked escrow that
  pays the provider is rejected.
- `escrow_status` on `GET /v1/tasks/{task_id}/escrow` reflects the
  coordinator's bookkeeping entry; `/rpc/escrow/{job_id}` on the chain is
  the settlement record.
- Buyers on nodes without an island IPFS daemon cannot upload payloads or
  fetch results (`<node0>` currently lacks the daemon — deploy
  `aitbc-island-ipfs` there before it can be a buyer).
- The coordinator's `PaymentEscrow` store is in-memory: a coordinator
  restart loses bookkeeping entries. On-chain escrow records are unaffected;
  `GET /v1/tasks/{id}/escrow` will 404 for tasks created before a restart.
