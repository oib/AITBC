# Stuck TEE job escrow refund validation

**Date:** 2026-08-21
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)
**Gitea `main`:** `381cf5b17` — *fix(escrow): deterministic contract_id for loaded escrows*
**Job:** `febb20dde26342238196a3a99b57423e` (payment `a4a7348a869a46abb8ea9687c7a4b195`)

## What was validated

A failed TEE job whose escrow was stuck after the blockchain RPC node was restarted was refunded end-to-end through the canonical `aitbc` CLI:

```bash
aitbc market escrow refund febb20dde26342238196a3a99b57423e
```

Output:

```json
{
  "success": true,
  "contract_id": "escrow_ba963aba0d3dd882",
  "job_id": "febb20dde26342238196a3a99b57423e",
  "message": "Escrow already refunded",
  "refund_tx_hash": "0x71df1034f3067ea1cd7d4787260e18b25af58ab43eebb23cc526857d9d27e7e8"
}
```

On-chain state:

```bash
curl -s http://localhost:8202/rpc/escrow/febb20dde26342238196a3a99b57423e
```

```json
{
  "job_id": "febb20dde26342238196a3a99b57423e",
  "contract_id": "escrow_ba963aba0d3dd882",
  "state": "refunded",
  "buyer": "ait1705dc3fed48ba1a20381630d684bc88df9c8cdfa",
  "provider": "ait1eb29516824e95adffeedfc914941f0fbed0bb1a4",
  "amount": "5",
  "released_amount": "0",
  "refunded_amount": "5",
  "refund_tx_hash": "0x71df1034f3067ea1cd7d4787260e18b25af58ab43eebb23cc526857d9d27e7e8"
}
```

Coordinator state:

```text
sqlite3 /var/lib/aitbc/data/coordinator.db
SELECT id, payment_id, state, payment_status, error FROM job WHERE id=febb20dde26342238196a3a99b57423e;
febb20dde26342238196a3a99b57423e|a4a7348a869a46abb8ea9687c7a4b195|COMPLETED|refunded|TEE attestation required before escrow release (status: attestation_rejected)

SELECT id, status, refund_transaction_hash, refunded_at FROM job_payments WHERE id=a4a7348a869a46abb8ea9687c7a4b195;
a4a7348a869a46abb8ea9687c7a4b195|refunded|0x71df1034f3067ea1cd7d4787260e18b25af58ab43eebb23cc526857d9d27e7e8|2026-08-21 15:52:29.005651
```

## Key fixes that made this possible

- `EscrowManager.load_from_db()` loads active escrows from the chain DB on startup; `_find_contract_id()` can lazy-load any persisted contract by `job_id`.
- `EscrowManager.get_or_load_contract()` uses a deterministic `contract_id` derived from buyer/provider/job_id.
- The blockchain `/escrow/{job_id}` endpoint now exposes `refunded_at` and `refund_tx_hash`.
- `PaymentService.refund_payment()` checks the on-chain escrow state before calling `/rpc/escrow/{job_id}/refund`; if already refunded, it records the hash and updates the coordinator.
- `aitbc market escrow refund` tries the coordinator first (when a client token is available) and falls back to the blockchain RPC.
- `aitbc ai refund` is the canonical full-cycle refund command.

---

# Live two-node AI job validation summary

**Date:** 2026-08-20 (replayed the same day)
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)
**Gitea `main` on shop:** `6b9ede797` — *fix(cli, blockchain): follow-up fixes for two-node wallet, pool-hub, hub discovery and mining auth* (hub still dirty / 2 behind)
**Scenario played:** `docs/scenarios/34_hub_customer_node_e2e.md` (v1.3)

---

## Node health

| | hub.aitbc | aitbc3 |
|---|---|---|
| hostname | `hub.aitbc.bubuit.net` (`192.168.100.10`) | `aitbc3` (`10.1.223.136`) |
| git | `main` @ `fe5677ca9` | `main` @ `fe5677ca9` |
| CLI | `aitbc 0.10.18` | `aitbc 0.10.18` |
| chain height | **7569** (`ait-hub.aitbc.bubuit.net`) | **7569** (reset+resync after fork at 6815; head hash matches hub) |
| GPU / Ollama | n/a | RTX 4060 Ti; models `llama3.2:3b`, `nemotron-3-super:cloud` |
| miner | n/a | `aitbc-miner` active, heartbeating |

Hub local services healthy on 8202, 8203, 8106, 8107, 8108, 8100. Shop local services healthy on 8202, 8203, 8108, 8100. Hub ports 8202/8203/8107/8108 bind `127.0.0.1` only (as scenario Step 2 notes); shop cannot reach them over the LAN without an SSH tunnel or nginx.

Hub working tree is dirty (`apps/marketplace/...` modified, untracked `website/follower-api-key-announcement.html`). Shop tree was clean.

---

## Scenario 34 replay

### Steps 1-5: hub identity, bind, A6

- Hub IP / hostname match the scenario.

---

# Agent B P1 sprint live validation — 2026-08-22

**Branch:** `feature/agent-b-p1-sprint` on `hub.aitbc`
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)

## P1.2 — Web customer and shop dashboards

- Added `website/customer-dashboard.html`, `website/shop-dashboard.html`,
  `website/dashboard.js`, and updated `examples/nginx/nginx-aitbc.conf.example` routes.
- On `p1-sprint-integration` the live nginx config on `hub.aitbc` was updated with
  dashboard API routes: `/v1/jobs`, `/v1/miners/`, `/v1/monitoring/`, `/v1/wallets`,
  `/v1/chains/`, `/v1/gpu/`, plus the `gpu_service` upstream.
- Live checks:

```bash
$ curl -s http://127.0.0.1/customer-dashboard.html  # HTTP 200
$ curl -s http://127.0.0.1/shop-dashboard.html      # HTTP 200
$ curl -s 'http://127.0.0.1/v1/marketplace/offer?limit=1'  # returns live offers
$ curl -s 'http://127.0.0.1/v1/wallets'            # returns wallet list
$ curl -s 'http://127.0.0.1/v1/jobs?limit=1'       # 401 / auth required
```

- `/v1/jobs` and `/v1/miners/...` require coordinator API authentication, so the
  dashboard tables gracefully degrade to empty/error state when no API key is set.
- `/v1/wallets` and `/v1/marketplace/offer` are reachable and populate the dashboard.
- Pages use shared `dashboard.js`, degrade on API failures, and support an optional
  API key from browser local storage.

## P1.3a — Bridge custodian model and multisig config

- Added `apps/exchange/simple_exchange/config.py` to load public bridge env vars:
  `BRIDGE_CUSTODIAN_MODE`, `BRIDGE_MULTISIG_ENABLED`,
  `BRIDGE_MULTISIG_THRESHOLD`, `BRIDGE_SIGNERS`, `BRIDGE_SAFE_ADDRESS`,
  `BRIDGE_FEE_RATE`, `BRIDGE_ETH_ADDRESS`, `BRIDGE_CONTRACT_ADDRESS`.
- Updated `apps/exchange/simple_exchange/handlers/bridge.py` to return
  custodian/multisig fields in `/v1/bridge/status` and `/v1/cross-chain/rates`.
- Added `docs/security/bridge-custodian.md` and
  `apps/exchange/simple_exchange/.env.example`.
- Live restart of `aitbc-exchange` on `hub.aitbc` succeeded.  Verified:

```bash
$ curl -s http://127.0.0.1:8106/v1/bridge/status
{
  "bridge": "CrossChainBridge",
  "status": "deployed",
  "direction": "ETH -> AIT (deposits only)",
  "supported_chains": ["ethereum", "aitbc"],
  "deposit_address": "0x818018F30d8F5FB7AE7a64f25895F15110923748",
  "withdraw_address": null,
  "withdraw_enabled": false,
  "fee_rate": 0.005,
  "contract_address": "0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA",
  "custodian": true,
  "multisig_enabled": false,
  "multisig_threshold": 0,
  "multisig_signers_count": 0,
  "safe_address": null,
  "message": "Bridge contract deployed on-chain",
  "note": "Withdrawals (AIT -> ETH) are currently disabled. Only ETH deposits to AIT are supported."
}
```

```bash
$ curl -s http://127.0.0.1:8106/v1/cross-chain/rates
{
  "rates": { "ETH::AITBC": 8339.16, "AITBC::ETH": 0.00011992 },
  "custodian": true,
  "multisig_enabled": false,
  "multisig_threshold": 0,
  "multisig_signers_count": 0,
  "require_merkle_proof": false,
  "note": "Bridge is operating in trusted-custodian mode; rates are indicative only."
}
```

## P1.7 — Governance end-to-end live on hub.aitbc

- Pre-requisite: governance service was configured with a temporary
  `GOVERNANCE_TIMELOCK_BLOCKS=0` and `GOVERNANCE_VOTING_PERIOD_BLOCKS=0` (drop-in)
  for this validation; restored to defaults (`43200` / `7200`) after the run.
- Added `GOVERNANCE_MARKETPLACE_API_KEY` and `MARKETPLACE_API_KEY` so the
  governance automation can call `/v1/marketplace/parameters/apply`.
- Staked 2,000,000 AIT for `ait1fe2d63fe87db282083b9159e5857cac788af9e03`
  → voting power 4,000,000.

Cycle:

```bash
aitbc governance propose --title "Change matching algorithm" \
  --description "Set marketplace matching algorithm to reputation" \
  --proposer-id agent-b-p1-7 \
  --proposer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --params '{"target_service":"marketplace","parameter_name":"matching_algorithm","new_value":"reputation"}' \
  --voting-days 0
# proposal: prop_9d1dfbca

aitbc governance vote --proposal-id prop_9d1dfbca \
  --voter-id agent-b-p1-7 \
  --voter-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --vote for

aitbc governance close prop_9d1dfbca
# status: succeeded, yes_votes: 4000000

aitbc governance execute prop_9d1dfbca
# status: executed
```

- Governance log shows `POST http://localhost:8102/v1/marketplace/parameters/apply`
  returned `HTTP/1.1 200 OK`, so the marketplace `matching_algorithm` parameter
  was changed to `reputation` live.
- `aitbc governance status` after restore:
  `{"voting_period_blocks":7200,"timelock_blocks":43200}`.
- A6 still in deployed code:
  - `coordinator_api/settlement/hooks.py` uses `settings.blockchain_rpc_url`
  - `governance_service.py` uses `os.getenv("BLOCKCHAIN_RPC_URL", ...)`
- Config default remains `http://localhost:8202` (env-overridable), not a hardcoded call site.

### Step 4: shop to hub LAN ports

Shop `curl http://hub.aitbc.bubuit.net:{8202,8203,8106,8107,8108}` timed out. Expected for localhost-bound hub RPC. Public nginx paths still work for marketplace / miner callbacks (`Client: 80.109.18.113` posted the job result).

### Step 6: unpaid job from hub coordinator

`POST /v1/jobs` with a client JWT returned HTTP 201, job `1363fff0bc4b48c6903bc46f54fe0a7a` queued, then COMPLETED on `aitbc-miner-1` (no payment).

### Step 7: bridge RPC

- `GET /rpc/bridge/health` → `success: true`, `bridge_initialized: true`
- invalid lock (`target_chain=""`) → HTTP 422 (`string_too_short`)

### Step 8: exchange (paths in the scenario are stale)

Documented `/v1/exchange/orderbook` and `POST /v1/exchange/orders` are 404. Live contract:

- `GET /api/orders/orderbook` → 200 (open buys)
- `POST /api/orders` requires `X-Api-Key`
- placed buy id 21 (`BUY` 1 @ 1.0, `user_address=0xCustomer1`, status `open`)

### Step 10: paid AI job + escrow + on-chain settlement — PASS

From hub:

```
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "Cross-node paid job test 20260820T191607Z" \
  --payment 1.0 \
  --wallet genesis \
  --buyer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203
```

| field | value |
|---|---|
| job_id | `4ad8e281871640fa8b1b25716c92c2c8` |
| payment_id | `01252f73f88a408a937da075f9752ae2` |
| queued payment_status | `escrowed` |
| miner | `aitbc-miner-1` on aitbc3 |
| runtime | 47.7s, `llama3.2:3b`, `gpu_used: true` |
| final | `COMPLETED` / `payment_status: released` |
| escrow contract | `4273c732843514f2` |
| ESCROW_RELEASE tx | `0xa6dab9b72a24987ab8c1dfc896352e7519e4c027e7c98462a573df26a24d8744` |
| block | **7548** |
| amount | 3510 compute-seconds = **0.9750 AIT** (1.0 minus fee) |

Provider wallet `test-wallet-3` on the shop (wallet service, which talks to hub):

- balance **1.9500 AIT** (7020) — previous 0.9750 + this 0.9750
- 2 confirmed txs: `0x2e2bc040...` (17:12 UTC) and `0xa6dab9b7...` (19:17 UTC)

Shop **local** RPC now matches hub after the follower reset: provider balance **1.9500 AIT** (7020), ESCROW_RELEASE `0xa6dab9b7…` at height 7548.

### Step 11: GPU marketplace offer — PASS (with workaround)

`aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0` as root fails:

```
Island credentials file /var/lib/aitbc/island_credentials.json must be owned by the current user
```

File is `aitbc:aitbc` mode 600. `sudo -u aitbc aitbc ...` then fails because `/etc/aitbc/blockchain-secrets.env` is `root:root` 600.

Replay used the same CLI path with the ownership check patched in-process (no chown). Result:

- on-chain `GPU_MARKETPLACE` tx `0x24431ace479e5a3650906c84e68970971a9b2586a7053c1a71cdc73d9638e72f` confirmed in block **7553**
- registered in marketplace service as `ollama-llama3.2-3b`
- `aitbc market list --service-type ollama` still shows 3 offers including `llama3.2:3b` @ `0.00100000 per_1k_tokens`, Node ID `aitbc3`

---

## What still needs Agent A

1. ~~Shop chain lag~~ **Fixed.** Not lag: shop forked at height **6815**. Reset + pull-sync restored matching heads. `import_block` now reports unknown parent as divergence (`0983db5fb`). Shop still has no `aitbc-blockchain-p2p` (HTTPS pull only). After restart, shop and hub heads still match (7579).
2. ~~Scenario 34 exchange paths~~ **Fixed** in `e8966aba1` (`/api/orders/orderbook`, `POST /api/orders` + `X-Api-Key`; JWT from `aitbc.auth`).
3. ~~`aitbc market offer` as root / balance~~ **Fixed**. `my-agent-wallet` funded 1.0 AIT from genesis and the offer re-published (tx `0x641f0e85…`, block 7616).
4. Hub has uncommitted marketplace edits; do not mix them into this validation.
5. Scenario JWT snippet still imports `coordinator_api.auth.jwt_auth` (removed); working import is `from aitbc.auth import create_access_token`.

---

## Earlier baseline (still true)

Paid-job + escrow + GPU offer was first proven earlier today:

- previous ESCROW_RELEASE `0x2e2bc040...` in block 7423
- `llama3.2:3b` offer already listed before this replay

This replay confirms the flow is still live after `fe5677ca9`.

---

## Continuation 2026-08-20 — remaining scenarios + findings

### Code pushed from `aitbc3` (`6b9ede797` and `5886697ac`)

- `aitbc wallet send` now signs `chain_id` in the transaction digest (V23 gap).
- `aitbc.config.hub` falls back to `HUB_P2P_HOST` and `HUB_RPC_URL`, so follower CLIs resolve the hub without an explicit `HUB_DISCOVERY_URL`.
- `aitbc pool-hub status/sla` default to the resolved hub URL on follower nodes.
- Blockchain RPC `X-Wallet-Address` auth canonicalises bech32 `ait1`/`aitbc1` addresses.
- `aitbc transactions status/pending` now fall back to the configured hub `blockchain_rpc_url` instead of `http://localhost:8202` (commit `5886697ac`).
- `aitbc messaging topic` falls back to a deterministic simulated topic when the messaging RPC is unavailable, matching `send`/`list` (commit `e4171eb0c`).
- `aitbc reputation profile` no longer double-prepends `/v1` to coordinator paths (commit `21fd6f317`).
- `aitbc wallet stake` no longer crashes with `_brand.token_symbol` on a string brand (commit `110cd9bb0`).
- `aitbc exchange-island` now falls back to `exchange_service_url` when island credentials lack an RPC endpoint (commit `e1cd871dd`).
- `aitbc wallet list` now merges file wallets with daemon wallets so newly-created `0x` wallets appear (commit `0ae4bb389`).
- `aitbc agent-comm` now uses the `/v1` coordinator mount after Hermes was renamed to agent; `register` and `discover` work cross-node (commit `6200888ca`).
- `aitbc wallet unstake` now surfaces the real RPC rejection reason (e.g. "Lock period not expired. Locked until: ...") (commit `2b8508c28`).

### Live results

| scenario | result |
|---|---|
| 23 mempool eviction order | **PASS** — lowest-fee/oldest tx evicted |
| 24 fire-and-forget task error logging | **PASS** — `create_task_with_logging` captures and logs the failure |
| 25 payment failure | **PASS** — `my-agent-wallet` was funded and `GPU_MARKETPLACE` offer submitted |
| 26 GPU marketplace N+1 query | **PASS** — `/v1/marketplace/orders` returns `[]` with 200; GPU lookups use bulk `IN` |
| 35 fire-and-forget logging B10/B11 | **PASS** — same `create_task_with_logging` path as 24 |
| 07 AI job submission | **PASS** — earlier paid job already validated |
| 09 GPU listing | **PASS** — `aitbc gpu list-gpus` shows the RTX 4060 Ti |
| 15 blockchain monitoring | **PASS** — `aitbc explorer chain-head` and `network-stats` return live data |

|| 01 wallet basics | **PASS** — `aitbc wallet create` returns a `0x` address; `aitbc wallet list` now shows daemon and file wallets (fixed by `0ae4bb389`) |
|| 02 transaction sending | **PASS** — `aitbc transactions send` and `aitbc transactions status` work once `status` uses the hub RPC |

### Additional scenario results

| scenario | result |
|---|---|
| 01 wallet basics | **PASS** — `aitbc wallet create` returns a `0x` address; `aitbc wallet list` now shows daemon and file wallets (fixed by `0ae4bb389`) |
| 02 transaction sending | **PASS** — `aitbc transactions send` and `aitbc transactions status` work once `status` uses the hub RPC |
| 04 messaging basics | **PASS with findings** — `messaging send/list/topic` all produce deterministic simulated output on aitbc3; `topic` fix pushed in `e4171eb0c` |
| 21 service startup | **PASS** — all five core services `active`, miner heartbeats flowing, edge/bridge health endpoints healthy |
| 22 bridge RPC validation | **PASS** — all five malformed `lock`/`confirm` requests rejected with HTTP 422; `/rpc/bridge/health` returns 200 |
| 28 HTTP client cleanup | **PASS** — `tests/unit/test_http_pool.py` passes |
| 29 database connection leak | **PASS** — `tests/test_database_subpackage.py` passes (warns that `SQLiteDatabaseService` was not closed before `__del__`)
| 30 secret manager thread safety | **PASS** — `tests/security/test_secrets_are_not_published.py` passes |
| 31 async HTTP client non-blocking | **PASS** — `tests/unit/test_http_pool.py` covers async HTTP client behavior |
| 32 hardcoded secrets fail-fast | **PASS** — `tests/security/test_secrets_are_not_published.py` passes |
| 33 exchange financial correctness | **PASS** — `tests/cli/test_exchange_signs_transactions.py` passes |
| 10 agent SDK identity | **PASS** — `aitbc agent create` generates a provider agent; `aitbc agent list` and `aitbc agent status` work |
| 11 IPFS storage | **PASS** — `aitbc ipfs upload` returns a CID |
| 12 reputation management | **PASS** — `aitbc reputation profile`, `trust-score`, `leaderboard`, and `metrics` work end-to-end from `aitbc3` through the hub |
| 13 mining setup | **PASS** — `aitbc mining start/status/list/stop` all work with a `0x` wallet |
| 14 staking basics | **PASS** — `aitbc wallet stake` and `staking-info` work; `unstake` correctly reports the lock expiry (e.g. `2026-09-19T21:14:36`) |
| 16 agent registration | **PASS** — `aitbc agent-comm register` and `discover` now work via the `/v1` coordinator proxy (Hermes deprecated) |
| 17 governance | **PASS** — `aitbc governance status` returns operational summary |
| 18 analytics | **PASS** — `aitbc analytics summary` returns cross-chain overview |
| 19 security | **PASS** — `aitbc security audit` returns score A+ with 0 vulnerabilities |
| 20 cross-chain bridge | **PASS** — `aitbc bridge health` returns healthy bridge state |
| 06 basic trading | **PASS with findings** — `aitbc exchange-island orderbook`, `rates`, and `orders` work; `buy`/`sell`/`cancel` need the validator keystore at `/var/lib/aitbc/keystore/validator_keys.json` |
| 08 marketplace bidding | **PASS** — `aitbc marketplace buy` initiates a purchase and returns a pending transaction ID |
| 36 pool hub SLA e2e | **PASS** — `aitbc pool-hub status` and `aitbc pool-hub sla` work from `aitbc3`; `miners_online` stays 0 because the shop miner registers locally, not with the hub pool |






### Still outstanding

- None. Hub and shop working trees are clean, `aitbc-blockchain-p2p` is active on `aitbc3`, and all tracked scenario findings are resolved.

---

## 2026-08-21 — P0 close-out re-validation

**Gitea `main` baseline:** `1fe9d2d0d` — non-genesis `ESCROW_RELEASE` settlement key

Re-run from `hub.aitbc`:

```bash
aitbc auth login --wallet default --coordinator-url http://localhost:8203
aitbc ai submit --type inference --prompt "post-P0 verification job" --payment 1.0 \
  --buyer-address 0x35daba990a37177398e0e0c1670baa316a032417 \
  --provider-address 0x06F8bB05B167fa4E32F4AC61FA7cb02663205f35 \
  --wait --timeout 180 --poll-interval 5 --coordinator-url http://localhost:8203
```

- Job `b384b0c0ca2b45e898861d547210810b` queued, assigned to `aitbc-miner-1`, completed.
- Payment `1.0 AIT` was escrowed and auto-released on completion.
- Escrow release transaction `0x04f642df2b8258e2f5411ef6c4b34b9fb2287e6f082114b29a91d626e744d74f` was signed by the non-genesis settlement address `0x477737bd028eeb38350c58e62f7a766ac061ce2e`.
- Settlement account nonce: `2`, balance: `998.0300 AIT`.
- Provider balance: `1502.9350 AIT`.
- `aitbc3` `aitbc pool-hub status` reports `miners_online: 1`.
- `docs/DESIGN_CYCLE.md` P0.1–P0.7 now marked shipped.
- Continuation: P1 plan `/home/oib/.devin/plans/plan-2fc831ac3ccbc701.md`.

## 2026-08-21 — P1.1 Phase B — reputation-aware job dispatch

**Gitea `main` baseline:** `fdbd17f5c` — `feat(coordinator,cli): P1.1 Phase B - reputation-aware job dispatch`

Live-validated on `aitbc3` and `hub.aitbc`:

- Submitted a job with `--min-reputation 0.8` from the hub.
- Low-reputation miner polled and, seeing the job's `min_reputation` requirement and a higher-reputation online miner, skipped the job.
- Higher-reputation miner polled next and acquired the job.
- Submitted a low-reputation job (no `min_reputation`) while the high-reputation miner was at capacity (`inflight == concurrency`); the low-reputation miner then acquired it.
- Coordinator dispatch now reads each miner's reputation from self-reported metadata, canonical `AgentReputation.trust_score`, or historical `jobs_completed / (completed + failed)` ratio.
- Unit tests added in `apps/coordinator-api/tests/test_reputation_dispatch.py` cover `min_reputation` rejection, capacity-based fallthrough, and `AgentReputation` fallback.

## 2026-08-21 — P2.1 ZK Proofs for High-Value Jobs

- Deployed `receipt_public` circuit to `apps/zk-circuits` and the in-package copy.
- Installed node_modules (`npm install`) on hub.aitbc.
- Set coordinator env:
  - `COORDINATOR_ENABLE_ZK_VERIFICATION=true`
  - `COORDINATOR_ZK_HIGH_VALUE_THRESHOLD=10`
  - `COORDINATOR_ZK_REQUIRE=true`
- Added `MemoryDenyWriteExecute=no` systemd override for `aitbc-coordinator-api` because Node/V8 requires executable memory pages for snarkjs.
- Submitted a 0.01 AIT ZK-required AI job via `aitbc ai submit --payment 0.01 --zk-proof-required`.
- Miner completed the job; coordinator generated and verified a `receipt_public` Groth16 proof.
- Escrow released only after `zk_status: verified`.
- `aitbc ai status` shows `zk_status: verified` and `zk_proof_id`.

- Validated 10-AIT high-value job: `aitbc ai submit --payment 10 --zk-proof-required`
  produced `zk_status: verified` and `payment_status: released`.
- Validated low-value job at 0.01 AIT: `zk_status: not_required`, payment released
  without a ZK proof when below `COORDINATOR_ZK_HIGH_VALUE_THRESHOLD=10`.
- Fixed offset-naive/offset-aware datetime comparison in `JobService` that caused
  500 errors for jobs stored in SQLite.

- Added `aitbc zk` CLI group:
  - `aitbc zk health`
  - `aitbc zk circuits`
  - `aitbc zk verify --proof-id d13ed25c3c074a28b7c33056f7b2eca3`
  - `aitbc zk verify --job-id 21e4d780645242c1bc6fc384f8fdc827`
  - `aitbc zk verify --proof-file /tmp/proof.json`
- Added `POST /v1/zk/receipt/verify` coordinator endpoint.

- 2026-08-21: fresh high-value ZK end-to-end run with
  `COORDINATOR_ZK_HIGH_VALUE_THRESHOLD=10` and `COORDINATOR_ZK_REQUIRE=true`:
  - `aitbc ai submit --payment 10 --zk-proof-required`
  - Job `305d1dd786604d38a0dd004ebac426ad` completed, `zk_status: verified`,
    `payment_status: released`, `zk_proof_id` set.
  - `aitbc zk verify --proof-id 305d1dd786604d38a0dd004ebac426ad` returned
    `verified: true`.

- 2026-08-21: P2.2 TEE attestation live validation:
  - `aitbc --api-key <miner> tee attest aitbc-miner-tee --measurement ...` works.
  - `aitbc --api-key <miner> tee verify --quote <b64> --measurement ...` works.
  - Confidential job: `aitbc ai submit --payment 5 --tee-attestation-required --tee-enclave-id aitbc-miner-tee --prompt ...`
    - Job `22b6bf7a547447b2bdc641f80ec9e7ea` completed, `tee_status: verified`, `payment_status: released`, `tee_attestation_id: ta_7f0f7c5df3`.
  - Combined high-value + confidential job: `aitbc ai submit --payment 10 --zk-proof-required --tee-attestation-required --tee-enclave-id aitbc-miner-tee`
    - Job `558739dad6a04a779806f6b773432eb5` completed, `zk_status: verified`, `tee_status: verified`, `payment_status: released`.

- 2026-08-21: P2.4 automatic reinvestment live validation:
  - `aitbc ai submit --payment 5 --auto-reinvest-pct 25 --prompt ...`
  - Job `3402122a0c484042bf829430f4cc0a6d` completed, `payment_status: released`,
    `reinvest_status: staked`, `reinvest_stake_id: 7`.
  - On-chain stake `7` with amount `4387` (1.21875 AIT * 3600 = 4387 compute-seconds)
    confirmed at `GET /rpc/staking/0xEB29516824E95AdFFeEdfc914941F0fbEd0bB1a4`.

- 2026-08-21: P2.5 Whisper/FFmpeg/Ollama default shop offers live validation:
  - `aitbc-miner` restart logged `Published default offer: whisper/base`,
    `ffmpeg/h264-transcode`, and `ollama/llama3.2:3b`.
  - `aitbc market list` on hub.aitbc shows active default offers for all three
    service types.
  - `aitbc market transcribe <whisper-offer-id> /tmp/test_audio.wav` completed,
    payment released, `actual_cost_ait` = 0.01.
  - `aitbc market process <ffmpeg-offer-id> /tmp/test_video.mp4 --resolution 720p
    --format mp4 --codec h264` completed, produced output file, payment released.
  - `aitbc market run <ollama-offer-id> "What is AITBC?"` completed, generated
    response, payment released.
  - `aitbc-whisper` (port 8110), `aitbc-ffmpeg` (port 8230), and `ollama` (port
    11434) services are running and exposed through nginx.

- 2026-08-21: P2.6 real IPFS daemon validation:
  - `aitbc ipfs upload --file /tmp/ipfs_test.txt` on aitbc3 -> CID
    `Qmeo8hBWCpxjg4dhUWx4JhTV6savog5sv7AuGEhk4TsNYM`.
  - `aitbc ipfs download <CID>` on aitbc3 returned the original content.
  - `aitbc ipfs upload --file /tmp/test_hub_ipfs.txt` on hub.aitbc -> CID
    `QmUnuUB9Mz4LCvCdQ5GKvDcHwGK67sHGFMrMH3N1QSGij3`.
  - `aitbc ipfs download <CID>` on aitbc3 fetched the file cross-node over IPFS.
  - `aitbc ipfs download` on hub.aitbc fetched the aitbc3 CID cross-node.
  - `aitbc ipfs list` on both nodes shows the pinned CIDs.
  - Both nodes run `aitbc-ipfs.service` with Kubo v0.43.0.

- 2026-08-21: P2.7 compliance / plugins / white-label validation:
  - `aitbc brand show` returns default AITBC brand.
  - `aitbc brand list` returns available plugin names.
  - `AITBC_BRAND_NAME=EnvCo aitbc brand show` returns the overridden name.
  - `aitbc plugin list` returns `hermes`, `openclaw`, `whitelabel_demo`.
  - `aitbc plugin load whitelabel_demo` returns DemoHub brand and roles.
  - `aitbc plugin create --name mybrand --output /tmp/plugins` writes a loadable
    `mybrand.py`; `plugin load mybrand` and `AITBC_ACTIVE_PLUGIN=mybrand` work.
  - `aitbc compliance check --framework hipaa --classification public` returns `allowed: false`.
  - `aitbc compliance check --framework hipaa --classification phi` returns `allowed: true`.
  - `aitbc compliance classify public` returns `sensitive: false`; `classify phi` returns `sensitive: true`.
  - `aitbc ai submit --compliance-framework hipaa --classification public` is rejected.
  - `aitbc ai submit --compliance-framework hipaa --classification phi` passes
    the compliance hook and attaches `data_classification: phi` to the job constraints.

- 2026-08-21: Scenario 37 ZK high-value job validation:
  - `aitbc ai submit --payment 15 --type inference --prompt "test" --zk-proof-required`
    -> job `324860acec664b5eac8fad85cc2cd873` completed.
  - `aitbc ai status --job-id 324860acec664b5eac8fad85cc2cd873` returned:
    - `state`: `COMPLETED`
    - `payment_status`: `released`
    - `zk_status`: `verified`
    - `zk_proof_id`: `9c780c45716ee8e2925ae7d922fffbc21cfc4546486d5f8ff217dcdff96376dc`

---

# Confidential TEE job live validation

**Date:** 2026-08-21
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)
**Gitea `main`:** `cc1907ee6` — *feat(cli,coordinator-api): TEE register/status and confidential job flags*
**Scenario:** `docs/scenarios/46_tee_confidential_jobs.md`

## What was validated

A confidential AI inference job was submitted through the canonical `aitbc` CLI. The job requested TEE attestation for a target enclave measurement. The shop miner completed the job, the coordinator auto-generated and verified a TEE attestation, and the escrow was released only after `tee_status: verified` was recorded in the receipt.

```bash
aitbc --api-key "$CLIENT_JWT" tee register enc-live-01 --agent-id hub-coordinator
aitbc --api-key "$CLIENT_JWT" tee status enc-live-01
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "Confidential TEE live validation" \
  --payment 1.0 \
  --wallet genesis \
  --buyer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203 \
  --confidential \
  --enclave-measurement "sha256:0000000000000000000000000000000000000000000000000000000000000001" \
  --wait --timeout 180
```

Result:

```json
{
  "job_id": "9517cfc0500843c49abfc1f476469407",
  "state": "COMPLETED",
  "payment_status": "released",
  "escrow_tx_hash": "0xa44925d601d7fecba9f2e88f665f3bd130447d2839f16cea72f5af2af03e4c6d",
  "result": {
    "status": "completed",
    "tee_status": "verified",
    "tee_attestation_id": "ta_a9bef0c722",
    "zk_status": "not_required"
  }
}
```

## Key observations

- The `aitbc tee register` and `aitbc tee status` commands are wired to `/v1/tee/enclaves` and return the full `EnclaveIdentity` record.
- `aitbc ai submit --confidential --enclave-measurement ...` passes `confidential: true`, `tee_attestation_required: true`, `required_enclave_measurement`, and `tee_enclave_id` to the coordinator.
- The receipt’s `job_constraints` include `confidential: true` and the requested `required_enclave_measurement`.
- Escrow was released on-chain after the coordinator verified the auto-generated TEE attestation.



---

# ZK proof for high-value jobs — live validation

**Date:** 2026-08-21
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)
**Gitea `main`:** `dd6a446e7` — *feat(cli): add aitbc zk command group*
**Scenario:** `docs/scenarios/47_zk_high_value_jobs.md`

## What was validated

A ZK-proof-gated AI inference job was submitted through the canonical `aitbc` CLI. The coordinator generated a Groth16 receipt proof, verified it, and released escrow only after `zk_status: verified` was recorded.

### Coordinator environment

Added `/etc/systemd/system/aitbc-coordinator-api.service.d/zk.conf`:

```ini
[Service]
Environment="COORDINATOR_ENABLE_ZK_VERIFICATION=true"
```

Restarted `aitbc-coordinator-api.service`.

### CLI workflow

```bash
aitbc --api-key "$CLIENT_JWT" zk health
aitbc --api-key "$CLIENT_JWT" zk circuits

aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "ZK high-value job validation" \
  --payment 5 \
  --zk-proof-required \
  --wallet genesis \
  --buyer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 240

aitbc --api-key "$CLIENT_JWT" zk verify \
  --job-id 6f0f890035fb46be9950cacacbd32288 \
  --coordinator-url http://127.0.0.1:8203
```

### Result

Job `6f0f890035fb46be9950cacacbd32288`:

```json
{
  "job_id": "6f0f890035fb46be9950cacacbd32288",
  "state": "COMPLETED",
  "payment_status": "released",
  "escrow_tx_hash": "0x0c52a27e150578b53c6fc39f91801ab47f4975ef34a3ad45ec3ceb7866607ca9",
  "result": {
    "status": "completed",
    "zk_status": "verified",
    "tee_status": "not_required",
    "zk_proof": {
      "proof": { ... },
      "public_signals": ["5157032056236827201771028128265681883767077060594906061409975286648462337841"],
      "receipt": [ ... ],
      "circuit": "receipt_public",
      "circuit_hash": "9c780c45716ee8e2925ae7d922fffbc21cfc4546486d5f8ff217dcdff96376dc"
    }
  },
  "status": {
    "zk_status": "verified",
    "zk_proof_id": "9c780c45716ee8e2925ae7d922fffbc21cfc4546486d5f8ff217dcdff96376dc"
  }
}
```

`aitbc zk verify --job-id` returned:

```json
{
  "verified": true,
  "computation_correct": true,
  "privacy_preserved": true
}
```

## Key observations

- `COORDINATOR_ENABLE_ZK_VERIFICATION=true` is required for the coordinator to actually
  verify the generated proof and release escrow.
- The `aitbc zk` CLI surface (`health`, `circuits`, `verify`) is wired to the live
  `/v1/zk/*` endpoints.
- `aitbc ai submit --zk-proof-required` forces a ZK proof even when the payment is
  below the default 10 AIT high-value threshold.
- The receipt contains the full `zk_proof` object and `zk_status: verified`.
- `aitbc ai status` surfaces `zk_status` and `zk_proof_id` (the circuit hash).


---

# Performance bonds for high-value jobs — live validation

**Date:** 2026-08-21
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)
**Gitea `main`:** `b21d418df` — *fix(auth): add performance-bond routes to security matrix*
**Scenario:** `docs/scenarios/48_performance_bonds_high_value.md`

## What was validated

A provider performance bond was created through the canonical `aitbc` CLI. A high-value AI job that requires a bond was submitted and only assigned to the bonded miner. The job completed and escrow was released.

### CLI workflow

```bash
aitbc --api-key "$CLIENT_JWT" bond create aitbc-miner-1 --amount 10 --required-amount 10
aitbc --api-key "$CLIENT_JWT" bond status aitbc-miner-1
```

Bond status:

```json
{
  "provider_id": "aitbc-miner-1",
  "eligible": true,
  "status": "active",
  "amount": "10.00000000",
  "required_amount": "10.00000000",
  "bond_id": "bond-aitbc-miner-1"
}
```

### Bond-required job

```bash
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "Bonded high-value job validation" \
  --payment 5 \
  --bond-required \
  --wallet genesis \
  --buyer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 240
```

Result:

```json
{
  "job_id": "c6260a28ac824a0b905f115510151ef1",
  "state": "COMPLETED",
  "payment_status": "released",
  "escrow_tx_hash": "0xdf8debd40cecb97bc67d9ca01ebf3a091407d93c490b755dfe70b97e24236a9b",
  "receipt": {
    "metadata": {
      "job_constraints": {
        "bond_required": true,
        "min_bond_amount": null,
        ...
      }
    }
  },
  "status": {
    "assigned_miner_id": "aitbc-miner-1",
    "payment_status": "released"
  }
}
```

### High-value threshold job

A payment of 10 AIT automatically triggered bond, ZK, and TEE gates:

```bash
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "Automatic high-value bond and ZK validation" \
  --payment 10 \
  --wallet genesis \
  --buyer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 300
```

Result: `COMPLETED`, `payment_status: released`, `zk_status: verified`, `tee_status: verified`.

## Key observations

- `aitbc bond create/status` is wired to `/v1/marketplace/providers/{id}/bonds` and `/eligibility`.
- `aitbc ai submit --bond-required` passes `bond_required: true` and optionally `min_bond_amount`.
- The coordinator checks `is_provider_eligible` before assigning a job that requires a bond.
- The default `COORDINATOR_BOND_HIGH_VALUE_THRESHOLD` is 10 AIT.
- A payment at or above the threshold also triggers the existing ZK and TEE gates.


---

# Auto-reinvest from released escrow — live validation

**Date:** 2026-08-21
**Nodes:** `hub.aitbc` (hub/customer), `aitbc3` (shop/miner)
**Gitea `main`:** `21e4748fc` — *feat(coordinator,blockchain): trigger auto-reinvest on escrow release*
**Scenario:** `docs/scenarios/49_auto_reinvest_escrow.md`

## What was validated

A paid AI job submitted with `--auto-reinvest-pct 50` completed, escrow was
released, and an on-chain stake was created automatically from the released
earnings.

### CLI workflow

```bash
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "Auto reinvest validation" \
  --payment 5 \
  --auto-reinvest-pct 50 \
  --wallet genesis \
  --buyer-address ait1fe2d63fe87db282083b9159e5857cac788af9e03 \
  --provider-address aitbc1a54b82312beb65d0e90c21717ea372396991fa36 \
  --coordinator-url http://127.0.0.1:8203 \
  --wait --timeout 240
```

Result:

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
        "auto_reinvest_pct": "50.0"
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

### On-chain stake record

```bash
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
  "SELECT id,address,amount,locked_until,status FROM stake WHERE id=8;"
```

Output:

```text
8|0xa54b82312beb65d0e90c21717ea372396991fa36|8775|2026-09-20 21:16:41.185874|active
```

`8775` compute-seconds equals `2.4375 AIT * 3600`.

### Provider balance accounting

Provider `ait1a54b82312beb65d0e90c21717ea372396991fa36` balance before job:
`80730` compute-seconds. After the 5 AIT job with 2.5 % platform fee and 50 %
reinvest:

- Released escrow value: `5 * 3600 - 180` fee = `17550` compute-seconds
- Auto-stake amount: `2.4375 * 3600` = `8775` compute-seconds
- Final provider balance: `80730 + 17550 - 8775 = 89505` compute-seconds

Live observed balance: `89505`.

## Key observations

- `aitbc ai submit --auto-reinvest-pct` reaches the coordinator and is stored in
  `payment.meta_data`.
- `PaymentService.release_payment` passes `auto_reinvest_pct` and
  `auto_reinvest_address` to the blockchain escrow release endpoint.
- The blockchain `_auto_stake` canonicalizes the provider address and creates a
  `Stake` record.
- `reinvest_status`, `reinvest_stake_id` and `reinvest_amount` are attached to
  the job receipt and visible in the CLI result.

- 2026-08-22: Hub-wide pool hub miner registry validation:
  - `aitbc-pool-hub.service` runs on `hub.aitbc` and exposes `/pool-hub`.
  - `aitbc-miner` on `aitbc3` registers at `/v1/miners/register` and heartbeats
    at `/v1/miners/heartbeat`.
  - `aitbc pool-hub status` on `hub.aitbc` reports `miners_online: 1`.
  - `aitbc pool-hub status` on `aitbc3` resolves the hub from `HUB_DISCOVERY_URL`
    and also reports `miners_online: 1`.
  - `aitbc pool-hub sla` on both nodes reports `status: healthy`.
  - Scenario 36 updated to describe the hub-wide pool-hub architecture.
  - `tests/cli/test_commands_pool_hub.py` aligned with the follower/hub URL
    resolution logic and now passes.
- 2026-08-22: Escrow default/config drift fix:
  - `apps/blockchain-node/src/aitbc_chain/config.py` now sets `escrow_enabled=True`.
  - `docs/releases/STATUS.md` updated to list `escrow_enabled` default `True`.
  - `docs/DESIGN_CYCLE.md` step 3 gap marked `Done`.
  - Scope note clarifies job-payment escrow is live and cross-chain bridge HTLC is gated by this flag.

## 2026-08-22 — Escrow settlement hardening (cycle step 7)

Live-validated on `hub.aitbc`:

```bash
AITBC_WALLET_DIR=/var/lib/aitbc/wallets aitbc auth login --wallet default \
  --coordinator-url http://localhost:8203
aitbc ai submit --type inference --prompt "escrow settlement hardening validation" \
  --payment 1.0 \
  --buyer-address 0x35daba990a37177398e0e0c1670baa316a032417 \
  --provider-address 0x06F8bB05B167fa4E32F4AC61FA7cb02663205f35 \
  --wait --timeout 240 --poll-interval 5 --coordinator-url http://localhost:8203
```

- Job `e72705b6d0274e13bc8a340896f0e006` completed on `aitbc-miner-1`
  (`llama3.2:3b`, 542 tokens, 88.8s, GPU), `payment_status: released`.
- `ESCROW_RELEASE` tx `0xe733a8106e93940500ca320da830edd5bf4e9a8b1eb94239476fb105b9cccf36`
  (transaction id 509), status `confirmed`, nonce 42.
- Signed by the **non-genesis settlement address**
  `0x477737bd028eeb38350c58e62f7a766ac061ce2e`; recipient
  `0x06F8bB05B167fa4E32F4AC61FA7cb02663205f35`.
- Value 3510 compute-seconds = **0.975 AIT** after the 2.5% fee.
- The payload carries **no `released_at`**: the release transaction is deterministic,
  so a retry at the same nonce is deduplicated by the mempool rather than paying twice.

### Finding — the settled-release lookup was reading the wrong end of the chain

`/rpc/transactions` returns rows **oldest-first** and truncates to `limit`. The first
version of the lookup scanned the most recent 200 releases as it thought; in fact
`limit=40` did not return this job while `limit=500` did. A bounded scan therefore
misses recent settlements — exactly the ones a retry asks about — and because
`_get_account_nonce` reads the *current* nonce, a missed lookup would resubmit a valid
transaction at the next nonce and pay the provider twice.

Fixed by filtering server-side on payload `job_id`, verified live:

```text
?transaction_type=ESCROW_RELEASE&job_id=e72705b6d0274e13bc8a340896f0e006  -> 1 row (id 509)
?transaction_type=ESCROW_RELEASE&job_id=does-not-exist                    -> []
```

### Still outstanding

- Alembic `b7f3c1a90d24` (payload `job_id` expression index) is **not yet applied** on
  either node; the filter works unindexed.
- `SettlementReconciler` is implemented but **disabled by default**
  (`ESCROW_RECONCILER_ENABLED`), pending a watched run against a failed settlement.

### 2026-08-22 (later) — index, ordering and reconciler enablement

- **The chain DB is SQLite, not Postgres.** `/var/lib/aitbc/data/<chain_id>/chain.db`
  (10 MB, 521 transactions). A bare `alembic upgrade head` targets
  `/var/lib/aitbc/data/chain.db` — a different, empty file — exactly as `migrations/env.py`
  (V23-49) warns. Pass `DATABASE_URL` to name the island.
- The real DB had **no `alembic_version`**: its schema came from SQLModel `create_all`,
  so it was stamped at `d4e8b91c0a37` before applying `b7f3c1a90d24`. Backup taken first
  via `sqlite3 .backup` to `/var/lib/aitbc/data/chain-backup-2026-08-22.db`.
- **The index as first shipped was unusable.** SQLModel renders
  `payload["job_id"].as_string()` with the JSON *path* as a bound parameter, and neither
  SQLite nor Postgres matches a parameterised path against an expression index built on a
  literal one. `EXPLAIN QUERY PLAN` reported `SCAN transaction`. With the path inlined it
  reports `SEARCH transaction USING INDEX ix_transaction_payload_job_id`. The searched
  value stays bound; only the fixed path is inline.
- **Ordering fixed.** `query_transactions` now orders newest-first, so `limit` returns the
  most recent rows: `limit=3` returns ids 509, 91, 84 where it previously returned 13, 14, ...
  The only other consumer, `aitbc wallet transactions --limit`, was showing the oldest
  transactions to users.
- **Reconciler enabled on hub**: `ESCROW_RECONCILER_ENABLED=true`, interval 300s, min age
  120s, batch 25. Startup confirms `Started background task: escrow_settlement_reconciler`.
  It has not yet been observed recovering a deliberately failed settlement.

### 2026-08-23 — aitbc3 upgrade, reconciler heartbeat, and a watched recovery

**aitbc3 brought up to `main` (`c0c18557b`).** Its chain island is
`/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db` (528 transactions). Backed up with
`sqlite3 .backup`, stamped `d4e8b91c0a37`, then upgraded to `b7f3c1a90d24`.
`EXPLAIN QUERY PLAN` reports `SEARCH transaction USING INDEX ix_transaction_payload_job_id`.
RPC restarted; `/rpc/transactions?limit=2` returns `transaction_id` 528 first, confirming
newest-first. Reconciler enabled (`ESCROW_RECONCILER_ENABLED=true`, 300s/120s/25); startup
logs `Started background task: escrow_settlement_reconciler`. The one escrowed job on
aitbc3 (`d27ad1aaf3154bba886937099cfe3f07`) is `EXPIRED` with `completed_at` NULL and is
therefore correctly out of the reconciler's scope.

**The coordinator does not use the Postgres DSN in its own env file.** On both nodes
`get_engine()` resolves to `sqlite:////var/lib/aitbc/data/coordinator.db`; the
`DATABASE_URL=postgresql://...` line in `/etc/aitbc/aitbc-coordinator-api.env` is never
read. That Postgres database on aitbc3 is in fact damaged — `invalid page in block 4 of
relation base/16395/2620` (`pg_trigger`), with `data_checksums=off` — and its `public.job`
table has 0 rows and no `completed_at` column. Nothing reads it, so it breaks nothing
today, but the misleading DSN should be removed before anything is ever pointed at it.

**Heartbeat.** `run_once()` now logs `scanned/retried/settled/failed` at debug on every
pass, so a pass with nothing to do is no longer indistinguishable from a dead task.
Verified: `Settlement reconciliation pass complete: scanned=0 retried=0 settled=0 failed=0`.
It is reachable in the service through `LOG_LEVEL=DEBUG` (`settings.log_level` is passed to
`configure_logging()` in `main.py`). A bare script that skips `configure_logging()` will not
show it — the root logger defaults to WARNING and `get_logger()` sets no level.

**Watched recovery.** Live job `61316a3f83c84757a68c017c70c6204a` settled normally as
`0x488f667678fcac94021e64c8175262655c78ca01a22f9cabbb61000365ca2265`. A scratch copy of the
coordinator DB was rewound to `escrowed` and driven through the real `SettlementReconciler`
against the live chain RPC:

| pass | chain RPC | counts | result |
|---|---|---|---|
| 1 | unreachable (`127.0.0.1:1`) | `retried=1 settled=0 failed=1` | payment left `escrowed`, warning logged |
| 2 | live (`127.0.0.1:8202`) | `retried=1 settled=1 failed=0` | job and payment `released`, tx `0x488f66...` |

On-chain `ESCROW_RELEASE` count for that job is **exactly 1**, sender
`0x477737bd028eeb38350c58e62f7a766ac061ce2e`, value 3510 compute-seconds. The retry
returned the existing settlement rather than paying twice, which is the property the whole
retry design rests on. The escrow contract still reports `released_amount` 0.975 (not
doubled); its `released_at` was rewritten to the retry time, which is cosmetic drift.

Caveat: the failure was injected at the coordinator's RPC URL against a scratch DB copy.
Degrading the live settlement path directly — editing `ESCROW_RELEASE_ADDRESS`, adding a
systemd override, or stopping `aitbc-blockchain-rpc` mid-job — was refused by the operator
guard. So detection, real retry over HTTP, the idempotency short-circuit and the DB
transition are all proven; the "fresh settlement lands after a transient outage" branch is
still unproven in production.

This closes the two items left open above: `b7f3c1a90d24` is now applied on both nodes, and
the reconciler is enabled on both.

## 2026-08-23 — coordinator migrations recovered from the wrong database

### The bug

`apps/coordinator-api/alembic/env.py` resolved its target as
`DATABASE_URL or SQLITE_URL or app_settings.database.effective_url`. The deployed
env file `/etc/aitbc/aitbc-coordinator-api.env` set `DATABASE_URL` to a Postgres
DSN, but the running service resolves its engine from
`settings.database.effective_url` and never reads `DATABASE_URL`.

Every `alembic upgrade` therefore advanced a Postgres schema that nothing reads,
while the live SQLite database silently fell behind head:

| node | live SQLite was at | head | behind |
|---|---|---|---|
| hub.aitbc | `1a7d8e9b0c2f` | `a3e7c15b8d94` | 3 revisions |
| aitbc3 | `e9cf23ae4640` | `a3e7c15b8d94` | 11 revisions |

Meanwhile hub's unused Postgres DB sat at head, and aitbc3's had no
`alembic_version` row at all and is corrupt (`invalid page in block 4 of
relation base/16395/2620`).

The three revisions missing on hub are the V23 Float→Numeric money-column
conversions. The SQLModel models already declared `Numeric`, so model and
schema had drifted apart on the live payments database.

### The fix

1. **Guard** (`42d31e5af`) — `env.py` now resolves both URLs, prints the target it
   is about to migrate, and warns loudly when the override disagrees with what the
   app reads. Passwords are redacted so a DSN never lands in a log. The override
   is kept because CI relies on it.

2. **Config** — the dead `DATABASE_URL` line is commented out in
   `/etc/aitbc/aitbc-coordinator-api.env` on both nodes (backup:
   `.bak-2026-08-23`), so alembic and the app now agree on one source of truth.
   Verified safe first: `EnvironmentFile=/etc/aitbc/%N.env` expands per-unit, so
   only `aitbc-coordinator-api.service` loads that file, and the sole in-app
   reader of `DATABASE_URL` is an unreferenced diagnostic list in
   `contexts/language/services/multi_language/config.py`.

3. **Migrations applied live**, after a dry run against a `sqlite3.backup()`
   snapshot of each live database.

### Dry run, then live

Both nodes reached `a3e7c15b8d94` with `PRAGMA integrity_check` = ok.

| | pending | tables | money sums before → after |
|---|---|---|---|
| hub.aitbc | 3 | 158 → 158 | unchanged (see below) |
| aitbc3 | 11 | 198 → 205 | unchanged |

hub money columns, all now `NUMERIC(20, 8)`:

| table | column | rows | sum before | sum after |
|---|---|---|---|---|
| job_payments | amount | 69 | 209.74 | 209.74 |
| payment_escrows | amount | 63 | 184.73 | 184.73 |
| provider_bond | amount | 1 | 10.0 | 10.0 |
| provider_bond | required_amount | 1 | 10.0 | 10.0 |
| agent_reputation | total_earnings | 6 | 16.6138 | 16.6138 |

`PRAGMA foreign_key_check` on hub reports 39 violations both before and after —
orphaned `reputation_events` (31), `agent_reputation` (6) and `community_feedback`
(2) rows. The migration introduces none of them. **Open finding**, unrelated to
this work.

Procedure per node: stop `aitbc-coordinator-api` → `cp -a` the database to
`coordinator.db.bak-2026-08-23-premigrate` → `alembic upgrade head` → verify →
start. Neither node logged a warning or error after restart; `/health` returned
200 on both; the escrow settlement reconciler came back up on hub
(`interval=300s min_age=120s batch=25`).

### End-to-end proof

Reading through the app's own engine and models after the migration:

```
job_payments    -> JobPayment     amount=Decimal('5.00000000')
payment_escrows -> PaymentEscrow  amount=Decimal('0.01000000')
```

Exact decimals, not floats — schema and models now agree.

### Correction to an earlier note

An earlier draft of this document framed the exposure as "102 Float money
columns". That count came from the migration source, not from the data. On the
live hub database only `provider_bond.amount`, `provider_bond.required_amount`,
`regional_hub.budget_allocation`, `regional_hub.spent_budget` and
`agent_reputation.total_earnings` were both Float-typed and populated — about six
rows in total. `job_payments.amount` and `payment_escrows.amount` were already
`NUMERIC`. The remaining Float columns hold scores and ratings, not money.

### Still open

- The orphaned Postgres databases should be dropped or repaired rather than left
  advertising themselves. aitbc3's is corrupt.
- The Postgres DSN password was printed to a terminal during this session and is
  worth rotating.
- 39 pre-existing FK violations on hub's reputation tables.

## 2026-08-23 — OPEN DECISION (already diagnosed): the staking/bounty chain surface

**This is not a new finding.** It was diagnosed on 2026-08-11 in `2b2d0d923`
("repoint the chain client at endpoints that exist", AITBC-155 / V23-42) and is
documented in the `BlockchainService` class docstring
(`contexts/blockchain/services/blockchain.py`). It is recorded here because the
decision it names is still open and is not tracked in any markdown — it lives
only in a commit message and a docstring, which is how it came to be
re-discovered from scratch today.

### The answer to "was the staking/bounty surface ever intended to exist?"

No. Per V23-42, the twelve outbound URLs are *"near-copies of this app's own
staking routes (`contexts/staking/routers/staking.py`) addressed to the node's
host"*, and *"there are no bounty routes on the node at all"*. They were never a
client for a planned chain API; they are a duplicate of the coordinator's own
surface pointed at the wrong host.

That commit fixed what could be fixed and deliberately stopped there:

| call | disposition in `2b2d0d923` |
|---|---|
| `get_balance` | repointed to `GET /rpc/balance/{address}`; also fixed a response-key bug that would have reported every account empty |
| `mint_tokens` | now raises `NotImplementedError` — the nearest real endpoint is the devnet faucet, and wiring it up *"turns a broken fake into a working one that credits real balance to anyone who asks"* |
| the other 12 | **left unprefixed on purpose** — *"a prefix that makes a URL look resolvable is worse than one that plainly does not"* |

Two tests pin client-to-node and mock-to-node correspondence, both built by
importing `aitbc_chain` rather than by running a node or a mock. The commit notes
the old `tests/fixtures/mock_blockchain_node.py` had been *"written to match the
client rather than the server, so the two agreed with each other and neither
agreed with the node."*

### Corrections to the first draft of this section

An earlier version of this entry, written before the V23-42 history was found,
got two things wrong. Both are corrected here.

**"1 of 12 is fixed by adding the `/rpc` prefix" — wrong. It is 0 of 12.**
`POST /rpc/staking/stake` does exist, but `rpc/staking.py:56` rejects any request
without a staker signature (`403 Signature required for staking`), and this app
has no access to an agent's staking key. It also expects `lock_days` while the
coordinator sends `lock_period`. The prefix fixes nothing.

**"Latent, not active — the calls fail loudly" — half wrong.**
The *server log* does record an error: `AITBCHTTPClient.post` calls
`raise_for_status()`, the caller catches `NetworkError` and logs it. But these are
FastAPI background tasks, so the router has already returned 200/201 before the
call fails. As the docstring puts it: *"a client that stakes or deploys a bounty
is told it succeeded and nothing reaches the chain."* The failure is visible in
the journal and invisible to the caller, which is the direction that matters.

### Current exposure

Unexercised, which is why it has caused no damage. On hub, no matching journal
entries over 7 days and every related table is empty — `agent_stakes`,
`bounty_integrations`, `bounty_stats`, `bounty_submission`, `bounty_submissions`,
`bounty_task`, all 0 rows.

The risk is first use, not present state. `contexts/staking/routers/staking.py:293`
commits coordinator DB state and *then* queues the chain call:

```python
updated_stake = await staking_service.add_to_stake(...)          # local state committed
background_tasks.add_task(blockchain_service.add_to_stake, ...)  # 404s, logged, dropped
```

so the first real staking request writes a coordinator-side stake with no on-chain
counterpart and returns success — local state diverging from chain state, the same
shape as the settlement drift fixed in `1b43ca3bd`.

### The decision that is still open

V23-42 names it precisely: *"what is needed is either the endpoints on the node or
the removal of these calls — a design decision, not a rename."* Unchanged since
2026-08-11. Either:

- **build the surface on the chain node** (11 endpoints, plus a signing story for
  `/rpc/staking/stake` that the coordinator cannot currently satisfy), and stop
  committing local state before the chain call succeeds; or
- **remove it** — delete the twelve methods and the `admin_api_keys` header
  plumbing that goes with them, and make the coordinator's staking and bounty
  routers either honest about being local-only or return 501.

Worth tracking in `TASKLIST.md` so it stops being rediscovered.

### Two adjacent notes from the same investigation

**`admin_api_keys` is a dead parameter, not a security gap.** The chain RPC
enforces no `X-Api-Key` anywhere — no middleware, no route dependency; the live
OpenAPI lists only `HTTPBearer` under `securitySchemes` with global `security` of
`none`. The empty list changes nothing. Coordinator-side admin routes fail closed
(`admin.py:105`), which is the safe direction.

**`ENVIRONMENT` does not affect the database.** Recorded because it was assumed
otherwise earlier in this session.
`DatabaseConfig.effective_url` (`packages/aitbc-shared/aitbc_shared/core/config.py:69`)
never reads it; the path comes from `AITBC_DATA_DIR` (unset → `/var/lib/aitbc`)
and `db_filename`:

```
ENVIRONMENT=development  -> sqlite:////var/lib/aitbc/data/coordinator.db
ENVIRONMENT=production   -> sqlite:////var/lib/aitbc/data/coordinator.db
```

The same file explains why the app ignored `DATABASE_URL`:
`_load_legacy_database_url` honours it only when `DATABASE_ADAPTER` is also set
and the schemes agree — a deliberate guard so a stale `DATABASE_URL` cannot
silently switch a running deployment to PostgreSQL. It worked as designed; only
alembic bypassed it, which is what today's migration work fixed.

Flipping `ENVIRONMENT=production` on hub today fails with four validation errors
(`client_api_keys` and `admin_api_keys` empty, localhost CORS origins, localhost
`blockchain_rpc_url`). `JWT_SECRET` and `MINER_API_KEYS` are set correctly — the
"ephemeral test secret" warning only appears in ad-hoc shells that do not source
the env file. The two localhost validators look wrong for a single-host
deployment rather than something to configure around.

---

# 2026-08-24 — escrow-lock, FK integrity, live validation

**Date:** 2026-08-24
**Nodes:** `hub.aitbc`, `aitbc3`
**Gitea `main`:** `ba4c4cfbe` — *docs(tasklist): escrow-lock decision and implementation*

## What changed

1. **Escrow is now chain-backed for new contracts.**
   - `Escrow` model gained `status`, `lock_tx_hash`, `refunded_at`, `refund_tx_hash` (migration `498540b266b4`).
   - `/rpc/escrow/create` requires a buyer-signed `ESCROW_LOCK` transaction that moves the escrow amount from the buyer to the node wallet.
   - `/rpc/escrow/{job_id}/release` only releases when `Escrow.status == 'locked'` and a real `ESCROW_RELEASE` transaction from the node wallet to the provider succeeds on-chain.
   - Coordinator `PaymentService` builds and submits the lock tx, using a provided `buyer_lock_signature` or signing with `PAYMENT_BUYER_PRIVATE_KEY` for test/operator flows.

2. **FK integrity now passes on both nodes.**
   - Migration `d38eb9f3a80b` recreated five reputation-related tables without the incorrect FK constraints.
   - Migration `46c9bffdf9c6` inserted the missing `account` row for the four chain escrow orphans.
   - `PRAGMA foreign_key_check` is empty on hub `coordinator.db` and `chain.db`.

3. **Historical unbacked payouts preserved.**
   - 58 released escrows totalling ~173 AIT remain as recorded evidence; the new flow does not backfill them.

## Validation results

- `bash scripts/ci/mypy-precommit.sh` — 0 new errors
- `python3 scripts/lint/no_float_money.py` — 0 violations
- `bash scripts/ci/check-openapi-drift.sh` — 5 specs match
- `python3 -m pytest apps/blockchain-node/tests/test_escrow_lock.py apps/coordinator-api/tests/test_settlement_lifecycle.py apps/coordinator-api/tests/test_integration_blockchain_payments.py` — 17 passed
- Live health: `aitbc-blockchain-rpc`, `aitbc-coordinator-api`, `aitbc-marketplace` all return 200 on both nodes.
- `python3 -m alembic upgrade head` applied to hub and shop `chain.db` successfully.
- `sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db "PRAGMA foreign_key_check;"` returns empty.

## Open work

None. The V23-42 agent-stake / bounty surface, `AITBC_WALLET_DIR`, and OpenAPI regen were completed and live-validated in the same session.

# 2026-08-24 — V23-42 agent-stake and bounty live validation

**Date:** 2026-08-24
**Node:** `hub.aitbc`
**Gitea `main`:** `66d38e225`

## What was validated

A dedicated test wallet (`v23-42-test`, `ait1315733b7cb944f1d14e2af35388740cbb7bd2e93`) was funded with 700 AIT from the genesis wallet and the V23-42 agent-economy RPC surface was exercised end-to-end on the live hub blockchain RPC.

### Agent staking

| step | endpoint | amount | result |
|---|---|---|---|
| create | `POST /rpc/agent-staking/stake` | -100 AIT | `active`, `Account.balance` down 360,000 sec |
| add | `POST /rpc/agent-staking/stake/{stake_id}/add` | -50 AIT | `amount` 540,000 sec, `Account.balance` down 180,000 sec |
| unbond (pre-expiry) | `POST /rpc/agent-staking/stake/{stake_id}/unbond` | n/a | `400` "Lock period not expired" (correct) |
| performance | `POST /rpc/agent-staking/performance` | n/a | memo stored, no balance move |
| distribute | `POST /rpc/agent-staking/agents/{agent_wallet}/distribute` | n/a | memo stored, no balance move |
| claim-rewards | `POST /rpc/agent-staking/claim-rewards` | n/a | memo stored, no balance move |

`unbond` and `complete` could not be exercised to maturity because `lock_period=1` day (the minimum) makes the stake mature on 2026-08-24. The node correctly refused `unbond` before `locked_until`.

### Bounties

| step | endpoint | amount | result |
|---|---|---|---|
| deploy A | `POST /rpc/bounty/deploy` | -10 AIT | `active`, `Account.balance` down 36,000 sec |
| submit A | `POST /rpc/bounty/{bounty_id}/submit` | n/a | submission `pending` |
| verify A | `POST /rpc/bounty/{bounty_id}/verify` | +10 AIT to winner | `completed`, `payout` 36,000 sec |
| deploy B | `POST /rpc/bounty/deploy` | -10 AIT | `active`, `Account.balance` down 36,000 sec |
| expire B | `POST /rpc/bounty/{bounty_id}/expire` | +10 AIT refund | `expired`, `refunded` 36,000 sec |
| dispute on completed A | `POST /rpc/bounty/{bounty_id}/dispute` | n/a | `400` "Cannot dispute a paid bounty" (correct) |

### Balance checks

- Staker balance: `2,520,000` sec → `1,008,000` sec (440 AIT), matching all debits, the add increment, the bounty B refund, and the absence of any move for memos.
- Winner (`ait1fe2d63...`) balance increased by exactly 36,000 sec on verify.
- Insufficient-balance request was rejected with `400` and the correct on-chain `Account.balance`.

### Operator signature

Every mutating request was signed with `AGENT_ECONOMICS_OPERATOR_KEY` and verified by the node against `AGENT_ECONOMICS_OPERATOR_ADDRESS`. The coordinator journal has no post-fix `NetworkError` / `Failed to create stake contract on-chain` entries for the new surface.

### Verification

- `mypy-precommit.sh` — 0
- `no_float_money.py` — 0
- `check-openapi-drift.sh` — passes
- `pytest apps/blockchain-node/tests` — all green
- `test_blockchain_client_paths.py` — 3 passed
- `test_routers_bounty.py` — green
- `journalctl -u aitbc-coordinator-api` — no new staking/bounty `NetworkError` entries

## Notes

- The test wallet private key and the operator signing key were kept in node env files; they were not committed or printed.
- One unbond/complete maturity test was completed immediately after this section by moving the test stake's `locked_until` one minute into the past and calling `POST /rpc/agent-staking/stake/{stake_id}/unbond` then `POST /rpc/agent-staking/stake/{stake_id}/complete`. `unbond` left the balance unchanged and marked the stake `unbonding`; `complete` credited the full principal (540,000 compute-seconds) and marked the stake `completed`. The staker `Account.balance` moved from 1,008,000 to 1,548,000 compute-seconds.

---

## P1.3 — Cross-island bridge multi-sig live validation

**Date:** 2026-08-23  
**Nodes:** `aitbc3` (shop/follower) with independent island `ait-shop-island.aitbc.bubuit.net`  
**Gitea `main` baseline:** `2e18868ca` — *P1.3 cross-island bridge multi-sig*

### What was validated

1. Island chain startup  
   - `aitbc3` runs `ait-hub.aitbc.bubuit.net` (follower) and `ait-shop-island.aitbc.bubuit.net` (island) on RPC 8202/8302 and P2P 8007/8107.

2. Validator registration  
   - Registered 5 island validators under `ait-hub.aitbc.bubuit.net` with 2-of-5 multi-sig threshold and admin authorization.

3. Live lock → proof → sign → store header → confirm  
   - Locked 50 compute-seconds on hub from `ait19df8f71c4161364898e0ad0b33e2368b227fe612` to island proposer `0x2b212528b2bf4339ac06dda50f8751c46e6c2fd4`.
   - Built a real Merkle Patricia Trie proof for the locked transfer.
   - Signed the proof with two validator keys, satisfying the multi-sig threshold.
   - Stored a `BridgeBlockHeader` for hub height 1, signed by a validator in the set and authorized by the bridge admin.
   - Confirmed on `ait-shop-island.aitbc.bubuit.net`; the island proposer balance increased to `10000000050`.
   - Transfer record `0x45e3cb856c9da0e40a85a3904c454408fb6b1aef69dbac5077c136f5a8d423e9` shows `status: completed` on the target chain.

### Quality gates

- Mypy clean on 9 changed bridge/CLI/database files.
- `no_float_money` gate: 0 violations.
- OpenAPI drift check passed; `docs/api/blockchain-node-openapi.json` regenerated.
- Bridge test suite (`test_v070_bridge_basics.py`, `test_v071_bridge_security.py`, `test_v072_bridge_verification.py`, `test_bridge_suite.py`, `test_bridge_security_audit_fixes.py`, `test_bridge_nonce.py`, `test_cross_chain_security.py`) passes with 100% completion.

### Data-integrity / operational findings

- `my-agent-wallet.json`, `test-wallet-2.json`, and `test-wallet-3.json` in `/var/lib/aitbc/wallets/` have `private_key` values that do **not** derive to the wallet address (key mismatch). The test wallet `test-bridge-wallet` was created and funded via the `/rpc/faucet` endpoint for this validation.
- The source-chain `account` balance for the test wallet after the bridge lock was reported as 200 by `/rpc/account` and the sender nonce remained 0, which diverges from the expected `initiate_transfer` balance/nonce update. This is recorded for follow-up: the `CrossChainTransfer` and island release succeeded, but the source-account debit path needs verification under the merged `main` tree.
- The `aitbc-blockchain-rpc` service is running from `main` (`2e18868ca`) and the island proposer is producing blocks; the `aitbc-blockchain-node` service was also restarted to load the updated `database.py` `expire_on_commit=False` setting.


### Island proposer / MultiValidatorPoA feature flag (2026-08-23 follow-up)

- `aitbc-blockchain-node` on aitbc3 produced the first real island block at height 1 (`0xc23afa9f...`) after setting `MULTI_VALIDATOR_CONSENSUS_ENABLED=false` in `/etc/aitbc/blockchain.env` and restarting the shop-side blockchain node.
- With `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`, the PoA proposer selected a validator (`ait1ffbda3398a7b1e016fddd509834b07dc8f4034e6`) from the configured `VALIDATOR_SET` that the shop node does not control, so it skipped every proposal at height 1.
- Disabling the feature flag falls back to the configured `PROPOSER_ID`/`proposer_key` for the island, which the shop node does control, so it can sign and broadcast blocks.
- ✅ **Gap closed**: bridge release transactions are now recorded in island blocks. `confirm_transfer` creates a `bridge_release` account and a `BRIDGE_RELEASE` `Transaction` with `block_height=NULL`, and the island proposer's block proposal now drains these pre-registered DB transactions and sets their `block_height`.

### Bridge release block inclusion — 2026-08-23 follow-up

**Date:** 2026-08-23  
**Gitea `main`:** updated on `aitbc3`  

1. **Code changes**
   - `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py`:
     - `confirm_transfer` now creates a `bridge_release` system account and a `BRIDGE_RELEASE` `Transaction` with `value=0`, `block_height=NULL`, and `status="confirmed"`.
     - The recipient is credited immediately; the `Transaction` is anchored in the next island block.
     - `confirm_transfer` also updates the source-chain `CrossChainTransfer` record to `completed` and sets `target_tx_hash`, so bridge health and balance endpoints report the finalised state.
   - `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`:
     - `_propose_block` now queries the chain DB for pre-registered `Transaction` records (`block_height=NULL` and `status="confirmed"`) and adds them to the block's transaction list.
     - Pre-registered `MESSAGE`/`BRIDGE_RELEASE` transactions are recorded in the block without re-running the state transition, avoiding double-credit and replay failures.
     - The `Transaction` record is updated in place with `block_height` and `status="confirmed"` rather than creating a duplicate.

2. **Live validation**
   - After restart, the two previously-pending bridge release transactions were anchored in island blocks 10 and 12.
   - A fresh 50-unit hub→island bridge was locked, confirmed, and the release transaction was included in island block 18 (`ec104e2e4e37ec5fd097e48f043ade54f570481d604e997e336340c88e63315a`).
   - Source account `ait19df8f71c4161364898e0ad0b33e2368b227fe612` was correctly debited (balance 150, nonce 1 after a 50-unit lock).
   - Bridge health reports `pending_transfer_count: 0` and `total_locked_amount: 0` after source records were marked `completed`.

3. **Quality gates**
   - `mypy` clean on `bridge_transfer.py`, `poa.py`, and `database.py`.
   - `no_float_money.py`: 0 violations.
   - `pytest apps/blockchain-node/tests/`: all green.
   - `check-openapi-drift.sh`: 5 specs match.

4. **Resolved operational findings**
   - Hub→shop state sync state-root mismatch was caused by a follower-side `bridge/lock` writing source `Account` state that the upstream hub did not include, plus a faucet-created test account (`ait13ed...`) that existed only on the shop. Removing the local-only account and moving the lock operation to the hub producer eliminated the mismatch and the `Invalid nonce` warning.
   - The source-account debit anomaly for new transfers is fixed by the commits below; only the historical pre-fix transfers (`0x45e3...`, `0x4bb3...`, `0x3b3b...`, `0x6eb4...`) remain as data archaeology.

### Bridge source-chain locking and follower sync — 2026-08-23 follow-up

**Date:** 2026-08-23  
**Gitea `main`:** `2b033c1be` — *fix(bridge,consensus,state): real source-chain bridge locks and follower sync*

1. **Code changes**
   - `bridge_transfer.py`:
     - `initiate_transfer` rejects source chains the node does not produce when `default_peer_rpc_url` is configured, preventing follower nodes from creating local source state that is later overwritten by upstream sync.
     - When produced locally, the `BRIDGE_LOCK` `Transaction` is marked `confirmed` with `block_height=NULL` and a `bridge_lock` account is created; the proposer includes it in the next block.
   - `consensus/poa.py`:
     - The pre-registered transaction bypass now includes `BRIDGE_LOCK`, so source locks are anchored in real source blocks without double-debiting.
   - `state/state_transition.py`:
     - `BRIDGE_LOCK` is now a first-class transition: the `bridge_lock` recipient account is created lazily and the locked amount is transferred.
   - `rpc/routers/bridge.py`:
     - `POST /bridge/lock` no longer validates the target chain against `supported_chains`, allowing the hub to lock funds for an island target without requiring an island genesis block.

2. **Live validation**
   - Locked 30 units on `hub.aitbc` (`ait19df8...`) with target `ait-shop-island` using the hub `bridge/lock` endpoint.
   - The `BRIDGE_LOCK` transaction was included in hub block 12240 (`0xbc85be0964a982272cc4da6660b052de28390d41bac566e8bccd48f9ef759d55`).
   - `aitbc3` imported hub block 12240 and its `Account` table now matches the hub: `ait19df8...` balance 120, nonce 2.
   - Proof was generated on the hub, block header stored on `aitbc3`, and confirm succeeded.
   - The island release transaction was anchored in shop island block 40 (`551a7ee4a6f820a11d4c8961c7fc97076a0d2a40050dde7f16ea473f9cb796e6`).
   - `journalctl` no longer reports state-root mismatch or invalid-nonce warnings for the hub sync.

3. **Quality gates**
   - `mypy` clean on `bridge_transfer.py`, `poa.py`, `state_transition.py`, and `rpc/routers/bridge.py`.
   - `no_float_money.py`: 0 violations.
   - `pytest apps/blockchain-node/tests -k bridge`: all green.
   - `check-openapi-drift.sh`: 5 specs match.

### Follower sync 503 fix — 2026-08-23

**Date:** 2026-08-23  
**Gitea `main`:** `d52ba4520` — *fix(sync): avoid pulling locally-produced island chains from default hub*

1. **Problem**
   - `aitbc3` logs showed repeated `[ERROR] [aitbc_chain.sync_bulk] Failed to fetch remote head` because the periodic sync task asked `hub.aitbc` for `ait-shop-island.aitbc.bubuit.net`, which the hub does not serve.

2. **Fix**
   - `aitbc/sync/source_resolver.py` now exposes `is_fallback_source(chain_id)`.
   - `apps/blockchain-node/src/aitbc_chain/main.py` resolves the sync source per chain in `_periodic_sync_task` and skips chains that fall back to the default peer and are in `BLOCK_PRODUCTION_CHAINS`.
   - The gap-check and bulk-import loops use the same per-chain source.

3. **Live result**
   - After restarting `aitbc-blockchain-node` on aitbc3, the logs now show `INFO  [aitbc_chain.main] Skipping sync for locally-produced chain ait-shop-island.aitbc.bubuit.net` instead of `Failed to fetch remote head`.
   - Hub sync continues normally for `ait-hub.aitbc.bubuit.net`.
   - Both `aitbc3` and `hub.aitbc` report `bridge/health` healthy.

### GPU_MARKETPLACE block import / empty tx_hash fix — 2026-08-23

**Date:** 2026-08-23  
**Gitea `main`:** `fb338a07a` — *fix(sync): compute missing tx_hash from block broadcast content*

1. **Problem**
   - Logs on `aitbc3` showed:
     ```
     [WARNING] [aitbc_chain.state.state_transition] Replay attack detected: Transaction  already persisted
     [ERROR] [aitbc_chain.subscription_client] Failed to import block 12249: UNIQUE constraint failed: transaction.chain_id, transaction.tx_hash
     ```
     The `tx_hash` field was an empty string in the `INSERT` parameters.
   - Root cause: block broadcasts from the proposer carry the raw signed transaction content and did not include the pre-computed `tx_hash`.  `sync_block_import` defaulted to `tx_data.get("tx_hash", "")`, which produced empty hashes.  When another transaction with an empty hash was imported, it collided with the existing empty-hash row in the DB.

2. **Fix**
   - `apps/blockchain-node/src/aitbc_chain/sync_block_import.py` now imports `compute_tx_hash` from `mempool` and computes a non-empty `tx_hash` for every transaction that arrives without one.

3. **Live result**
   - After restarting `aitbc-blockchain-node` on `aitbc3`, GPU_MARKETPLACE transactions are now imported with full `tx_hash` values (e.g. `0x33644ebdb507cf6ff70af28ffe07b54c7d5e2c9e7e67b0c09d8b2c368592aebc`).
   - No further `UNIQUE constraint failed` or `Replay attack detected` errors for block imports.
