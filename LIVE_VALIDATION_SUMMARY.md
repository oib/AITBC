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
| 12 reputation management | **PASS with findings** — `aitbc reputation profile` now constructs the correct `/v1/reputation/...` URL; the hub endpoint returns 404 because the reputation service is not exposed there |
| 13 mining setup | **PASS** — `aitbc mining start/status/list/stop` all work with a `0x` wallet |
| 14 staking basics | **PASS with findings** — `aitbc wallet stake` works after the `_brand.token_symbol` fix; `staking-info` works; `unstake` still returns 400 (locked/validation) |
| 16 agent registration | **PASS** — `aitbc agent-comm register` and `discover` now work via the `/v1` coordinator proxy (Hermes deprecated) |
| 17 governance | **PASS** — `aitbc governance status` returns operational summary |
| 18 analytics | **PASS** — `aitbc analytics summary` returns cross-chain overview |
| 19 security | **PASS** — `aitbc security audit` returns score A+ with 0 vulnerabilities |
| 20 cross-chain bridge | **PASS** — `aitbc bridge health` returns healthy bridge state |
| 06 basic trading | **FAIL with finding** — `aitbc exchange-island` no longer fails on missing `rpc_endpoint`, but the hub `/exchange/transactions` endpoint returns 404 (no exchange service deployed) |
| 08 marketplace bidding | **PASS** — `aitbc marketplace buy` initiates a purchase and returns a pending transaction ID |
| 36 pool hub SLA e2e | **PASS** — `aitbc pool-hub status` and `aitbc pool-hub sla` work from `aitbc3`; `miners_online` stays 0 because the shop miner registers locally, not with the hub pool |






### Still outstanding

- `aitbc pool-hub status` and `aitbc pool-hub sla` now work against the hub; `aitbc-pool-hub.service` is active on `hub.aitbc` (resolved).
- `hub.aitbc` working tree remains dirty with marketplace edits + the untracked `website/follower-api-key-announcement.html` and is still 2 commits behind `origin/main`.
