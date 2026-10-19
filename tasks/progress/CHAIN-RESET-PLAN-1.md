# CHAIN-RESET-PLAN-1 — progress ledger (append only)

## 2026-10-18 — preflight reads (coder session autumn-buffalo; read-only, nothing changed)

Baseline: `origin/main` = `465f39eeb`. All reads were `mode=ro` sqlite handles, `systemctl`/`ss`/`grep`/`journalctl` queries, or repo reads on the IDE clone `/opt/aitbc`. No writes to any host, no chain writes, no key material read. Timestamps: IDE 2026-10-18 21:43 UTC = hub 23:43 CEST.

Read-method note (director-corrected): `mode=ro` on a live WAL DB never writes DB or WAL contents (the `-shm` touch is harmless shared-memory bookkeeping and does not block sealing). `immutable=1` on a live DB is unsafe — it skips locking and can return stale/inconsistent results; it is only valid on frozen files. For stricter separation or heavy analysis (e.g. a replay rehearsal), the pattern is `sqlite3 <db> ".backup <dest>"` — a consistent snapshot via SQLite's own backup API — then read the copy.

### Era × tx-type matrix (hub chain.db, group-by block_height)

| era (heights) | txs | notable for gates |
|---|---|---|
| <11k | 161 | all pre-v4; 63 ESCROW_LOCK, 30 GPU_MARKETPLACE, 27 TRANSFER |
| 11k–24k | 24 | v4 evidenced (3 STAKE_RELEASE) |
| 24k–24.65k | 5 | thin — GPU_MARKET only |
| 24.8k–30.4k | 66 | v7 evidenced (23 TRANSFER) |
| 30.4k–32.1k | 16 | v9 evidenced (escrows + 4 GOV_EXEC) |
| 32.1k–35.4k | 31 | v10 evidenced (1 GPU_DEREGISTER) |
| 35.4k–37.5k | 34 | v11 evidenced (4 ESCROW_FEE_SWEEP) |
| 37.5k–46.1k | 19 | v12 evidenced (6 GOV_EXEC) |
| 46.1k–51k | 34 | **v13 NOT evidenced** — zero GOVERNANCE_EXECUTE ≥46100 |
| ≥51k | 12 | leaf-v2 evidenced (2 BRIDGE_LOCK) |

v2/v3/v6 heights = 0 → never-taken branches. v14 evidenced by every post-46100 block's headers.

### State at the cut

- Locked escrows (6, all buyer `0x08aB…`, all 2026-09-10): edge-test-002 36,000; ipfs_rental 36,000,000; sw_job_…09b8 60,912; sw_job_…d9b8 25,056; sw_job_…364d9 18,000; sw_job_…207d… 60,500. Total **36,200,468 units ≈ 1.006 AIT**.
- Orphans (6, `void`/`no sealed lock leg`, separate table): orphan `5f6ebf5f…` holds `lock_tx_hash 0x34fad479…` — **absent from `transaction` table and from `mempool` (mempool has 0 rows)** → write-off candidate, no sealed lock.
- cross_chain_transfer: 4 confirmed + 3 refunded, none pending.
- governance_proposal: `gap57-aux-sync-test` = `active` (only open proposal).
- stake: 1 active (4,387,500 units, `0x4A5b…`); gpu_allocation: 1 active (`node0-rtx4060ti`).
- `agent_coin_requests.db`: **1 PENDING** — `req-hub2.aitbc.bubuit.net-94Bb6b87-…`, 3,600,000,000 units (100 AIT).
- `hermes_coin_requests.db`: 22 rows; 13 APPROVED split **4 SEALED** (the four 100-AIT per-host faucet grants: `req-hub2…`, `req-node0…`, `req-node1…`, `req-node2…`) + **9 UNSEALED** test requests totalling 1,610 units ≈ 0.00004 AIT (dust). 5 of the 9 store a `signed_transaction` envelope, but the `from` account `0xdb5247d03c…` **does not exist in `account`** — the envelopes cannot seal. 3 of the 5 also bind `chain_id` in the signed body. Voiding is a service-DB status change (optional hygiene; DB archived at cut under D5), not a chain write.
- `bridge_deposits.db`: 1 failed deposit; `bridge_outbound` 5 rows.

### Service stores (names + sizes only)

Custody-bearing: `keystore.db` (all 5 hosts), `admin_nonces.db` (all 5), `peer_keys.db` (hub/hub1/node2), `wallet_ledger.db`, `wallet_operations.db`, `ops-signer-ledger.db` (hub only).
Service DBs per host (SQLite under `/var/lib/aitbc/data`): coordinator.db (largest, hub 8.6 MB), marketplace_service.db, trading_service.db, governance_service.db, agent_management.db, bridge_deposits.db, exchange/exchange.db, *_coin_requests.db, gpu_service.db (hub1/node0/node2), aitbc_edge.db (node0/node2), agent_coordinator.db, *_operations.db.
Extras: node2 has `chain-backup-2026-08-22.db` (10 MB) + `pre-migrate-20260816` (4 MB); hub chain dir holds historical backups (`chain.db.bak.*`, `chain.pre-snapshot.*`, `genesis.json.pre-reset.20260903`). node0 extra dirs: openclaw, registry, marketplace, blockchain-event-bridge.
Hub PostgreSQL: 9 DBs (`aitbc_*`×8 + `postgres`); services still write SQLite.

### Capacity (dress rehearsal input)

| host | cpu | mem | disk free |
|---|---|---|---|
| hub | 4 | 3GB (1 avail) | 370 GB |
| hub1 | 2 | 3GB (2 avail) | 13 GB |
| node0 | 8 | 24GB (22 avail) | ~8.1 TB |
| node1 | 8 | 16GB (14 avail) | ~8.1 TB |
| node2 | 32 | 24GB (14 avail) | ~8.1 TB |
| IDE | 32 | 62GB (26 avail) | ~7.8 TB |

No spare 5-host set exists; a multi-host twin would have to be containers/VMs on node2 or the IDE host (both have headroom; hub/hub1 are small).

### Validator-set interactions (per-host env names)

`VALIDATOR_SET`, `VALIDATOR_KEYS`, `PROPOSER_ID`, `PROPOSER_KEY`, `P2P_NODE_ID`, `MULTI_VALIDATOR_{CONSENSUS_ENABLED,MIN_ATTESTATIONS,ATTESTATION_TIMEOUT_SECONDS}`, `BRIDGE_MULTISIG_VALIDATORS`, `BRIDGE_VALIDATOR_ADDRESS_*`, `BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_*`, `BRIDGE_ADMIN_PRIVATE_KEY_SOURCE`. hub-only: `GOVERNANCE_PROPOSER_PRIVATE_KEY`, `CHAIN_SYNC_SOURCES`. node0-only: `HUB_PROPOSER_ID`, `trusted_proposers`. Stores: `peer_keys.db`, `bridge_validators` (10 rows), signer ledgers.

### Chain-id surface (D1)

All 5 hosts set `CHAIN_ID=ait-hub.aitbc.bubuit.net`. Consumers: `website/config.js:13`, `dashboard.js:17`; `aitbc_rules_test.yml` + `aitbc_rules.yml` alert text; `render-website.sh`; ops scripts (`replay-chain.py`, `gpu-registry-sweep.py`, `post_activation_audit.py`, `first-sweep-check.py`, `aitbc-backup.sh`); data dir `/var/lib/aitbc/data/<chain_id>/`; gossip topic `transactions.{chain_id}`; docs+tests. No charset validation — new id must stay `[a-z0-9.-]`-safe (dir name, DB path, topic suffix, metric label, URL).

### Tooling (W4)

- `aitbc genesis reset` → `genesis_reset.py:199-218` (director-verified): rewrites `PROPOSER_ID`/`PROPOSER_KEY` in 4 env files, writes single-proposer `VALIDATOR_SET`, writes genesis private key into env files — unsafe on any validator host. `RESET-TOOL-GUARD-1` covers.
- `create-genesis-block.py`: treasury-only, writes raw key to `node.env`+`wallets/genesis.json`, `--update-env` rewires `PROPOSER_ID`→treasury (wrong under PBFT). Coder-read, not director-verified.
- `reset_chain_0x.py`: 1B treasury + 1M/wallet + 1M/service-account allocations, seeds DB directly; mints service keys to `service_accounts.json` (0600); single-hub, no validator set.
- `reset-follower-to-genesis.sh`: working snapshot installer (WAL-aware `.backup`, `.pre-reset` preserved); stale bit: appends `STATE_TRANSITION_V2_HEIGHT=0`.
- `verify-genesis-root.py`, `reset-follower-to-snapshot.sh` also exist (not yet read end to end).

### Old-height consumers (W6)

`aitbc_rules.yml` `ChainHeadStalled` (gauge-based, no fixed height — survives reset), v9 shadow tripwires (obsolete after collapse), comments embedding heights (35400 etc.); `bridge-leaf-audit.py --v2-height`; `attestation-arrival-textfile.py` (reads max height — resets to 0 naturally); explorer/website charts + "Anchored" labels; docs (`unit-system.md` reset section); register/ledger history stays as history.

### Not yet covered by this pass

Coordinator service DB internals (open jobs table names seen but not enumerated), `verify-genesis-root.py`/`reset-follower-to-snapshot.sh` full reads, MCP genesis tools, GPU_MARKETPLACE intake-refusal surface detail, per-table schema walk of custody stores (by design — names only).

Nothing was changed on any host, in the repo, or on the chain.

## 2026-10-19 — Phase 0 inventory, second pass (read-only; nothing changed on any host)

Same baseline `465f39eeb`. Filled the gaps left by the 18 Oct pass: per-gate branch map, full legacy-site lists, coordinator/bridge-ledger states, allocation inputs, remaining tooling, and the item-11 co-existence answer. Hub reads ~09:xx UTC (`mode=ro` handles and repo greps only). **All findings below are coder-reported until director-verified.**

### Item 1 — per-gate branch map and evidence class

Version semantics are cumulative: a block at version ≥N runs every rule ≤N. `block_version` derives from height (v8+ ignores the metadata stamp — `state_transition.py:909-935`). Sources: `config.py:765-890` (heights), guarded branches below.

| gate | height | guarded branch (file:line) | behavior | live evidence |
|---|---|---|---|---|
| v2 | 0 | `state_transition.py:1602,1978` (`lock_version=2 if <3 else 3`), `escrow_routes.py:636`, `escrow_settlement_sweeper.py:37` | escrow lock format v2 | superseded — never the tip rule |
| v3 | 0 (never armed) | same lock_version branches; `escrow_routes.py:617-641` refuses v2-era locks | escrow lock format v3 | no evidence (whole chain pre-v3-era? **correction: v3=0 means never activated** — `config.py:771`) |
| v4 | 11000 | `agent_staking.py:250`, `staking.py:259` | stake-release gating | evidenced (3 STAKE_RELEASE 11–24k) |
| v5 | 24000 | `state_transition.py:1378-1386` via `bridge_credit.py` | bridge credit `bridge_signature` required | weak — 5 txs in 24–24.65k window; exercised continuously thereafter |
| v6 | 0 (never armed) | refund-lock binding for BRIDGE_RELEASE/REFUND (`v9_policy.py` docstring) | refund↔lock binding | no evidence |
| v7 | 24650 | `state_transition.py:1010-1030` (envelope nonce authoritative for signed txs), `:1726` (GPU_REGISTER `registered_by` ownership gate) | nonce + GPU ownership | **0 txs inside 24650–24800 window**, but evidenced cumulatively: every signed tx ≥24800 ran the nonce rule; 5 GPU_REGISTERs ≥24650 hit the ownership gate |
| v8 | 24800 | `state_transition.py:909-935` | height-derived version beats metadata stamp | structural — every block ≥24800 |
| v9 | 30400 | `v9_policy.py` (`V9_UNSIGNED_ALLOWED_TX_TYPES`, `v9_signature_verdict`), `remote_attestation.py:359-373` | sender signature at apply | evidenced (66 txs 24.8–30.4k incl. escrows/gov) |
| v10 | 32100 | `rpc/transactions.py:216`, `state_transition.py:2102` | GPU_DEREGISTER admitted | evidenced (1 GPU_DEREGISTER in window) |
| v11 | 35400 | `rpc/transactions.py:206`, `state_transition.py:2017`, `escrow_routes.py:921` | ESCROW_FEE_SWEEP + per-job custody | evidenced (4 sweeps in window) |
| v12 | 37500 | `state_transition.py:618-645` (`_authority_parameter_change_error`) | GOVERNANCE_EXECUTE authority-parameter value check | evidenced (6 GOV_EXEC in window) |
| v13 | 46100 | `state_transition.py:578-615` (`_governance_binding_verdict` via v13 shadow path), `v13_policy.py` | governance-binding rules on PROPOSE/EXECUTE | **no live evidence — 0 GOV txs ≥46100**; synthetic vectors required |
| v14 | 46100 | `side_root_shadow.py` (committed_fingerprint → `aux_state_root` in block hash, recomputed by `sync_block_import`) | aux state root in header | structural — every block ≥46100 |
| leaf-v2 | 51000 | `consensus/poa.py::_compute_bridge_state_root`, `bridge-leaf-audit.py` | bridge leaf gains `:<recipient>` | evidenced (2 BRIDGE_LOCKs ≥51k) |
| fee-sweep-min | 35400 | `config.py:208` `escrow_fee_sweep_pass_min_height` | sweep eligibility floor | with v11 |

Shadow computations (`side_root_shadow`, `bridge_root_shadow_check` `config.py:701,718-725`): node-local, never consensus; `side_root_shadow` wrote ~7,700 rows on hub. Deletion candidates under W2b, not migration items.

**Tx-type disposition** (dispatch in `state_transition.py:1784+`; `_tx_type` upper-cases, falls back to `payload.type` then `TRANSFER`; `_ZERO_VALUE_TX_TYPES` `state_transition.py:85` = MESSAGE, GOVERNANCE_EXECUTE, GPU_REGISTER, GPU_ALLOCATE, GPU_MARKET + GPU_DEREGISTER at v10):

- Explicit apply branches (27): BOND_LOCK/RELEASE/SLASH, BOUNTY_LOCK/PAYOUT/REFUND, BRIDGE_LOCK/RELEASE/REFUND/WITHDRAW, ESCROW_LOCK/RELEASE/REFUND/FEE_SWEEP, GOVERNANCE_EXECUTE/PROPOSE/VOTE(v9 allowlist + admission_authority:68 + poa.py:129,165), GPU_REGISTER/ALLOCATE/DEREGISTER, IPFS_SUBSCRIPTION, LIQUIDITY_DEPOSIT/CLAIM/WITHDRAW, RECEIPT_CLAIM, STAKE_LOCK/RELEASE.
- Generic debit/credit path (no own branch): TRANSFER, MESSAGE, EXCHANGE, **GPU_MARKETPLACE** (this is why old blocks replay today), GPU_MARKET.
- On-chain observed: 21 types. Never on-chain but with apply code: BOND_*, BOUNTY_*, LIQUIDITY_*, RECEIPT_CLAIM.
- **Surviving post-reset**: all of the above except `GPU_MARKETPLACE` (historical-only, `MARKET-TYPE-RESET-1`). `EXCHANGE` observed ×3 — keep on the survive list pending plan word (generic path, no dedicated branch). Unexercised types keep their apply code; their evidence class is "synthetic vectors or none".

### Item 2 — history-gated legacy sites

- **`ait-mainnet` fallback** (node src, `465f39eeb`): 8 resolution sites `or "ait-mainnet"` — `app.py:262,273`; `database.py:124,247,601,644`; `rpc/utils.py:254,447`. Plus 3 equality/flag uses — `database.py:131,602,652` (SQLCipher `==` gates + encryption flag) and `config.py:73` comment. Plus non-runtime defaults in genesis tooling: `create_bootstrap_genesis.py:10`, `unified_genesis.py:13,48,255,261`, `setup_production.py:93`, `layerzero.py:27,34` comment. All history-gated (W2b).
- **`GPU_MARKETPLACE` reads**: `analytics.py:91,153,168` (color + two SQL `IN` lists); `market_service.py:709,776` (offer-anchor compat read); `website/explorer.js:30` (chart legend); tests `test_network_stats.py`, `test_apply_parity.py`, `test_offer_chain_confirmation.py`. All read-side; keep until reset.
- **`bridge-leaf-audit.py`**: read-only V-4 audit; the "grandfather" surface is the `envelope` fallback for GAP-47 block-scoped rows whose payload stored empty (module docstring) — keyed to pre-leaf-v2 history.
- Old-height/hash keyed: see item 9 (previous section) — unchanged.

### Item 4 additions — coordinator and bridge ledgers

- `coordinator.db` `job` table: 306 rows **all terminal** — COMPLETED 154, FAILED 38, CANCELED 37, EXPIRED 77. `jobreceipt` 187, `bounty_task` 0, `data_collection_jobs` 0, `resource_allocations` 1 (`released`). **No open coordinator obligations.**
- `bridge_deposits.db` `bridge_outbound`: 5-row log (no status column; kinds: withdrawal×4, released×1, unidentified×1 — the unidentified row's note records a gas-burned failed send). Informational only, nothing pending.
- `eth_withdrawals`: 4 rows — completed×2, refunded×1, settled×1 (corrects the earlier "2 rows" line).
- Re-verify note: director's "50 txs since 46,100" (18 Oct) vs my matrix's 34+12=46 — consistent with overnight growth, not a contradiction.

### Item 5 — archive list (output)

`.pre-reset` copy + checksummed offline copy (`backups/`, 700/600), per host:

- **Custody-bearing** (archive before anything else): `keystore.db`, `admin_nonces.db` (all 5); `peer_keys.db` (hub/hub1/node2); `wallet_ledger.db`, `wallet_operations.db`, `ops-signer-ledger.db` (hub); `/var/lib/aitbc/keystore/` dir incl. `validator_keys.json` (hub + each validator); `/var/lib/aitbc/wallets/*.json` (hub: `default`, `ops`, `sepolia`, `ait-sell-escrow`).
- **Chain data**: `data/<chain_id>/chain.db` (+ `genesis.json`) all 5 hosts; hub's historical `chain.db.bak.*`, `chain.pre-snapshot.*`, `genesis.json.pre-reset.20260903` — archive or dispose per operator.
- **Service DBs** (fresh-start under D5 → archive only): the full `*.db` set from the previous section, plus `agent_coin_requests.db`, `hermes_coin_requests.db`, `bridge_deposits.db`, `exchange/exchange.db`.
- Sizes are small (chain 136 MB, largest service DB 8.6 MB) — fits even hub1's 13 GB.

### Item 6 — genesis allocation proposal (input for operator's numbers)

Post-rotation identities (addresses only, no key material read):

- **Validators (4)**: `0x2aD5…` (hub), `0xE894…` (node2), `0x19f0…` (node1), `0x5E8E…` (hub1) — from `VALIDATOR_SET`, stake weight "1000" each. Need fee/balance funding at genesis; stake itself is config, not balance.
- **Treasury**: current `0x34FF…f267` holds ~1e18 units (~1B AIT); D2 fresh-start means a new or re-confirmed treasury address is operator's call; precedent allocation 1B AIT (`reset_chain_0x.py` convention).
- **Hub wallets present**: `default`=`0x02B8…` (the *pre-rotation* hub proposer id — kept as default wallet), `ops`=`0xa7aD…`, `sepolia`=`0xA556…`, `ait-sell-escrow`=`0x40c7…`. Map these to roles: ops signer, Sepolia-facing wallet, exchange escrow.
- **Faucet**: currently **paused** — hub agent-coordinator has no `GENESIS_PRIVATE_KEY` (confined; `/execute` → 503) and no `COIN_REQUEST_*` env lines at all; hub1 keeps `COIN_REQUEST_AUTO_BUDGET_PER_HOUR=0`. Policy envs exist in code: `COIN_REQUEST_AUTO_APPROVE_MAX`, `COIN_REQUEST_AUTO_BUDGET_PER_{HOUR,DAY}`, `DEFAULT_*`. The pending 100-AIT agent request **cannot execute under current config** — its drain option is a dedicated budget-limited faucet wallet (the operator's stated direction) or a manual payout line.
- **Service accounts**: `reset_chain_0x.py` convention = 1M AIT per wallet + 1M per service account; current funded set shows most service accounts at exactly 36e15 units (1M AIT).
- **Bridge accounts**: 10 bridge validators in `bridge_validators` table; per-host `BRIDGE_VALIDATOR_ADDRESS_*` names only.
- **Suggested minimums for operator review** (numbers are operator's): treasury = operator's amount; validators = enough for fees (~small, e.g. 1–10 AIT each) since block production costs gas against proposer balance; faucet wallet = capped budget sized to `COIN_REQUEST_AUTO_BUDGET_PER_DAY` policy; service accounts = 1M AIT each matching convention; ops/sepolia/sell-escrow = per their current roles.

### Item 8 — tooling, completed

- `verify-genesis-root.py`: **read-only checker** — verifies genesis.json allocation set (non-empty, dedup), recomputes `state_root` via `StateManager.update_account`/`compute_state_root_full`, recomputes block hash. Exit 0/1. This is the verification half of the future genesis harness; keep.
- `reset-follower-to-snapshot.sh`: follower-side installer — stops local units, `.backup`s local DB to `.pre-snapshot.<ts>` (WAL-aware, raw-copy fallback keeps -wal/-shm), fetches hub snapshot to `/tmp`, installs. Leaves validator identity alone; assumes `ait-localnet` default chain id and `hub.aitbc.invalid` default hub (env-overridable). Same family as `-to-genesis`; the W1 collapse makes the v2-height append in the genesis variant obsolete.
- MCP genesis tools (`aitbc_mcp_cli_tools_generated_genesis.py`): `aitbc_genesis_info`/`aitbc_genesis_verify` (read), **`aitbc_genesis_init`** (wraps `aitbc genesis init` — `--create-wallet`, `--proposer`, `--force`, `--register-service`) and **`aitbc_genesis_sync_from_hub`** (writes genesis.json). MCP mutating tools are dry_run/confirm-gated, but the underlying CLI assumptions are the single-proposer ones — **`RESET-TOOL-GUARD-1` scope should include the MCP wrappers**, not just the CLI/scripts.
- Tooling table otherwise as previous section (genesis_reset hazard director-verified; create-genesis-block/reset_chain_0x coder-read).

### Item 11 — co-existence and point of no return

- **Serving co-existence: yes.** `SUPPORTED_CHAINS` is a comma-list (defaults to `chain_id`); `app.py:298-301,446` and `sync_manager.py:122` iterate it — one node process can serve/follow multiple per-chain DBs under `data/<chain_id>/`. No port collision; old chain stays queryable.
- **Production co-existence: no (per process).** `consensus/poa.py` binds everything to `self._config.chain_id` singular (lines 239-327, 477-611) — one producing chain per process. Two *producing* chains on one host need a second unit instance with own ports/env — possible but heavier, and validator key material would need separation anyway.
- **Consequence for PoNR**: the old chain can stay *readable* on the same hosts while the new chain produces — cheap insurance for the rollback window. The true point of no return is therefore **not** "genesis written" but the first irreversible external act: the first Sepolia contract interaction naming the new chain id, or deletion of the `.pre-reset` copies — matching runbook skeleton section D candidates.
- **Contradictions with plan**: none found this pass. (The 46-vs-50 tx-count delta is overnight growth, not a disagreement.)

### Proposed row breakdown (reset release)

1. `RESET-VECTORS-1` — synthetic corpus: v13 GOV binding (zero live evidence), BOND_*/BOUNTY_*/LIQUIDITY_*/RECEIPT_CLAIM branches (never on-chain), v7-ownership edge cases; replay gate = equivalence on 51,001→head window (12 txs) + full-history replay on `.backup` copy.
2. `RESET-GENESIS-HARNESS-1` — genesis.json + DB seed generator (validator set from public-addresses file; verify via `verify-genesis-root.py`).
3. `RESET-TOOL-GUARD-1` — safe-mode-only tools incl. MCP wrapper surface.
4. `RESET-ROLLBACK-1` — follower snapshot install rehearsal (`reset-follower-to-snapshot.sh` is the safe base).
5. `RESET-CHAINID-1` (new) — chain-id rename consumers list → coordinated switch (item-3 list is the input).
6. W2a caller-gated row — after `LEGACY-CALLERS-1` evidence.
7. W2b history-gated row — bundled into the reset release (GPU_MARKETPLACE reads, ait-mainnet fallbacks, v9/shadow code, audit grandfathering).
8. `RESET-SEPOLIA-READ-1` — already staged; feeds bridge re-point decision.
9. `PG-MIGRATIONS-1` → feeds D8.
10. Dress-rehearsal row — containers/VMs on node2 or IDE (no spare fleet).

### CLI/MCP gaps observed

- No CLI for tx counts by type per height range (used raw `mode=ro` sqlite) — suggest `aitbc chain tx-stats --from H --to T`.
- No CLI listing of a host's service stores with engine+size — suggest `aitbc ops stores --host H`.
- `mempool` has no CLI list either (checked via table count).

Nothing was changed on any host, in the repo, or on the chain. Report is coder-produced; independent director verification is the closure gate.

## 2026-10-19 — director-verification corrections (coder's second ledger section)

The director verified the pass-2 report against hub and `origin/main` and returned four errors plus a new decision (v3/v6). Corrections below; each was re-read independently before writing.

### 1. Units — allocation-proposal numbers corrected (live read 19 Oct)

- Treasury `0x34FF…f267`: **35,999,911,364,928,412 units ≈ 999,997,538 AIT** (my "~1e18" was wrong — the correct figure is 3.6e16).
- Service accounts: **13 accounts hold exactly 36,000,000,000,000 units = 1,000,000 AIT each** (my "36e15" was off by 1000×).
- Funded set: 47 accounts totalling **36,612,359,365,190,437 units ≈ 1.017 B AIT**.
- Rule going forward: genesis numbers are quoted from the live read, never from the prior section's approximations.

### 2. `eth_withdrawals` corrected

**2 rows, both `completed`.** The "4 rows (completed×2, refunded×1, settled×1)" I wrote mixed in `bridge_sell_locks` (which is indeed refunded×1 + settled×1). `bridge_deposits.db` drain surface stands as: `eth_deposits` non-terminal ×2 (`funding`, `exchange_prepay`), `bridge_sell_quotes` locked×1, `bridge_deposits` failed×1, `bridge_outbound` 5-row log.

### 3. Item 11 — production co-existence corrected

Wrong: "one producing chain per process." `main.py` builds **one `PoAProposer` per chain in `BLOCK_PRODUCTION_CHAINS`** (`main.py:260`, env at `:658,677`) — a single node process CAN produce several chains. The real limit is **one proposer identity per process** (`PROPOSER_ID`/`PROPOSER_KEY` are single-valued), so an old-chain + new-chain pair on one process shares the same validator key. Clean separation wants separate unit instances — **this is a key-separation question folded into D4, not a code limit.** Serving co-existence via `SUPPORTED_CHAINS` stands as reported.

### 4. Gate semantics — corrected column (from config.py comments, verified line-by-line)

| gate | height | real semantics |
|---|---|---|
| v2 | 0 | version stamping + current account-creation rules (v1 = pre-2026-09-01, no auto-created accounts); 0 = all blocks v2+ from first block |
| v3 | 0 = never stamped | **S-4 per-escrow custody**: lock funds sit in a derived per-escrow account; release debits it, authority pays only fee (`state_transition.py:1620-1635`, route era-check `escrow_routes.py:603-641`) |
| v4 | 11000 | consensus stake lock windows: STAKE_RELEASE must name lock hashes, locks matured |
| v5 | 24000 | **fail-closed authority gates**: ESCROW_RELEASE/REFUND need `escrow_settlement_authority`, GOVERNANCE_EXECUTE needs `governance_executors`, BRIDGE_RELEASE/REFUND need bridge pseudo-sender (NOT "bridge_signature required" as I wrote — that check is adjacent but the gate is the authority gates) |
| v6 | 0 = never stamped | BRIDGE_REFUND must name sealed lock (`payload.lock_tx_hash`, sender/amount match, not already refunded) — `state_transition.py:1396-1407` |
| v7 | 24650 | GPU_REGISTER for existing gpu_id must come from `registered_by` (+envelope nonce authoritative, `use_account_nonce_override` `:1007-1030`) |
| v8 | 24800 | stamped version advisory; height-derived wins, mismatch logged+counted |
| v9 | 30400 | sender signature at apply + stored signed envelope + attester checks |
| v10 | 32100 | GPU_DEREGISTER exists; ALLOCATE on deactivated row refused |
| v11 | 35400 | ESCROW_FEE_SWEEP: authority sweeps custody residue to `escrow_fee_recipient` |
| v12 | 37500 | authority-parameter value checks on GOVERNANCE_EXECUTE parameter_change |
| v13 | 46100 | governance binding: EXECUTE applies sealed PROPOSE's stored execution_payload; PROPOSE must carry it |
| v14 | 46100 | `aux_state_root` in block hash + BRIDGE_LOCK must carry derivable leaf data |

### 5. v3/v6 — the decision reframed by evidence

The config comment "0 disables the gate" is **misleading for the apply path**: the derived-version function skips 3/6 (top-down threshold match, `state_transition.py:958-1006`), but the guarded checks compare `block_version >= N`, so they fire under every later armed version:

- **v3 custody has been de-facto live since v4** — every block ≥11000 derives version ≥4 ≥3, so every lock sealed since then went to a per-escrow custody account. Proven indirectly: the 4 sealed ESCROW_FEE_SWEEPs only have residue because custody accounts exist (sweep comment: "a v2-era job has none").
- **v6 binding has been enforced since v7** — `block_version >= 6` is true for every block ≥24650, and all 3 live BRIDGE_REFUNDs (heights 27639, 51048, 52052) sealed **under** that check carrying `lock_tx_hash`.
- **Does v11 supersede v3?** No — complementary, not superseding: v3 decides *where lock funds sit*; v11 sweeps the residue that v3-custody accounts hold. v11 needs v3 semantics to have anything to sweep.

**Consequence for W1:** collapsing "every rule on from 0" does NOT switch on never-run rules — it preserves the exact semantics the live chain has run since v4/v7. What the collapse deletes is the never-used plumbing: the `get_block_version_for_height` 3/6 branches, the dead route-era refusal at `escrow_routes.py:636` (`block_height < 0` never fires), and the `lock_version` fallback. The residual operator decision is narrower: v6's "already refunded" double-refund path and v3's v2-era-lock fallback were never *triggered* on-chain — they need synthetic vectors in `RESET-VECTORS-1`, or explicit deletion if the new chain will never see those inputs (it won't — no v2-era locks, no unbound refunds).

Flag for the release notes: `config.py`'s "0 disables the gate" comments for v3/v6 should be corrected — on this codebase a 0 height never disabled the apply-path `>=` checks.

Verbatim text of the two last unverified sites (provided for director check):
- `escrow_routes.py:636`: `if block_height < settings.state_transition_v3_height:` → HTTP 409 "…below state_transition_v3_height=… (v2-era); routes do not settle these rows — operator repair only". With `v3_height=0` the guard is `block_height < 0` — unreachable.
- `state_transition.py` lock_version resolution: `_get_escrow_lock_block_version` (`:665-678`) reads the lock's own sealed-block version via `get_block_version`; only when None does `lock_version = 2 if block_version < 3 else 3` (`:1600-1601`, mirror at `:1978`) apply — and every applying block derives ≥4, so the fallback always yields 3.

## 2026-10-19 — env-pin correction (deployed heights, not config defaults)

**Coder error corrected by the director:** the earlier table quoted `config.py` defaults as deployed truth. The deployed pins (`grep ^STATE_TRANSITION_V.*_HEIGHT /etc/aitbc/*.env`, read 19 Oct ~08:45 CEST) are **uniform on all five hosts**:

```
STATE_TRANSITION_V2_HEIGHT=0      (in 14 env files per director)
STATE_TRANSITION_V3_HEIGHT=5470   (armed by env — config default is 0)
STATE_TRANSITION_V11_HEIGHT=35400
STATE_TRANSITION_V12_HEIGHT=37500
```

Consequences:
- **v3 is armed at 5470**, so custody (`block_version >= 3`) has been live **since 5470**, not 11000 as the earlier section said. Blocks 5470–10999 derive version 3; ≥11000 version 4+.
- **`escrow_routes.py:636` is live, not unreachable** — the six locked escrows (lock heights 1262–1598, all < 5470) are v2-era and route settlement answers 409 "operator repair only" (per `docs/ops/escrow-settlement-ops.md` §1.4 + deployed env). The guard is working as designed; `ESCROW-V2ERA-GUARD-1` was withdrawn by the director (there is nothing to fix).
- **Drain consequence:** the six escrows cannot settle via the normal route. Apply-time still resolves `lock_version=2` for them (sender-debit path), so draining means a **direct ESCROW_RELEASE/REFUND transaction** bypassing the route's 409, or operator repair — a named-line chain write each way, matching the existing drain rule.
- **v6 stands**: still height 0 (no env pin), de-facto enforced since 24650 via `>=6` checks; all 3 sealed refunds carried `lock_tx_hash`.
- **New inventory requirement (relayed from the director):** the rule-collapse inventory must list env pins per host — the live rule set is **config defaults + env overrides**, not config alone. The earlier "0 disables the gate" release-note flag now applies only to v6's comment (v3's pin exists and works); and on the *new* chain the route-era guard + derivation plumbing become unneeded again — collapse deletes them for the fresh-chain reason, not because they were dead here.

## 2026-10-19 09:22 CEST — D1 resolved: chain id = `bc-2`

**Decided:** `bc-2` — selected by the operator 19 Oct after the coder named it (revised from `bc-v2` on the director's overload point). Rationale:
- `v2` is already claimed four ways in this codebase: `state_transition_v2` gate, bridge leaf-v2 (height 51000), the v2 replay window, and `gossip_tx_topic_v2_template` — which would render `transactions.bc-v2` ("the v2 topic on bc-v2"). In a reset ledger saturated with v2–v14 tokens, a chain named `bc-v2` invites grep/alert misreads exactly when they cost most.
- `bc-2` keeps the generation marker (it is the second chain), drops the colliding token, and stays generic — the fleet is single-chain so genericness costs nothing.
- Label only: never resolved as DNS (id is a key in `chain_id:url` maps; URLs come from the value side → **no DNS change**).
- Dated labels (`bc-2026`) rejected: reset is unscheduled, a baked-in year can lie later.

**Validator check** (`rpc/utils.py:258-260`, read 19 Oct): `validate_chain_id` is a **membership** check (`chain_id in supported_chains`), not a charset validator — no regex exists. The binding constraints are parse seams: no `,` (`split(",")` at `utils.py:265`), no `:` (`chain_id:url` at `config.py:272`, `island_id:chain_id:hub_url` at `:294`, `chain_id:redis://` at `:316`, `chain_id:height` composite at `settlement.py:78`), plus path component (`data/<id>/chain.db`), env suffix (`CHAIN_CONFIG_<id>`), and gossip topic (`transactions.<id>`). `bc-2` passes all.

Touch surface at cut (env names, no values invented): `CHAIN_ID`, `SUPPORTED_CHAINS`, `BLOCK_PRODUCTION_CHAINS`, `CHAIN_SYNC_SOURCES`, `GOSSIP_BACKENDS`, `ISLAND_REGISTRY`, `trusted_proposers`; monitor/coordinator/exchange `CHAIN_ID`-ish names; service-DB `chain_id` columns then write `bc-2`; stale signed bodies from the old chain are invalid on the new id by construction (feature, per hermes-envelope analysis).

**Dress rehearsal:** operator chose **node2 containers** (32 CPU/24GB, ~8TB free; closest to fleet hardware, runs beside live services).

Still open: D8 (director's recommendation, relayed: **no DB moves at reset** — all services start on fresh SQLite, pool-hub stays on its current PG; the six fix rows register post-reset), genesis allocation numbers. **Inventory closed by the director.** `PG-MIGRATIONS-1` done (ledger `tasks/progress/PG-MIGRATIONS-1.md`, "verified partly" — matrix/NUMERIC/suite results unreproduced).
