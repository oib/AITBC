# bc-2 Host Inventory

Read-only host census for `bc2-reset-runbook.md` — the per-host unit
names, timers, and store files the C1/C2 steps act on. Gathered
2026-10-20 with `systemctl list-unit-files`/`list-units`/`cat`, `ls` and
`test -e` (name lists only; no env values, no key material).

Conventions: **stop order** follows the runbook's dependency order —
customer-facing first, coordinator/exchange/market next, rpc before
node, node/p2p last. Monitoring units (`aitbc-prometheus-watch`,
`aitbc-monitoring`, node-exporter, `prometheus.service` on hub) are
observability, not writers — they stay up through the window so the
alert evidence keeps flowing (see `RESET-ALERTS-1`).

## hub — proposer + all customer services (34 active aitbc units)

### Stop order for C1 (unit names)

1. Customer-facing: `aitbc-api-gateway`, `aitbc-blockchain-explorer`,
   `aitbc-wallet`, `aitbc-agent-coordinator`, `aitbc-ops-signer`,
   `aitbc-blockchain-event-bridge`, `aitbc-island-ipfs`,
   `aitbc-pool-hub`, `aitbc-bridge-monitor`, `aitbc-recovery`,
   `aitbc-load-secrets`, `aitbc-governance`
2. Coordinator/exchange/market: `aitbc-coordinator-api`,
   `aitbc-exchange`, `aitbc-market`, `aitbc-trading`
3. RPC: `aitbc-blockchain-rpc`
4. Node/p2p last (validator-interrupting): `aitbc-blockchain-node`,
   `aitbc-blockchain-p2p`

`aitbc-blockchain-p2p` exists **only on hub** — hub1/node0/node1/node2
have no such unit (`systemctl cat` → "No files found"); their
`aitbc-blockchain-p2p.env` files exist but serve no unit.

### Timers (13) — what each writes

| timer | cadence | writes | in-window behaviour |
|---|---|---|---|
| `aitbc-escrow-settlements.timer` | minutely | read-only `.prom` (escrow-settlements-textfile.py scans `data/*/chain.db`) — the chain-writing settlement sweeper lives inside `aitbc-coordinator-api` and stops with C1 | **suspend first** — after C2 it finds no chain.db and emits CheckFailed noise |
| `aitbc-backup.timer` | daily 01:00 | dump files under `/var/backups/aitbc` | **suspend** — a mid-window run dumps the old chain or fails on moved dirs and leaves a torn "latest" generation |
| `aitbc-native-energy-rate-refresh.timer` | 12-hourly | POSTs the energy rate → coordinator service DB | **suspend** — writes into the old service DB if it fires before the move |
| `aitbc-ntfy-heartbeat-daily.timer`, `aitbc-ntfy-heartbeat-hourly.timer` | daily/hourly | outbound notifications | optional — keep or suspend with the batch |
| `aitbc-authority-balances.timer` | minutely | read-only `.prom` (RPC reads) | suspend — rpc down means Unreadable noise |
| `aitbc-bridge-set.timer` | static | read-only `.prom` (`data/*/chain.db` scan) | suspend |
| `aitbc-env-watch.timer` | 15 min | read-only `.prom` (env-name presence) | suspend — C3 edits names mid-window |
| `aitbc-journal-errors.timer` | ~5 min | read-only `.prom` (journal scan) | optional — expected AITBCJournalErrors noise either way |
| `aitbc-cache-monitor.timer`, `aitbc-memory-monitor.timer` | 15 min | read-only `.prom`/logs | optional |
| `aitbc-chain-isolation-monitor.timer` | hourly | read-only verify + log | suspend — hosts intentionally diverge |

### Store files (`/var/lib/aitbc/data/`)

- Chain dir `ait-hub.aitbc.bubuit.net/`: `chain.db` (+`-shm`/`-wal`),
  `genesis.json`, `genesis.json.pre-reset.20260903-191240`,
  `chain.pre-snapshot.20260909-*` (2), `chain.db.bak.*` sets (20260910,
  -20260927-fork, -20260928-27207wedge, -pre-gpu-clean-20261002).
- **Top-level `chain.db`** (legacy, outside any chain dir).
- Service DBs: `admin_nonces.db`, `agent_coin_requests.db`,
  `agent_coordinator.db`, `agent_management.db`, `bridge_deposits.db`,
  `coordinator_api.db`, `coordinator.db`, `coordinator_operations.db`,
  `governance_service.db`, `hermes_coin_requests.db`, `keystore.db`,
  `market_operations.db`, `marketplace_service.db` (+4 `.bak`),
  `ops-signer-ledger.db`, `peer_keys.db`, `trading_service.db`,
  `wallet_ledger.db`, `wallet_operations.db`.
- Dirs: `exchange/` (`exchange.db`, `trading_service.db`,
  `wallet_ledger.db` + `.bak`, `wallet_operations.db`, 4 test json),
  `backups/`, `ipfs-island/`.

## hub1 — proposer/follower services only (11 active units)

### Stop order

1. `aitbc-blockchain-explorer`, `aitbc-wallet`, `aitbc-island-ipfs`,
   `aitbc-recovery`, `aitbc-load-secrets`
2. `aitbc-governance`, `aitbc-trading`
3. `aitbc-blockchain-rpc`
4. `aitbc-blockchain-node` (validator-interrupting)

No p2p unit. Timers (8): `alert-digest`, `backup-metrics`, `backup`,
`cache-monitor`, `chain-isolation-monitor`, **`escrow-settlements`**,
`journal-errors`, `memory-monitor` — same write classes as hub;
`alert-digest` sends digest notifications.

### Store files

- Chain dir `ait-hub.aitbc.bubuit.net/` with `chain.db`.
- Top-level `genesis.json` (old artifact).
- Service DBs: `admin_nonces.db`, `agent_coordinator.db`,
  `agent_management.db`, `bridge_deposits.db`, `coordinator.db`,
  `coordinator_operations.db`, `governance_service.db`, `gpu_service.db`,
  `hermes_coin_requests.db`, `keystore.db` (+`keystore/` dir),
  `market_operations.db`, `marketplace.db`, `marketplace_service.db`,
  `peer_keys.db`, `trading_service.db`, `wallet_ledger.db`,
  `wallet_operations.db`.
- Dir: `exchange/`, `ipfs-island/`.
- **No top-level `chain.db`** (only host without one).

## node0 — customer follower, non-validator (11 active units)

### Stop order

1. `aitbc-blockchain-explorer`, `aitbc-wallet`, `aitbc-island-ipfs`,
   `aitbc-recovery`, `aitbc-load-secrets`
2. `aitbc-governance`, `aitbc-trading`
3. `aitbc-blockchain-rpc`
4. `aitbc-blockchain-node` (last — always last fleet-wide)

No p2p unit. Timers (9): hub1's set plus `aitbc-ntfy-heartbeat-daily`.

### Store files

- Chain dir `ait-hub.aitbc.bubuit.net/` + **top-level `chain.db`**.
- Service DBs: `admin_nonces.db`, `agent_coin_requests.db`,
  `aitbc_edge.db`, `bridge_deposits.db`, `coordinator.db` (+`.backup`,
  `.backup2`), `gpu_service.db`, `keystore.db`,
  `marketplace_service.db`, plus per-service dbs under `coordinator/`,
  `marketplace/`, `exchange/`, `agent-coordinator/`, `registry/`,
  `blockchain-event-bridge/`, `openclaw/` dirs.
- Legacy/stray residue inside `data/` (move with the sweep): `aitbc_chain.db`,
  `blockchain.db`, `agent_registry.json`, `cli_extended_state.json`,
  `economic_system.json`, `gpu_marketplace.json`, `job_marketplace.json`,
  `test_*.json` (15 files), `README.md`, `ipfs-island/`.

## node1 — proposer/follower (11 active units)

### Stop order

Same unit set as hub1 (explorer, wallet, island-ipfs, recovery,
load-secrets → governance, trading → rpc → node; node is
validator-interrupting). No p2p unit. Timers (8): hub1's set.

### Store files

- Chain dir `ait-hub.aitbc.bubuit.net/` + **top-level `chain.db`**
  (+`chain.db.ait-testnet.bak`, `chain.db.backup.20260428_082834`,
  `mempool.db.ait-testnet.bak`).
- Service DBs: `admin_nonces.db`, `agent_coin_requests.db`,
  `aitbc_chain.db` (legacy), `blockchain.db` (legacy),
  `bridge_deposits.db`, `coordinator.db`, `governance_service.db`,
  `keystore.db`, `trading_service.db`, `wallet_ledger.db`,
  `wallet_operations.db`.
- Dirs: `exchange/`, `ipfs-island/`, `agent-coordinator/`.

## node2 — proposer + shop services (18 active units)

### Stop order

1. Shop/customer-facing: `aitbc-hermes-agent`, `aitbc-market`,
   `aitbc-edge`, `aitbc-ffmpeg`, `aitbc-whisper`, `aitbc-gpu`,
   `aitbc-miner`, `aitbc-api-gateway`, `aitbc-blockchain-explorer`,
   `aitbc-wallet`, `aitbc-island-ipfs`, `aitbc-recovery`,
   `aitbc-load-secrets`
2. `aitbc-governance`, `aitbc-trading`
3. `aitbc-blockchain-rpc`
4. `aitbc-blockchain-node` (validator-interrupting)

No p2p unit. Timers (9): hub1's set minus none, plus
`aitbc-island-subscription-check` (subscription verify, read-mostly).

### Store files

- Chain dir `ait-hub.aitbc.bubuit.net/` + **top-level `chain.db`**,
  `chain_aitbc.db`, `chain-backup-2026-08-22.db`,
  `pre-migrate-20260816_220424-island-chain.db`.
- Service DBs: `admin_nonces.db`, `agent_coin_requests.db`,
  `agent_coordinator.db`, `agent_management.db`, `aitbc_edge.db`
  (+`.bak-pre-sweep`), `bridge_deposits.db`, `coordinator_api.db`,
  `coordinator.db` (+5 `.bak`), `coordinator_operations.db`,
  `governance_service.db`, `gpu_service.db`, `hermes_coin_requests.db`,
  `keystore.db`, `market_operations.db`, `market_service.db`,
  `marketplace_service.db` (+`.bak`), `peer_keys.db`,
  `trading_service.db`, `wallet_ledger.db`, `wallet_operations.db`,
  `agent_executor_state.json`, `README.md`.
- Dir: `ipfs-island/`.

## Cut-day notes

- `.pre-reset` destination: `/var/lib/aitbc/pre-reset-<YYYY-MM-DD>/` — a
  **sibling of `data/`, never inside it**. Everything listed above (chain
  dir, service DBs, stray top-level `chain.db`, `*.bak` residue) moves
  into that tree, so the `data/*/chain.db` textfile exporters see no
  archived store after C2. Same filesystem → the move is a rename; the
  §D move-back is fast.
- `Restart=on-failure` is set on every `aitbc-blockchain-node` unit on
  all five hosts — a failed bc-2 start crash-loops; `is-active` alone is
  not proof of a clean start (journal evidence at C5).
- `BRIDGE_LOCKS_PAUSED` appears in **two** env files on hub
  (`blockchain.env`, `bootstrap.env`) — the B3 flag edit covers both.
- `TRUSTED_PROPOSERS` appears in **zero** env files on hub and node0 —
  C3 adds the name, it does not edit an existing line.
- node0's drift names live nowhere in `blockchain.env`;
  `STATE_SYNC_MAX_GAP` is pinned only in `aitbc-blockchain-node.env`.
- Env-name file counts on hub (name → files): `CHAIN_ID` 18,
  `PBFT_CONSENSUS_ENABLED` 13, `BLOCK_TIME_SECONDS` 14,
  `MULTI_VALIDATOR_MIN_ATTESTATIONS` 5, `ENABLE_BLOCK_PRODUCTION` 3,
  `GOSSIP_BACKEND` 3, `BRIDGE_LOCKS_PAUSED` 2, `SUPPORTED_CHAINS` 2,
  `AUTO_SYNC_ENABLED` 2, `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP` 1.
  A C3 verify greps *every* file holding a name, not just the first.
