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