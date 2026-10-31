# bc-3 env map — /etc/aitbc/*.env key-name union across the fleet

Status: **read-only audit, Phase-0 evidence for the E4 row.** Key
NAMES only — this document contains no env values and must never gain
any. Names were collected via
`grep -oHE '^[[:space:]]*(export[[:space:]]+)?[A-Z][A-Z0-9_]*=' /etc/aitbc/*.env`
on each host (2026-10-31).

## 1. Inventory

| host | env files | unique key names |
|---|---|---|
| node0 | 32 | 164 |
| node1 | 30 | 159 |
| node2 | 36 | 216 |
| hub | 37 | 250 |
| hub1 | 41 | 259 |
| **union** | | **333** |

## 2. Disposition table (grouped by family)

| family | keys | bc-3 disposition |
|---|---|---|
| chain identity (3) | `CHAIN_ID`, `DEFAULT_CHAIN_ID`, `SUPPORTED_CHAINS` | **rewrite** — new chain id from #410; GENESIS_ADDRESS wallet only on hub-era units |
| STATE_TRANSITION_V*_HEIGHT (17) | `STATE_TRANSITION_V10_HEIGHT`, `STATE_TRANSITION_V11_HEIGHT`, `STATE_TRANSITION_V12_HEIGHT`, `STATE_TRANSITION_V13_HEIGHT`, … (17) | **rewrite** — all heights → 1 on the new chain (GATES.md rule) |
| validator/proposer/consensus (12) | `ATTESTATION_POST_QUORUM_LINGER_SECONDS`, `BLOCK_PRODUCTION_CHAINS`, `ENABLE_BLOCK_PRODUCTION`, `MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS`, … (12) | **rewrite** — VALIDATOR_SET/VALIDATOR_KEYS per rotated set; PROPOSER_ID/PROPOSER_KEY per validator host; TRUSTED_PROPOSERS genesis value |
| BRIDGE_* (30) | `BRIDGE_ADMIN_PRIVATE_KEY_SOURCE`, `BRIDGE_DB_PATH`, `BRIDGE_DEPOSITS_DB`, `BRIDGE_ENABLED`, … (30) | **mixed** — BRIDGE_LOCKS_PAUSED → true staged at genesis (decided #410); authority/payout/admin keys → custody gate; contract/redploy rows → investigate (redeploy flow, bc-3 launches paused) |
| ESCROW_* (10) | `ESCROW_CHANGE_PASS_DRY_RUN`, `ESCROW_CHANGE_PASS_ENABLED`, `ESCROW_FEE_RECIPIENT`, `ESCROW_FEE_SWEEP_ENABLED`, … (10) | **mixed** — ESCROW_FEE_RECIPIENT → treasury SOT (#489); ESCROW_FEE_SWEEP_* verbatim; *_PRIVATE_KEY rows → custody gate §2 |
| *_PRIVATE_KEY (signing) (8) | `BOND_SLASH_PRIVATE_KEY`, `BRIDGE_PAYOUT_PRIVATE_KEY`, `BRIDGE_RELEASE_PRIVATE_KEY`, `ESCROW_RELEASE_PRIVATE_KEY`, … (8) | **custody-gate** — key material never migrates verbatim by doc — each needs a known-store proof (§2); no keys in envs that should hold only addresses |
| proposer/validator signing keys (1) | `PROPOSER_KEY` | **custody-gate** — per-host proposer keys — known-store proof required |
| *_ADDRESS (verifying/configured peers) (20) | `ADMIN_WALLET_ADDRESSES`, `AGENT_ECONOMICS_OPERATOR_ADDRESS`, `BOND_BURN_ADDRESS`, `BOND_SLASH_AUTHORITY_ADDRESS`, … (20) | **mostly migrate-verbatim** — address pins without keys are safe to carry; authority addresses re-verify vs classes.json SOT |
| service auth keys (*_API_KEY / JWT_SECRET_KEY / SECRET_KEY) (21) | `AGENT_ECONOMICS_OPERATOR_KEY`, `AITBC_API_KEY`, `API_GATEWAY_KEY`, `API_KEY`, … (21) | **migrate-verbatim** — service-to-service shared secrets — carry as-is; rotation is a separate decision |
| gossip/mesh peering (8) | `DEFAULT_PEER_RPC_URL`, `GOSSIP_BACKEND`, `GOSSIP_BROADCAST_URL`, `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP`, … (8) | **rewrite** — GOSSIP_MESH_PEER_URLS re-seeded for the new mesh; HUB_DISCOVERY_URL/DEFAULT_PEER_RPC_URL repointed to the bc-3 hub |
| sync/snapshot (5) | `AUTO_SYNC_ENABLED`, `AUTO_SYNC_THRESHOLD`, `STATE_SYNC_MAX_GAP`, `SYNC_MANAGER_ENABLED`, `SYNC_STATE_ROOT_VALIDATION_ENABLED` | **migrate-verbatim** — incl. node0 STATE_SYNC_MAX_GAP=-1 decided value |
| timing/rate/budget (2) | `BLOCK_TIME_SECONDS`, `MAX_EMPTY_BLOCK_INTERVAL` | **migrate-verbatim** — existing tuned values carry; no semantic changes expected |
| mempool/storage (3) | `DATABASE_URL`, `MEMPOOL_BACKEND`, `MEMPOOL_DB_URL` | **migrate-verbatim** — MEMPOOL_BACKEND=database + pg DSN; storage paths carry |
| agent-coordinator (8) | `AGENT_COORDINATOR_BIND_HOST`, `AGENT_COORDINATOR_BIND_PORT`, `AGENT_COORDINATOR_URL`, `AGENT_DB_PATH`, … (8) | **migrate-verbatim** — hub-located service config carries; TASK_PAYMENT_ESCROW_ENABLED etc. |
| AITBC_* client/metrics (16) | `AITBC_DEFAULT_WALLET`, `AITBC_HEARTBEAT_URL`, `AITBC_HOSTNAME`, `AITBC_NODE_METRICS_HOST`, … (16) | **migrate-verbatim** — cli/metrics wiring |
| redis (6) | `REDISCLI_AUTH`, `REDIS_DB`, `REDIS_HOST`, `REDIS_PASSWORD`, `REDIS_PORT`, `REDIS_URL` | **migrate-verbatim** — local redis wiring |
| ethereum/website (4) | `ETH_NETWORK`, `ETH_RPC_URL`, `WEBSITE_CHAIN_ID`, `WEBSITE_DOMAIN` | **migrate-verbatim** — Sepolia RPC + website keys unchanged until redeploy flow |
| exchange (5) | `EXCHANGE_HOST`, `EXCHANGE_PORT`, `EXCHANGE_SETTLEMENT_ENABLED`, `SELL_ESCROW_ENABLED`, `SELL_ESCROW_FUNDING_SOURCES` | **migrate-verbatim** — exchange wiring incl. SELL_TREASURY_ADDRESS — value stays, must equal treasury SOT |
| miner/gpu/energy (10) | `ENERGY_MAX_RATE_AGE_SECONDS`, `ENERGY_PRICING_CHAIN_ID`, `FFMPEG_GPU_DEVICE`, `FFMPEG_HW_ACCEL`, … (10) | **migrate-verbatim** — gpu/miner/energy service wiring |
| market/shop (12) | `HERMES_AGENT_ID`, `HERMES_COORDINATOR_URL`, `HERMES_DB_PATH`, `HERMES_PORT`, … (12) | **migrate-verbatim** — market wiring; review shop envs only on node2 |
| p2p/subscription (6) | `P2P_BIND_HOST`, `P2P_BIND_PORT`, `P2P_NODE_ID`, `P2P_PEERS`, `SUBSCRIPTION_ENABLED`, `SUBSCRIPTION_TRANSPORT` | **migrate-verbatim** — subscription transport + ipfs wiring |
| governance/bond (6) | `BOND_SLASH_DOWNTIME_COOLDOWN_SECONDS`, `BOND_SLASH_TX_FEE`, `GOVERNANCE_DEFAULT_CHAIN_ID`, `GOVERNANCE_ENABLE_ONCHAIN_SUBMISSION`, `GOVERNANCE_TIMELOCK_BLOCKS`, `GOVERNANCE_VOTING_PERIOD_BLOCKS` | **mixed** — GOVERNANCE_* keys → custody gate; BOND_* addresses verbatim vs authorities table |
| edge/gateway/follower (3) | `API_GATEWAY_BIND_HOST`, `EDGE_WORKER_EXECUTOR`, `GATEWAY_REQUIRED_SERVICES` | **migrate-verbatim** — gateway/follower api keys verbatim |
| service wiring (10) | `BLOCKCHAIN_RPC_API_KEY_PEERS`, `BLOCKCHAIN_RPC_URL`, `COORDINATOR_BASE_URL`, `COORDINATOR_BOND_MIN_AMOUNT`, … (10) | **migrate-verbatim** — ports/bind/urls per host |
| misc (107) | `ADMIN_API_KEYS`, `AIT_EUR_FIXED_PRICE`, `AIT_SELL_ESCROW`, `AIT_USD_FIXED_PRICE`, … (107) | **investigate** — row-by-row review |

## 3. Enumeration gaps — live vars outside the fleet checker's set

The checker (`scripts/monitoring/fleet-config-check.sh` `VARS` + `EFF_VARS` +
`SHADOW_CONFLICT_ALLOW` + inline greps) enumerates **46** names; the live union covers **333**. Covered: **38**; gaps: **295**. Dead checker rows (enumerated but absent everywhere on the fleet): `ESCROW_SETTLEMENT_AUTHORITY`, `AGENT_INTEGRATION_ZK_MOCK`, `BOND_ESCROW_ADDRESS`, `SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL`, `CONSENSUS_PROPOSER_ROUND_SECONDS`.

Gaps grouped by file class — full names in the appendix:

### blockchain service envs (110)

- `AGENT_ECONOMICS_OPERATOR_ADDRESS` — `aitbc-blockchain-rpc.env`, `aitbc-coordinator-api.env`, `blockchain.env`
- `AITBC_DEFAULT_WALLET` — `node.env`
- `AITBC_HOSTNAME` — `blockchain.env`, `node.env`
- `AITBC_NODE_METRICS_HOST` — `blockchain.env`
- `AITBC_NODE_METRICS_PORT` — `aitbc-blockchain-node-island.env`, `node-island.env`
- `AITBC_PROTOCOL` — `node.env`
- `AIT_EUR_FIXED_PRICE` — `blockchain.env`, `exchange.env`
- `ALLOW_LOCAL_BLOCKCHAIN_RPC` — `aitbc-coordinator-api-override.env`, `blockchain.env`
- `API_PORT` — `blockchain.env`
- `ATTESTATION_POST_QUORUM_LINGER_SECONDS` — `aitbc-blockchain-node.env`, `node.env`
- `AUTO_SYNC_ENABLED` — `aitbc-blockchain-node.env`, `blockchain.env`, `bootstrap.env`
- `AUTO_SYNC_THRESHOLD` — `aitbc-blockchain-node-island.env`, `aitbc-blockchain-node.env`, `blockchain-island.env` …
- `BLOCKCHAIN_MODE` — `blockchain.env`, `bootstrap.env`, `node-island.env`
- `BLOCKCHAIN_RPC_URL` — `aitbc-blockchain-node.env`, `aitbc-coordinator-api-override.env`, `aitbc-market.env` …
- `BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS` — `blockchain.env`, `bootstrap.env`
- `BLOCK_TIME_SECONDS` — `aitbc-blockchain-explorer.env`, `aitbc-blockchain-node.env`, `aitbc-blockchain-p2p.env` …
- `BRIDGE_ADMIN_ADDRESSES` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_DEPOSITS_DB` — `blockchain.env`
- `BRIDGE_LEDGER_API_KEY` — `aitbc-blockchain-rpc-island.env`, `aitbc-blockchain-rpc.env`
- `BRIDGE_LEDGER_URL` — `aitbc-blockchain-rpc-island.env`, `aitbc-blockchain-rpc.env`
- `BRIDGE_LOCKS_PAUSED` — `blockchain-island.env`, `blockchain.env`, `bootstrap.env`
- `BRIDGE_LOCK_LEAF_V2_HEIGHT` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_LOCK_REQUIRE_REPLAY_GUARD` — `aitbc-blockchain-rpc.env`
- `BRIDGE_MAX_LOCK_AMOUNT` — `blockchain.env`, `bootstrap.env`
- `BRIDGE_MULTISIG_ENABLED` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_MULTISIG_THRESHOLD` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_MULTISIG_VALIDATORS` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_RELAYER_ENABLED` — `blockchain.env`
- `BRIDGE_RELEASE_ENABLED` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_RELEASE_KEYS_JSON` — `aitbc-blockchain-rpc-island.env`, `aitbc-blockchain-rpc.env`
- `BRIDGE_RELEASE_PRIVATE_KEY` — `aitbc-blockchain-node.env`, `aitbc-blockchain-rpc-island.env`, `aitbc-blockchain-rpc-override.env`
- `BRIDGE_REQUIRE_MERKLE_PROOF` — `blockchain-island.env`, `blockchain.env`
- `BRIDGE_ROOT_SHADOW_CHECK` — `aitbc-blockchain-node.env`
- `BRIDGE_SUPPORTED_CHAINS` — `blockchain-island.env`, `blockchain.env`
- `COIN_APPROVAL_MODE` — `node.env`
- `COIN_AUTOMATIC_APPROVAL_AMOUNT` — `node.env`
- `CONSENSUS` — `blockchain.env`
- `CONTACT_EMAIL` — `node.env`, `website.env`
- `CROSS_CHAIN_REQUIRE_REPLAY_GUARD` — `aitbc-blockchain-rpc.env`
- `DB_ENCRYPTION_ENABLED` — `blockchain.env`
- `DB_KEEPER_CONNECTION` — `blockchain.env`
- `DEBUG` — `blockchain.env`
- `DEFAULT_PEER_RPC_URL` — `aitbc-blockchain-node.env`, `blockchain.env`, `bootstrap.env` …
- `DISABLED_SERVICES` — `node.env`
- `ENABLE_AI_APPROVAL` — `node.env`
- `ENERGY_OPERATOR_ADDRESS` — `aitbc-blockchain-rpc.env`, `aitbc-coordinator-api.env`
- `ESCROW_CHANGE_PASS_DRY_RUN` — `aitbc-blockchain-rpc.env`
- `ESCROW_CHANGE_PASS_ENABLED` — `aitbc-blockchain-rpc.env`
- `ESCROW_FEE_SWEEP_PASS_ENABLED` — `aitbc-blockchain-rpc.env`
- `ESCROW_RELEASE_PRIVATE_KEY` — `aitbc-blockchain-rpc-override.env`
- `EXCHANGE_HOST` — `aitbc-exchange.env`, `blockchain.env`
- `EXCHANGE_PORT` — `blockchain.env`
- `EXTRA_SERVICES` — `node.env`
- `FOLLOWER_API_KEY` — `blockchain.env`, `bootstrap.env`
- `GENESIS_ADDRESS` — `aitbc-agent-coordinator.env`, `aitbc-blockchain-explorer.env`, `aitbc-blockchain-node.env` …
- `GENESIS_WALLET_ADDRESS` — `aitbc-blockchain-explorer.env`, `aitbc-blockchain-node.env`, `aitbc-blockchain-p2p.env` …
- `GOSSIP_BROADCAST_URL` — `blockchain-secrets-island.env`, `blockchain-secrets.env`, `blockchain.env`
- `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP` — `blockchain.env`, `node.env`
- `HARDWARE_PROFILE` — `bootstrap.env`, `node.env`
- `HERMES_AGENT_ID` — `node.env`
- `HERMES_COORDINATOR_URL` — `node.env`
- `HERMES_DB_PATH` — `node.env`
- `HERMES_PORT` — `node.env`
- `HUB_BLOCKCHAIN_RPC_URL` — `node.env`
- `HUB_COORDINATOR_URL` — `node.env`
- `HUB_DISCOVERY_URL` — `aitbc-blockchain-node.env`, `aitbc-miner.env`, `blockchain-secrets.env` …
- `HUB_HERMES_URL` — `node.env`
- `HUB_PROPOSER_ID` — `blockchain.env`, `node.env`
- `HUB_RPC_URL` — `aitbc-blockchain-rpc-override.env`, `aitbc-market.env`, `aitbc-marketplace.env` …
- `INFURA_API_KEY` — `node.env`
- `ISLAND_HUB_PROPOSER_ID` — `aitbc-blockchain-node.env`
- `ISLAND_ID` — `aitbc-island-ipfs.env`, `aitbc-island-subscription-check.env`, `bootstrap.env` …
- `IS_HUB` — `blockchain-island.env`, `blockchain.env`, `node.env`
- `LOG_LEVEL` — `blockchain.env`
- `MARKET_BOND_MIN_AMOUNT` — `blockchain.env`
- `MARKET_ROLE` — `blockchain.env`, `bootstrap.env`, `node.env`
- `MAX_EMPTY_BLOCK_INTERVAL` — `aitbc-blockchain-node-island.env`, `aitbc-blockchain-node.env`, `blockchain-island.env` …
- `MEMPOOL_BACKEND` — `blockchain-island.env`, `blockchain.env`, `node.env`
- `MEMPOOL_DB_URL` — `blockchain-island.env`, `node.env`
- `MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS` — `aitbc-blockchain-node.env`, `blockchain-island.env`, `blockchain.env` …
- `MULTI_VALIDATOR_MIN_ATTESTATIONS` — `aitbc-blockchain-explorer.env`, `aitbc-blockchain-node-island.env`, `aitbc-blockchain-node.env` …
- `NATIVE_COORDINATOR_URL` — `node.env`
- `NETWORK_ID` — `blockchain.env`
- `NODE_ENV` — `aitbc-coordinator-api-override.env`, `blockchain.env`
- `NODE_ID` — `node-island.env`, `node.env`
- `NODE_WALLET_ADDRESS` — `node.env`
- `OLLAMA_MODEL` — `node.env`
- `OLLAMA_URL` — `node.env`
- `P2P_BIND_HOST` — `aitbc-blockchain-p2p.env`, `node.env`
- `P2P_BIND_PORT` — `node.env`
- `P2P_NODE_ID` — `node-island.env`, `node.env`
- `P2P_PEERS` — `node.env`
- `PARALLEL_TX_VALIDATION` — `blockchain.env`
- `PBFT_CONSENSUS_ENABLED` — `aitbc-blockchain-explorer.env`, `aitbc-blockchain-node.env`, `aitbc-blockchain-p2p.env` …
- `PBFT_VIEW_CHANGE_TIMEOUT` — `aitbc-blockchain-node.env`, `blockchain.env`, `node.env`
- `REQUIRE_TRUSTED_RECEIPT_KEYS` — `blockchain.env`
- `RPC_BIND_HOST` — `aitbc-blockchain-rpc-island.env`, `blockchain.env`, `node-island.env` …
- `RPC_BIND_PORT` — `aitbc-blockchain-rpc-island.env`, `blockchain.env`, `node-island.env` …
- `RPC_PUBLIC_ENDPOINT` — `aitbc-blockchain-rpc.env`, `node.env`
- `SIDE_ROOT_SHADOW_ENABLED` — `aitbc-blockchain-node.env`
- `STATE_SYNC_MAX_GAP` — `aitbc-blockchain-node.env`
- `SUBSCRIPTION_ENABLED` — `aitbc-blockchain-node.env`, `blockchain-island.env`, `blockchain.env` …
- `SUBSCRIPTION_TRANSPORT` — `aitbc-blockchain-node.env`, `blockchain-island.env`, `blockchain.env`
- `SYNC_MANAGER_ENABLED` — `aitbc-blockchain-node.env`, `blockchain-island.env`, `blockchain.env` …
- `TRUSTED_PROPOSERS` — `aitbc-blockchain-node.env`, `blockchain-island.env`
- `TRUSTED_RECEIPT_KEY_IDS` — `blockchain.env`
- `TRUST_X_WALLET_ADDRESS` — `aitbc-blockchain-rpc.env`
- `WALLET_DIR` — `node.env`
- `WALLET_PORT` — `blockchain.env`
- `WORKERS` — `blockchain.env`

### coordinator/agent api (44)

- `ADMIN_API_KEYS` — `aitbc-coordinator-api-override.env`
- `ADMIN_WALLET_ADDRESSES` — `aitbc-coordinator-api-override.env`
- `AGENT_COORDINATOR_BIND_HOST` — `aitbc-agent-coordinator.env`
- `AGENT_COORDINATOR_BIND_PORT` — `aitbc-agent-coordinator.env`
- `AGENT_DB_PATH` — `aitbc-agent-coordinator.env`
- `AGENT_ECONOMICS_OPERATOR_KEY` — `aitbc-coordinator-api.env`
- `AGENT_MSG_SIGNATURE_MODE` — `aitbc-agent-coordinator.env`
- `ALLOW_ORIGINS` — `aitbc-coordinator-api-override.env`
- `BOND_SLASH_DOWNTIME_COOLDOWN_SECONDS` — `aitbc-coordinator-api.env`
- `BOND_SLASH_PRIVATE_KEY` — `aitbc-coordinator-api.env`
- `BOND_SLASH_TX_FEE` — `aitbc-coordinator-api.env`
- `CHAIN_RPC_API_KEY` — `aitbc-coordinator-api-override.env`
- `CLIENT_API_KEYS` — `aitbc-coordinator-api-override.env`
- `COIN_REQUEST_AUTO_BUDGET_PER_HOUR` — `aitbc-agent-coordinator.env`
- `CONFIDENTIAL_TEE_ENABLED` — `aitbc-coordinator-api.env`
- `COORDINATOR_BOND_MIN_AMOUNT` — `aitbc-coordinator-api.env`
- `COORDINATOR_ENABLE_ZK_VERIFICATION` — `aitbc-coordinator-api.env`
- `COORDINATOR_ZK_HIGH_VALUE_THRESHOLD` — `aitbc-coordinator-api.env`
- `COORDINATOR_ZK_REQUIRE` — `aitbc-coordinator-api.env`
- `DATABASE_ADAPTER` — `aitbc-coordinator-api.env`
- `DEFAULT_CHAIN_ID` — `aitbc-agent-coordinator.env`, `aitbc-gpu.env`
- `ENERGY_MAX_RATE_AGE_SECONDS` — `aitbc-coordinator-api.env`
- `ENERGY_PRICING_CHAIN_ID` — `aitbc-coordinator-api.env`
- `ENERGY_PRICING_CONTRACT_ADDRESS` — `aitbc-coordinator-api.env`
- `ENVIRONMENT` — `aitbc-coordinator-api-override.env`
- `ESCROW_RECONCILER_BATCH_SIZE` — `aitbc-coordinator-api.env`
- `ESCROW_RECONCILER_ENABLED` — `aitbc-coordinator-api.env`
- `ESCROW_RECONCILER_INTERVAL_SECONDS` — `aitbc-coordinator-api.env`
- `ESCROW_RECONCILER_MIN_AGE_SECONDS` — `aitbc-coordinator-api.env`
- `ETH_RPC_URL` — `aitbc-bridge-monitor.env`, `aitbc-coordinator-api.env`, `exchange.env`
- `FAUCET_ADDRESS` — `aitbc-agent-coordinator.env`
- `FAUCET_PRIVATE_KEY` — `aitbc-agent-coordinator.env`
- `GENESIS_PRIVATE_KEY` — `aitbc-agent-coordinator.env`
- `ISLAND_IPFS_HUB_HOST` — `aitbc-coordinator-api.env`
- `ISLAND_IPFS_HUB_PEER_ID` — `aitbc-coordinator-api.env`
- `JWT_NO_EXPIRATION` — `aitbc-coordinator-api-override.env`
- `MAX_MEDIA_UPLOAD_BYTES` — `aitbc-coordinator-api.env`
- `MEDIA_STORAGE_DIR` — `aitbc-coordinator-api.env`
- `MINER_API_KEYS` — `aitbc-coordinator-api.env`
- `NATIVE_ENERGY_PRICING` — `aitbc-coordinator-api.env`
- `RECEIPT_ATTESTATION_KEY_HEX` — `aitbc-coordinator-api-override.env`
- `RECEIPT_SIGNING_KEY_HEX` — `aitbc-coordinator-api-override.env`
- `TASK_PAYMENT_ESCROW_ENABLED` — `aitbc-agent-coordinator.env`
- `TRADING_API_KEY` — `aitbc-coordinator-api.env`, `aitbc-trading.env`

### bridge/monitor (20)

- `AIT_USD_FIXED_PRICE` — `aitbc-bridge-monitor.env`
- `BRIDGE_ADMIN_ADDRESS` — `bridge-validator-keys.env`
- `BRIDGE_ADMIN_PRIVATE_KEY_SOURCE` — `blockchain-island.env`, `bridge-reg-run.env`, `bridge-validator-keys.env`
- `BRIDGE_CONTRACT_ADDRESS` — `aitbc-bridge-monitor.env`
- `BRIDGE_ETH_ADDRESS` — `aitbc-bridge-monitor.env`, `aitbc-exchange.env`
- `BRIDGE_FUNDING_SOURCES` — `aitbc-bridge-monitor.env`
- `BRIDGE_LOW_FLOAT_AIT` — `aitbc-bridge-monitor.env`
- `BRIDGE_MAX_PAYOUT_AIT` — `aitbc-bridge-monitor.env`
- `BRIDGE_MAX_PAYOUT_FRACTION` — `aitbc-bridge-monitor.env`
- `BRIDGE_PAYOUT_ADDRESS` — `aitbc-bridge-monitor.env`
- `BRIDGE_PAYOUT_PRIVATE_KEY` — `aitbc-bridge-monitor.env`
- `BRIDGE_POLL_INTERVAL` — `aitbc-bridge-monitor.env`, `exchange.env`
- `BRIDGE_RPC_URLS` — `bridge-validator-keys.env`
- `BRIDGE_VALIDATOR_ADDRESS_1` — `bridge-validator-keys.env`
- `BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1` — `bridge-reg-run.env`, `bridge-validator-keys.env`
- `BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_2` — `bridge-reg-run.env`
- `CACHE_MONITOR_SKIP_HIT_RATE` — `aitbc-cache-monitor.env`
- `ETH_NETWORK` — `aitbc-bridge-monitor.env`, `exchange.env`
- `EXCHANGE_SETTLEMENT_ENABLED` — `aitbc-bridge-monitor.env`, `aitbc-exchange.env`, `exchange.env`
- `MIN_ETH_DEPOSIT` — `aitbc-bridge-monitor.env`, `exchange.env`

### secrets/api-key files (72)

- `AGENT_COORDINATOR_URL` — `aitbc-market.env`, `aitbc-marketplace.env`
- `AGENT_EXECUTOR_ENABLED` — `aitbc-miner.env`
- `AITBC_API_KEY` — `aitbc-cli.env`, `aitbc-island-subscription-check.env`
- `AITBC_WALLET_DIR` — `aitbc-island-subscription-check.env`
- `AIT_SELL_ESCROW` — `aitbc-exchange.env`, `exchange.env`
- `API_GATEWAY_BIND_HOST` — `aitbc-api-gateway.env`
- `API_GATEWAY_KEY` — `aitbc-api-gateway.env`
- `API_KEY` — `aitbc-market.env`, `aitbc-marketplace.env`
- `API_KEY_HASH_SECRET` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `BLOCKCHAIN_API_KEY` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `BLOCKCHAIN_RPC_API_KEY` — `aitbc-edge.env`, `aitbc-market.env`, `aitbc-marketplace.env` …
- `BLOCKCHAIN_RPC_API_KEY_PEERS` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `BRIDGE_DB_PATH` — `exchange.env`
- `BRIDGE_ENABLED` — `exchange.env`
- `BRIDGE_FEE_RATE` — `exchange.env`
- `BRIDGE_WITHDRAW_ENABLED` — `exchange.env`
- `COORDINATOR_API_KEY` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `COORDINATOR_BASE_URL` — `aitbc-wallet.env`
- `COORDINATOR_URL` — `aitbc-island-subscription-check.env`, `aitbc-miner.env`
- `DATABASE_URL` — `aitbc-exchange.env`, `aitbc-pool-hub.env`, `aitbc-wallet.env`
- `DB_HOST` — `aitbc-governance.env`
- `DB_NAME` — `aitbc-governance.env`
- `DB_PASS` — `aitbc-governance.env`
- `DB_PORT` — `aitbc-governance.env`
- `DB_TYPE` — `aitbc-governance.env`
- `DB_USER` — `aitbc-governance.env`
- `DEFAULT_RATE_LIMIT` — `security.env`
- `DEFAULT_RATE_PERIOD` — `security.env`
- `DEFAULT_ROLE` — `security.env`
- `EDGE_WORKER_EXECUTOR` — `aitbc-edge.env`
- `ENABLE_AUTHENTICATION` — `security.env`
- `ENABLE_AUTHORIZATION` — `security.env`
- `ENABLE_RATE_LIMITING` — `security.env`
- `ENABLE_RBAC` — `security.env`
- `ENABLE_SECURITY_HEADERS` — `security.env`
- `ETH_WALLET_ADDRESS` — `exchange.env`
- `ETH_WALLET_PRIVATE_KEY` — `aitbc-wallet.env`
- `EXCHANGE_API_KEY` — `aitbc-exchange.env`, `exchange.env`
- `GATEWAY_REQUIRED_SERVICES` — `aitbc-api-gateway.env`
- `GOVERNANCE_DEFAULT_CHAIN_ID` — `aitbc-governance.env`
- `GOVERNANCE_ENABLE_ONCHAIN_SUBMISSION` — `aitbc-governance.env`
- `GOVERNANCE_POOLHUB_API_KEY` — `aitbc-governance.env`
- `GOVERNANCE_PROPOSER_PRIVATE_KEY` — `aitbc-governance.env`
- `GOVERNANCE_TIMELOCK_BLOCKS` — `aitbc-governance.env`
- `GOVERNANCE_VOTING_PERIOD_BLOCKS` — `aitbc-governance.env`
- `GPU_API_KEY` — `aitbc-gpu.env`
- `HSTS_MAX_AGE` — `security.env`
- `ISLAND_WALLET` — `aitbc-island-subscription-check.env`
- `JWT_ALGORITHM` — `security.env`
- `JWT_SECRET` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `JWT_SECRET_KEY` — `aitbc-edge.env`, `security.env`
- `JWT_TOKEN_EXPIRY` — `security.env`
- `MINER_API_KEY` — `aitbc-miner.env`
- `MINER_AUTH_TOKEN` — `aitbc-miner.env`
- `MINER_ENDPOINT` — `aitbc-miner.env`
- `MINER_MAX_CONCURRENT_JOBS` — `aitbc-miner.env`
- `MINER_WALLET_ADDRESS` — `aitbc-miner.env`
- `POOL_HUB_URL` — `aitbc-miner.env`
- `REDIS_URL` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `REQUIRE_AUTH_FOR_PUBLIC_ENDPOINTS` — `security.env`
- `SECRET_KEY` — `blockchain-secrets-island.env`, `blockchain-secrets.env`
- `SELL_ESCROW_ENABLED` — `exchange.env`
- `SELL_ESCROW_FUNDING_SOURCES` — `exchange.env`
- `SELL_TREASURY_ADDRESS` — `exchange.env`
- `TEE_ENCLAVE_ID` — `aitbc-miner.env`
- `TEE_SIGNING_KEY_FILE` — `aitbc-miner.env`
- `TRADING_DEFAULT_CHAIN_ID` — `aitbc-trading.env`
- `TRADING_GOSSIP_BROADCAST_URL` — `aitbc-trading.env`
- `TRADING_LEASE_TRACKER_REDIS_URL` — `aitbc-trading.env`
- `VALID_API_KEYS` — `security.env`
- `WALLET_AUTH_ENABLED` — `aitbc-wallet.env`
- `WALLET_IMPORT_PASSWORD` — `blockchain-secrets.env`

### infra/other (49)

- `AITBC_HEARTBEAT_URL` — `prometheus-watch.env`
- `AITBC_WATCH_METRICS_FILE` — `prometheus-watch.env`
- `AITBC_WATCH_NOTIFY_CLICK` — `prometheus-watch.env`
- `AITBC_WATCH_NOTIFY_FORMAT` — `prometheus-watch.env`
- `AITBC_WATCH_NOTIFY_MIN_SEVERITY` — `prometheus-watch.env`
- `AITBC_WATCH_NOTIFY_TOKEN` — `prometheus-watch.env`
- `AITBC_WATCH_NOTIFY_TOPIC` — `prometheus-watch.env`
- `AITBC_WATCH_NOTIFY_URL` — `prometheus-watch.env`
- `AITBC_WATCH_REMIND_INTERVAL` — `prometheus-watch.env`
- `AITBC_WATCH_SILENCE_FILE` — `prometheus-watch.env`
- `CACHE_ACCOUNT_TTL` — `cache.env`
- `CACHE_BLOCKCHAIN_TTL` — `cache.env`
- `CACHE_DEFAULT_TTL` — `cache.env`
- `CACHE_ENABLED` — `cache.env`
- `CACHE_EVICTION_POLICY` — `cache.env`
- `CACHE_MAX_MEMORY` — `cache.env`
- `CACHE_SERVICE_TTL` — `cache.env`
- `CHAIN_SYNC_SOURCES` — `node-island.env`
- `FFMPEG_GPU_DEVICE` — `ffmpeg.env`
- `FFMPEG_HW_ACCEL` — `ffmpeg.env`
- `FFMPEG_PORT` — `ffmpeg.env`
- `ISLAND_IPFS_ANNOUNCE` — `aitbc-island-ipfs.env`
- `ISLAND_IPFS_BOOTSTRAP` — `aitbc-island-ipfs.env`
- `ISLAND_IPFS_HUB` — `aitbc-island-ipfs.env`
- `OPS_AUDIT_LOG` — `ops-signer.env`
- `OPS_FEE_UNITS` — `ops-signer.env`
- `OPS_LEDGER_PATH` — `ops-signer.env`
- `OPS_MAX_PER_DAY` — `ops-signer.env`
- `OPS_MAX_PER_TX` — `ops-signer.env`
- `OPS_SIGNER_ALLOW_FILE` — `ops-signer.env`
- `OPS_SIGNER_GROUP` — `ops-signer.env`
- `OPS_SIGNER_RPC_URL` — `ops-signer.env`
- `OPS_SIGNER_SOCK` — `ops-signer.env`
- `OPS_WALLET_PATH` — `ops-signer.env`
- `PERIODIC_SYNC_ENABLED` — `node-island.env`
- `POOLHUB_COORDINATOR_BILLING_URL` — `aitbc-pool-hub.env`
- `POOLHUB_COORDINATOR_SHARED_SECRET` — `aitbc-pool-hub.env`
- `POOLHUB_DEFAULT_CHAIN_ID` — `aitbc-pool-hub.env`
- `POOLHUB_ENABLE_SLA_COLLECTION` — `aitbc-pool-hub.env`
- `POOLHUB_POSTGRES_DSN` — `aitbc-pool-hub.env`
- `POOLHUB_REDIS_URL` — `aitbc-pool-hub.env`
- `REDISCLI_AUTH` — `aitbc-backup.env`, `redis.env`
- `REDIS_ADDR` — `prometheus-redis-exporter.env`
- `REDIS_DB` — `cache.env`
- `REDIS_HOST` — `cache.env`
- `REDIS_PASSWORD` — `cache.env`, `prometheus-redis-exporter.env`
- `REDIS_PORT` — `cache.env`
- `WEBSITE_CHAIN_ID` — `website.env`
- `WEBSITE_DOMAIN` — `website.env`

## 4. Signing/verifying env-pair separation audit (template §9.4)

Design rule: the signing side (private key) and verifying side
(public address) of an authority pair live in different env files —
the verifier runs where the key must never exist. An address appearing
next to its own key on the *signer's* file is inherent (a signer
always knows its own address); the question the audit answers is
**which files hold the KEY**, and whether any is a file that should
not.

| pair | files holding the key | assessment |
|---|---|---|
| AGENT_ECONOMICS_OPERATOR | `hub/hub1: aitbc-coordinator-api.env` only | **split holds** — key nowhere outside the coordinator env; `OPERATOR_ADDRESS` in rpc envs fleet-wide (the designed shape) |
| BOND_SLASH | `hub/hub1: aitbc-coordinator-api.env` only | **split holds** — key only where slashing is signed; `BOND_SLASH_AUTHORITY_ADDRESS` in `blockchain.env` + coordinator env |
| BRIDGE_RELEASE | `hub: node.env + rpc-override.env`; `hub1/node1: rpc-island.env` | **flag** — `BRIDGE_RELEASE_PRIVATE_KEY` sits in *island* rpc envs on hub1 and node1 in addition to hub's primary files. Island units either still sign bridge releases (worth verifying) or carry a stale copy — mark for §2 custody review |
| ESCROW_RELEASE | `hub: rpc-override.env` only | **split holds** — `ESCROW_RELEASE_ADDRESS` in node/rpc envs fleet-wide |
| BRIDGE_PAYOUT | `hub/hub1: aitbc-bridge-monitor.env` only | **split holds** — monitor signs and reads its own address on the same file; expected |
| BRIDGE_ADMIN / BRIDGE_VALIDATOR | `bridge-validator-keys.env` on **all five hosts** | **flag** — admin + validator private keys staged fleet-wide, not only where bridge signing happens. Deliberate validator participation or over-staging — a §2 custody-gate review item (the file name suggests deliberate staging; confirm the consuming services) |
| GENESIS / FAUCET | `hub: aitbc-agent-coordinator.env` only | **split holds** — key only on hub; `GENESIS_ADDRESS`/`FAUCET_ADDRESS` appear in ~100 envs fleet-wide as configured peers (the bc-2-era baked identity — on bc-3 these rows become (R-pending) rewrites) |
| ENERGY_OPERATOR | **no key anywhere** | **flag** — `ENERGY_OPERATOR_ADDRESS` configured on hub/hub1 coordinator/rpc envs but no `ENERGY_OPERATOR_*KEY` exists on the fleet — either a dead-key finding (the bc-2 executor-key shape) or the key is deliberately off-fleet. §2 custody row. |

**Net verdict**: the §9.4 design holds for every pair whose signing
service has a clear home. Three items graduate to the §2 custody gate
as bc-3 inputs: island-env bridge-release keys, fleet-wide
`bridge-validator-keys.env`, and the keyless `ENERGY_OPERATOR_ADDRESS`.

## 5. bc-3 env template skeleton (per host class)

Carry-forward file list with disposition tags; values pending the
remaining #410 R-items are marked `(R-pending)`:

- all hosts: `aitbc-blockchain-node.env`, `aitbc-blockchain-rpc.env`,
  `blockchain.env` — chain id `(R-pending)`, heights → 1,
  `ESCROW_FEE_RECIPIENT` → treasury SOT (decided #489, address
  mint pending), gossip/peering repointed, `MEMPOOL_BACKEND=database`
- validators (hub, hub1, node1, node2): `VALIDATOR_SET`/`VALIDATOR_KEYS`
  rotated set `(R-pending)`, `PROPOSER_ID`/`PROPOSER_KEY` per host
- hub: `aitbc-agent-coordinator.env`, `aitbc-coordinator-api.env`,
  `aitbc-bridge-monitor.env`, `aitbc-governance.env` — service
  keys verbatim; custody-gated signing keys per §2
- staging: `BRIDGE_LOCKS_PAUSED=true` in the launch env (decided)
- service-api envs (`*-api-gateway`, `*-market`, `*-exchange`,
  `*-miner`, `*-trading`, `*-secrets`, `*-wallet`, `security`) —
  migrate-verbatim; rotation is a separate decision
- `*_island` envs — investigate which island services persist

## 6. What this does NOT decide

- The ~295-var enumeration gap is listed, not patched — extending
  `fleet-config-check.sh`'s `VARS`/`EFF_VARS` is a separate decision
  (changes what the checker diffs and alerts on).
- Every `*_PRIVATE_KEY`/custody row points at the reset-2 §2 gate;
  nothing here moves or proofs a key.
- `*_island` envs' fate depends on which island services carry to
  bc-3 — an open item, marked investigate.
