# Live Validation Summary

Daily validation notes are split into the `LIVE_VALIDATION_DAYS/` folder.

- [2026-08-20](LIVE_VALIDATION_DAYS/2026-08-20.md)
- [2026-08-21](LIVE_VALIDATION_DAYS/2026-08-21.md)
- [2026-08-22](LIVE_VALIDATION_DAYS/2026-08-22.md)
- [2026-08-23](LIVE_VALIDATION_DAYS/2026-08-23.md)
- [2026-08-24](LIVE_VALIDATION_DAYS/2026-08-24.md)
- [2026-08-25](LIVE_VALIDATION_DAYS/2026-08-25.md)
- [2026-08-26](LIVE_VALIDATION_DAYS/2026-08-26.md)
- [2026-08-27](LIVE_VALIDATION_DAYS/2026-08-27.md)
- [2026-08-28](LIVE_VALIDATION_DAYS/2026-08-28.md)
- [2026-08-30](LIVE_VALIDATION_DAYS/2026-08-30.md)
- [2026-08-31](LIVE_VALIDATION_DAYS/2026-08-31.md)
- [2026-09-01](LIVE_VALIDATION_DAYS/2026-09-01.md)
- [2026-09-02](LIVE_VALIDATION_DAYS/2026-09-02.md)
- [2026-09-03](LIVE_VALIDATION_DAYS/2026-09-03.md)
- [2026-09-07](LIVE_VALIDATION_DAYS/2026-09-07.md)
- [2026-09-08](LIVE_VALIDATION_DAYS/2026-09-08.md)

To add a new day, create `LIVE_VALIDATION_DAYS/YYYY-MM-DD.md`.

## 2026-09-02 — consensus recovery and G5 downtime slash

- Disabled PBFT/multi-validator consensus on hub, aitbc3, hub2, and node1 and restarted blockchain services. Hub resumed block production; hub and followers converged at height 2731 with identical head hash and state root.
- Live-validated the `downtime` slashing path end-to-end:
  - Created a fresh on-chain `BOND_LOCK` for `aitbc-miner-1` (3 AIT).
  - Forced `RUNNING` job + stale heartbeat after stopping the miner.
  - `BondSlashSweeper` triggered `BondSlashingService.slash()` and produced an on-chain `BOND_SLASH` tx in block 2728.
- Discovered and fixed a nonce-reuse bug when multiple `BOND_SLASH` transactions are submitted before the next block is mined:
  - `BondSlashingService._get_nonce` now uses a module-level `_slash_nonce` counter protected by `asyncio.Lock`.
  - Fix committed/pushed as `15d41decc` on gitea `main`, pulled to `hub.aitbc`, and `aitbc-coordinator-api` restarted.
- `node1` (`aitbc1`, `10.1.223.40`) brought back online: confirmed follower mode, replaced the locally-ahead `chain.db` with a hub snapshot, fast-forwarded to gitea `main` (`15d41decc`), and synced to matching head height. Updated OS hostname from `aitbc1` to `node1` / `node1.aitbc.bubuit.net` and set `NODE_ID=node1`. All four nodes now converge.

## 2026-09-02 (continued) — PBFT mesh fault-tolerance, state-root corruption, and recovery

- Rolled multi-peer `MeshGossipBackend` and PBFT mesh configuration to all four validators.
- Fault-tolerance test: stopped `hub.aitbc` for ~4 minutes.
  - `aitbc3`, `hub2.aitbc`, and `node1` produced one block (2846) while hub was down, then stalled.
  - After hub restart, all four nodes converged to height 2846, but the computed account state root (`0xe00873c3...`) diverged from the block header (`0xa7a8f15d...`).
- Diagnosis: a failed PBFT proposal on the hub applied two GPU marketplace transactions, then called `session.rollback()`, but the new `Transaction` rows and account updates created inside `begin_nested()` savepoints were not fully rolled back. This produced orphan `block_height=2847` transactions and a corrupt account state, which then propagated to followers.
- Recovery (option 2):
  - Reconstructed a consistent database from `node1`'s `chain.db.bak-20260902-node1-ahead` (head 2795) by replaying blocks 2796–2846 using `ChainSync.import_block`.
  - The replay produced the canonical block 2846 state root `0xa7a8f15d...` and the correct `0xd3d...` account state (balance `3193561404`, nonce `24`).
  - Preserved each live database as `chain.db.corrupt.20260902-1145`.
  - Replaced `chain.db` on all four validators with the reconstructed snapshot.
  - Restarted services hub-first; all four converged at height 2848 with matching state roots.
- Fix for failed-proposal rollback bug:
  - In `poa.py`, removed per-transaction `begin_nested()` savepoints and the `session.add()` of new `Transaction` records from within them.
  - New/updated `Transaction` records are now collected in `pending_transaction_records` and `session.add()`-ed only after all state transitions for the block succeed.
  - Governance-payload and duplicate checks now happen before `apply_transaction` so a skipped tx cannot leave account mutations.
  - On exception, the session is rolled back and the block is aborted.
  - Committed/pushed as `3acefcda7` on gitea `main`; pulled and restarted on all four nodes.
- Post-fix validation:
  - All four validators converge at height 2860 with identical head hash and state root.
  - Re-ran the hub-down test: no state-root corruption and no orphan `Transaction` rows, and the hub catches up cleanly after restart.
  - The network still stalls after one block while `hub.aitbc` is offline because PBFT view-change does not currently rotate to an available proposer. This is the remaining liveness issue.

## 2026-09-02 (continued) — full-window validator outage and PBFT round takeover

- Full 14-minute outage of `hub.aitbc` (`13:31:28` to `13:45:31`) with the new round-takeover code deployed.
- The chain did not freeze:
  - Block 2910 committed with hub offline: first live 3-of-3 quorum on a 3-validator set (`required=3, prepares=3, commits=3`).
  - Block 2911 (`key 2911:1`) was hub's slot; node1 claimed it at round 1 after the 300 s round flip, and block 2915 repeated the takeover.
  - All four nodes converged at height 2922 with identical hash `0xe898e16f8611` and state root `0x450ecee8b8ef`; hub resynced and proposed its own slot (2919).
- Round-takeover warning log appeared exactly twice (`Height 2911` and `Height 2915 has gone 1 round(s) without a block`); zero false-positive out-of-turn rejections.
- `hub2.aitbc` `MAX_EMPTY_BLOCK_INTERVAL` misconfiguration (180 s) was fixed to 60 s; normal ~71 s cadence restored across all validators.
- Remaining unproven edge (same as before): a proposer dies after collecting `prepare` messages but before `commit` (needs NEW-VIEW with prepared certificates). Host-level outage where RPC/gossip also fails is still untested.

## 2026-09-02 (continued) — rolling restart and nginx worker-connections fix

- Rolling restart of all four `aitbc-blockchain-node` services, one validator at a time, while the chain continued producing.
- Heights advanced throughout the restarts: 2981 → 2982 (hub) → 2983 (hub2) → 2984 (aitbc3) → 2985 (node1). Each node was confirmed rejoined and the mesh advanced past the previous head before the next restart.
- Confirms the round-takeover fix works under real validator churn with 3-of-4 quorum.
- nginx `worker_connections` / IPv6 fix verified: zero new `Connection refused` or `no live upstreams` errors on all four hosts during the restarts, down from 39–73 errors per minute earlier in the day. aitbc3 added no error-log lines after the IPv6 change.
- Live workers at the new `8192` limit: hub 2/2, hub2 2/2, aitbc3 32/32, node1 8/8 with one stale worker on node1 from 31 Aug held by `aitbc-agent`/`aitbc-loadbalancer` (not the validator mesh).
- Final: all four active at height **2985**, hash `0x5b149ea4bec67b6e`, state root `0x450ecee8b8efafed`, identical across the mesh.

## 2026-09-02 (continued) — node rename and second rolling restart

- `aitbc3` renamed to `node2.aitbc.bubuit.net` with public DNS and at1 nginx config; `GOSSIP_MESH_PEER_URLS` and `DEFAULT_PEER_RPC_URL` updated across the four validators.
- `node0.aitbc.bubuit.net` public DNS and nginx config also enabled; `GOSSIP_MESH_PEER_URLS` on the four validators updated to include it.
- Second rolling restart (node0 → node2 → hub → hub2 → node1) completed. All four validators converged at height **3043** and continued advancing.
- `node0` `aitbc-blockchain-node` was on older commit `33a0f8a28` (pre-mesh backend), so `GOSSIP_BACKEND=mesh` crashed. It was then pulled to current `main` (`cb8cfbf25`), its `chain.db` was backed up and reset, and `GOSSIP_BACKEND=mesh` restored. `node0` resynced from genesis to the network head and now advances with the mesh.
- `node0` nginx was also fixed: `server_name` set to `node0.aitbc.bubuit.net`, `/rpc/` `proxy_pass` port corrected from `8006` to `8202`, and WebSocket upgrade headers added so that `wss://node0.aitbc.bubuit.net/rpc/gossip/ws` now returns `101 Switching Protocols` and peer gossip can establish.
- `gossip/broker.py` was refactored into a `gossip/backends/` package (base, in_memory, broadcast, websocket, mesh) plus `gossip/_internal.py` and a thin `broker.py`. Rolling `git pull` + restart across all five live nodes loaded the new package without stalling the chain.
- Open Arcs live validation was mirrored into canonical `docs/releases/STATUS.md` and pushed to Gitea (`42febfdda9`), then pulled onto all five live nodes.
- No `broker.py` stash exists on `node2`; unrelated stashes remain. Older `chain.db.pre*` backups were deleted, keeping the newest backup per data directory; live nodes were also pulled to the updated `main`.

## 2026-09-03 — PBFT view-change liveness fix and host-level hub outage

- Deployed `d3861a2eb` (`fix(consensus): let a later round supersede one that produced no block`) to all four validators, restarting both services on all four together because the per-round prepare rule changes which proposals a node accepts.
- Three defects closed: the per-height block-hash pin that spanned every round and froze a height until restart; a view-change timer armed only by the proposer, which nothing read and which the dead node was never running; and `consensus_proposer_round_seconds`, now derived as `max(120, 2 * max_empty_block_interval)` = 120 s live, down from a hardcoded 300 s against a 60 s heartbeat.
- Host-level outage test (`08:57:03`-`09:06:42` UTC, 9 min 39 s) with **both** `aitbc-blockchain-node` and `aitbc-blockchain-rpc` stopped on `hub.aitbc` — the case left untested on 2026-09-02, where hub's RPC stayed up.
  - Both heights hub owned at round 0 (4051, 4055) were taken over by node1 at round 1 after 122 s. Every other height held 60-72 s; the chain never went more than 122 s without a block.
  - Quorum held at exactly 3 of 3 survivors throughout. Zero `refusing a second block` warnings and zero commit-quorum timeouts.
  - Hub rejoined without intervention and proposed its own slot at 4059. All four converged at height **4059**, hash `0xb0b1996e07119c51`, state root `0x50e75efff2f03fb4`.
- Scope: the faster rotation and full-surface outage are proven live; the permanent-pin fix is proven only in unit tests, because both live outages stopped hub cleanly between blocks with no pre-prepare outstanding. Rotation still supersedes a round rather than running a NEW-VIEW exchange with prepared certificates, and with one validator down quorum is 3 of 3 with no slack.

## 2026-09-03 (evening) — open-issue megaplan resolved

See full notes in [LIVE_VALIDATION_DAYS/2026-09-03.md](LIVE_VALIDATION_DAYS/2026-09-03.md).

- `StaleJobReaper` dry-run mode added and deployed on `hub.aitbc`; the reaper had already
  expired the two stuck `RUNNING` jobs and `StuckEscrowSweeper` refunded their escrow.
- `StuckEscrowSweeper` dry-run mode added for safe refund validation.
- `BondSlashingService` now enforces a `BOND_SLASH_DOWNTIME_COOLDOWN_SECONDS` window,
  preventing a bond from being repeatedly slashed for one continuous downtime incident.
- `node2` fork at height 4373 root-caused as a block produced by an unconfigured proposer
  (`0x19e7e376...`) rather than the hub's scheduled proposer; node2 resynced from a hub
  snapshot and converged at the fleet head (height 4496, same hash as hub).
- New `scripts/ops/reset-follower-to-snapshot.sh` provides a safe follower recovery path
  that avoids the broken full-genesis replay on this chain.
- **2026-09-03 (evening) — fleet-wide hard fork:** the live chain was replaced by a clean fork
  genesis built from the `hub.aitbc` head, preserving all 20 accounts and total balance
  `36071999920573440`. All five nodes converged at height 2 with hash
  `0xa7e99d6a722a4a6355dadedb12c19e5e3b31accdd3041d03f61114e92138ab4a`.
  `STATE_TRANSITION_V2_HEIGHT=0` is set fleet-wide; `reset-follower-to-genesis.sh` is viable
  for the new fork.

## 2026-09-03 (later) — open-issue resolution run

See full notes in [LIVE_VALIDATION_DAYS/2026-09-03.md](LIVE_VALIDATION_DAYS/2026-09-03.md).

- `MultiValidatorPoA.validate_block` wired into the import path; receiver-side schedule enforcement now runs for known proposers.
- `aitbc-blockchain-rpc` `SIGTERM` handling fixed at the code level; `systemctl stop` exits in ~15 s on `node2`, `hub2.aitbc`, and `node0`.
- `MULTI_VALIDATOR_MIN_ATTESTATIONS=2` quorum clamped to active non-proposer count; PBFT `required_messages` is recalculated each phase.
- Single-peer bulk-sync contamination mitigated: an imported block must extend the current local head.
- `--wallet <name>` now searches configured + service wallet directories in `gpu_resources`, `auth`, `agent`, `operations`, `bridge`, and `wallet_loader`.
- `node2` `github` remote verified fetch-only (`github no_push`) and `stash@{0}` dropped after confirming its contents were already in `main`.
- Orphaned escrow IDs `43adc25374cd999c` and `1e10b73ff1076eb1` not found on live nodes or backups; documented as unresolved pending an older backup.
- Root `tests/` triaged: 126 pre-existing CLI/import/security failures, no regressions from these changes.

## 2026-09-07 — CI green, redacted MCP bridge-status tool, node1 outage recovery, bridge round-trip

See full notes in [LIVE_VALIDATION_DAYS/2026-09-07.md](LIVE_VALIDATION_DAYS/2026-09-07.md).

- Gitea CI run 19639 on `b62637a792` passed all gates (lint, C901 ratchet, typecheck, unit/app/CLI/governance tests, OpenAPI drift, version check, live dry-run).
- Redacted MCP bridge-status tool added; `rpc_url` and credential-bearing fields are dropped while readiness and deposit constraints remain.
- **Bridge (A-2) end-to-end closed 7 Sep:** `0.001` Sepolia ETH deposited from hub `test-bridge-deposit` wallet to node2 bridge address; `2.49425` AIT minted to `0x3Ed42960a36489Fe1BA39ceCcbbd6F87C8551Ebf` in AIT block **4640**. Bridge config (`BRIDGE_ENABLED`, `GENESIS_WALLET_ADDRESS`, `ETH_RPC_URL`, `BLOCKCHAIN_RPC_URL`) corrected on `node2`. Redacted MCP `get_eth_bridge_status_redacted` tool deployed and verified to omit `rpc_url`; the wallet's raw `GET /v1/bridge/status` endpoint still returns `rpc_url`.
- **S-3/R1 closed 8 Sep (`6651dc3b1` + `c79462f3e`):** client `Constraints` no longer accepts server-only spot-check fields; `JobService.create_job` strips them; `SpotCheckService` stores the authoritative record on the shadow job only; `get_dispute_evidence` verifies the shadow job and binding. Regression test proves client-forged evidence is ignored. `aitbc-coordinator-api` on `hub.aitbc` restarted to `c79462f3e`; live `/openapi.json` confirms `Constraints` has no `shadow_mode`; `journalctl` clean. Gitea CI run 19643 green. Live dispute end-to-end exercise still pending.
- Operator-approved node1 `aitbc-blockchain-node` outage: 3-of-4 validators produced blocks 4619–4621 while node1 was down; node1 rejoined and converged at height 4621 within ~2 minutes.
- Bridge (A-2) preflight on node2: wallet `/v1/bridge/status` reachable, `price`/`estimate` work, but `enabled: false`; no live ETH→AIT round-trip performed.
- **node0 block lag resolved 8 Sep:** `default_peer_rpc_url` pointed to `node1` (follower) instead of `hub`. Corrected in `/etc/aitbc/blockchain.env` to `https://hub.aitbc.bubuit.net`, stale `SYNC_SOURCE_*` removed, `BLOCK_TIME=5` replaced with `BLOCK_TIME_SECONDS=60`, `market_role` set to `customer`; `aitbc-blockchain-node` + `aitbc-blockchain-rpc` restarted. node0 caught up and is now at fleet height.
- **B-8 closed in code 8 Sep (`3d09e8105`):** `001_initial_migration` and the B-8 schema-conformance test now import `coordinator_api.models.multitenant`, so a fresh `alembic upgrade head` creates all declared tables. `make test-apps` includes `apps/coordinator-api/tests/integration`; Gitea CI run **19643** on `c79462f3e` green. mypy baseline fixed in `c79462f3e` with per-file `warn_unused_ignores=False` for the optional `torch` modules. Historical-schema upgrade regression remains a follow-up.
- **S-4 closed in code 8 Sep (`d119e8ca9`):** v3 activation rule, per-escrow beneficiary/signer validation, v2→v3 cross-activation handling, and regression tests added. Proposer stamps `state_transition_version` from `get_block_version_for_height`. `make lint-strict/typecheck/no-float-money/test-apps` passed; Gitea CI **19645** green. `pure_state_transition` parallel path and live activation height remain follow-ups.
- **F-5f closed in code 8 Sep (`8cb48178d`):** added `EscrowService` Solidity test suite (23 tests) and `MockEnergyPricing`; fixed `EscrowService.createEscrow` `releaseTime` persistence bug. `npx hardhat test` passes 182 tests; Gitea CI **19646** green. Other Solidity contracts remain as potential follow-up.
- **D-2 re-derived 8 Sep:** `761b887837` is on `origin/feat/open-island-gossip-remediation`, but `252469f3b` on `main` has the same tree and the two follow-up fixes are on `main`; relevant tests pass. Branch still carries unmerged CLI escrow-guard and CI contract-suite commits.
- **O-3 closed 8 Sep:** `SYNC_REDIS_URL` password rotated and hub Redis `requirepass` updated; `REDISCLI_AUTH`/`REDIS_URL`/`GOSSIP_BROADCAST_URL` on `hub.aitbc` and `SYNC_REDIS_URL` fleet-wide updated; `redis-server` and AITBC services restarted; verified by Redis `PING` and `fleet-config-check.sh` exit 0.
- **CI red-streak audited 8 Sep:** 39 consecutive Gitea Actions failures (19600–19638) before 19639 green; 19642 (`3d09e81054`) failed, 19643 (`c79462f3e`) green. **Correction (late-8-Sep re-verify):** 162 failed runs, 19477–19638 (~70 h) — earlier counts were API page-size artifacts.

## 2026-09-08 (continued) — O-1 / R8 closed by operator confirmation

See full notes in [LIVE_VALIDATION_DAYS/2026-09-08.md](LIVE_VALIDATION_DAYS/2026-09-08.md).

- **O-1 / R8 closed 8 Sep:** the operator confirmed node2's GitHub PAT is revoked at github.com/settings/tokens. Recorded as dated operator attestation only — the token was not requested, read, copied, or tested. Local cache clearance on node2 had been recorded 7 Sep; this closes the provider-side confirmation.
- **R10 manifest refreshed 8 Sep (read-only):** all five hosts at gitea tip `7d93b678a` (CI 19655 green), converged at height 5268, zero failed `aitbc-*` units; coordinator `alembic_version = f53990f9d6cc` at `/var/lib/aitbc/data/coordinator.db` on hub; daily `/var/backups/aitbc` snapshots present on all hosts. node2 R7 files committed/pushed, release log reconciled to current open-task state. Per-pull approval log not established (not manufactured); service-level networked rejoin/restore test completed post-close on `node0`.
- **TASKLIST reconciled 8 Sep (operator-approved):** the stale "3 open / 0 operator-only / 7 lanes" header is replaced by an explicit-ID count (58 IDs; 56 closed, 1 open = C-1/R7, 1 operator-blocked = O-3). Item texts corrected or annotated: O-1, O-3, A-2, C-1, S-3, S-4, B-8, F-1, A-1, D-2, and the source-artifact availability note.
- **ENERGY_OPERATOR_ADDRESS resolved on hub 8 Sep:** dedicated operator pair generated on `hub.aitbc`, written to `aitbc-coordinator-api.env` (key never in transcript); `ENERGY_OPERATOR_ADDRESS = 0xD8ca07D43584509b715e2Be475a635D793f03E4d`. Coordinator restarted, health 200. Energy quotes now sign and verify instead of 503. Same pair deployed to node2's coordinator (one fleet-wide identity); chain-side `escrow_routes` gate armed hub-only.
- **BOND_SLASH_AUTHORITY_ADDRESS split fixed 8 Sep (config-only):** the shared key was derived on-host — it controls `0xab07…1d76`, the only working authority; `0xe738…d225` had no matching key. Operator chose config fix over rotation (exposure = accepted risk). Canonical address now set on all 5 hosts (node0 added, node1 + hub corrected); rolling restarts done, fleet converged at 5265. Old key copies in `/etc/aitbc/*.bak*` and `/var/backups/aitbc/` archives were purged post-close under operator approval.
- **Bond-slash divergence proven + fix shipped 8 Sep (`5c79eebe3`):** old-chain snapshots prove node0 skipped the five 1–2 Sep slashes (txs in its blocks, bonds left `active`) — silent state divergence on a chain since rebuilt. `_bond_slash_authority` now prefers the on-chain `bond_slash_authority` chain parameter over per-node env; skipped effects log their reason; genesis can seed `parameters`; `fleet-config-check.sh` diffs consensus env vars across hosts. **Parameter pinned on-chain in block 5336** (`bond_slash_authority=0xab07…1d76` on all five hosts' chain state; ghost `0xfe2d…` identified as the genesis address). Side finding: REST tx submission never gossips txs — they only reach the submitting host's local mempool (worked around via direct mempool-DB insert on proposers).
- **O-3 closed 8 Sep:** `redis.env` is needed — it supplies `REDISCLI_AUTH` to `aitbc-cache-monitor.service`, which had never been installed. Correction: redis-server runs on **all five** hosts (gossip backend); auth only on hub + node2, where `redis.env` lives. Monitor + timer installed fleet-wide; first runs healthy. Durability fix in `7d93b678a`: the role-aware relink used to delete hand-installed units — `aitbc-cache-monitor` is now gated on redis-server presence, `setup.sh` creates `redis.env` on Redis hosts and enables the timer. With C-1/R7's same-day code fix (`7ccdabf9b`), the register is fully closed: all 58 IDs have a dated disposition.
- **R7 — watchdog phase diagnosis closed 8 Sep:** `PoAProposer._propose_phase` now tracks the active proposal phase, the watchdog ERROR and a per-phase metric include the phase, and `test_proposer_watchdog.py` verifies stalled-phase scenarios at `LOG_LEVEL=INFO`; Gitea CI **19652** green on `7ccdabf9b`.
- **F1/F2 closed + register finalised 8 Sep (`aef0b5099`):** `fleet-config-check.sh` now pulls chain-head convergence over each node's `/rpc/status`, so it runs from any fleet host without ssh; `BOND_BURN_ADDRESS` is set and uniform fleet-wide. §14 acceptance re-asserted at `aef0b5099` with Gitea CI **19673** green. The register is fully closed; the only R10 residual is the per-pull approval log (recorded, not manufactured). Operator-lane credentials/identity hygiene and the service-level networked rejoin/restore test on `node0` (live hub snapshot, rejoined at 5581 / `0xfab1122fe72f11`, `fleet-config-check.sh` exit 0) were completed post-close under explicit operator approval.
- **Post-close active outage closed 8 Sep 23:28:** after the §17.14 rotation, the chain halted at 5581. Two causes found: (1) missing colon in `redis://PASSWORD@host` URLs, and (2) `blockchain.env` forcing `GOSSIP_BACKEND=websocket` to a self-referencing `wss://hub.aitbc.bubuit.net:443` on the hub. Both fixed; fleet switched to `GOSSIP_BACKEND=mesh` with `wss://<peer>/rpc/gossip/ws`. Redis password exposed during debugging was rotated again. `fleet-config-check.sh` now requires a 60s height increase; verified 5591 → 5592.
- **F3/F4/F5 remediation 9 Sep:** `GOSSIP_MESH_PEER_URLS` override in `node.env` removed on all five hosts, restoring full mesh. Local Redis on every host re-secured with `bind 127.0.0.1`, `protected-mode yes`, `requirepass`, and local consumer URLs authenticated; `redis.env` created for `aitbc-cache-monitor`. World-readable credential files `chmod 640` + `chgrp aitbc`; stale `BLOCKCHAIN_API_KEY` removed from hub2; local Postgres user passwords and `MINER_*` tokens rotated; `GENESIS_WALLET_PRIVATE_KEY` removed from `node0`/`node1`/`hub2` (no `GENESIS_WALLET_ADDRESS` there). New genesis wallet created and full spendable balance transferred on-chain to `0x5A1a52b85B687Af457C406E8d22562F9Efa86c3A`; new key/address written to `node.env` and `blockchain.env` on `node2` and `hub`; `aitbc-wallet` and `aitbc-bridge-monitor` reloaded. `BLOCKCHAIN_RPC_API_KEY` and all Redis `requirepass` values were re-rotated after debug exposure and services reloaded. `fleet-config-check.sh` sample interval raised to 90s and live nodes updated; verification 6031 → 6032, 6073 → 6074, and 6082 → 6083.
