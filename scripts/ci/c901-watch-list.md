# C901 / except-ratchet watch-list

Machine-regenerated reference for reviewers (#1517). **Do not edit by hand** —
run `scripts/ci/render-c901-watch-list.py > scripts/ci/c901-watch-list.md`.

## Gates

- **C901:** `scripts/ci/check-c901-ratchet.sh` (pre-push hook `c901-complexity-ratchet`)
- **BLE001/S110:** `scripts/ci/check-except-ratchet.sh` (pre-push hook `except-ratchet`)
- Baseline files: 175 C901 files, 488 except files

## Tier 1 — brushing complexity 11–12 in hot files

Extract a helper before adding branches to these functions.

- `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` `prepare_phase` @ 303 (complexity 11, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` `_validate_governance_payload` @ 133 (complexity 11, baseline 5)
- `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py` `get_or_load_contract` @ 714 (complexity 11, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py` `settlement_legs_from_chain` @ 293 (complexity 11, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py` `initiate_transfer` @ 172 (complexity 11, baseline 4)
- `apps/blockchain-node/src/aitbc_chain/main.py` `_load_private_key_from_keystore` @ 94 (complexity 11, baseline 5)
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py` `_build_lock_tx` @ 403 (complexity 11, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_settlement_sweeper.py` `_escrow_legs_by_job` @ 428 (complexity 11, baseline 5)
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_settlement_sweeper.py` `change_owed_candidates` @ 830 (complexity 11, baseline 5)
- `apps/blockchain-node/src/aitbc_chain/state/block_deltas.py` `_mark_domain_row_orphaned` @ 1093 (complexity 11, baseline 4)
- `apps/blockchain-node/src/aitbc_chain/sync_block_import.py` `_resolve_fork` @ 1415 (complexity 11, baseline 3)
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py` `_attach_zk_proof` @ 129 (complexity 11, baseline 3)
- `apps/market/src/market_service/services/market_service.py` `register_software_service` @ 1283 (complexity 11, baseline 5)
- `apps/trading/examples/main.py` `execute_trade` @ 387 (complexity 11, baseline 3)
- `cli/aitbc_cli/commands/agent.py` `send` @ 244 (complexity 11, baseline 3)
- `mcp-server/aitbc_mcp_server.py` `_load_hosts_config` @ 77 (complexity 11, baseline 3)
- `scripts/utils/verify-db-schema.py` `_auto_discover` @ 632 (complexity 11, baseline 3)
- `scripts/utils/verify-db-schema.py` `main` @ 751 (complexity 11, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` `propose_and_wait` @ 213 (complexity 12, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py` `release_payment` @ 925 (complexity 12, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/p2p_network.py` `_mempool_sync_loop` @ 204 (complexity 12, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/sync_bulk.py` `_parallel_bulk_import` @ 665 (complexity 12, baseline 3)
- `apps/trading/examples/main.py` `process_market_order` @ 321 (complexity 12, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py` `refund_transfer` @ 615 (complexity 13, baseline 4)
- `apps/blockchain-node/src/aitbc_chain/main.py` `process_txs` @ 337 (complexity 13, baseline 5)
- `apps/blockchain-node/src/aitbc_chain/mempool.py` `add` @ 240 (complexity 13, baseline 3)
- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` `_validate_stake_release_locks` @ 1625 (complexity 13, baseline 9)
- `apps/market/src/market_service/services/market_service.py` `list_software_services` @ 919 (complexity 13, baseline 5)

## Tier 2 — highest C901 baseline counts (per-file ceiling)

- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py`: 9
- `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`: 5
- `apps/blockchain-node/src/aitbc_chain/main.py`: 5
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_settlement_sweeper.py`: 5
- `apps/market/src/market_service/services/market_service.py`: 5
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py`: 4
- `apps/blockchain-node/src/aitbc_chain/state/block_deltas.py`: 4
- `apps/bridge-monitor/src/bridge_monitor/main.py`: 4
- `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py`: 3
- `apps/blockchain-node/src/aitbc_chain/consensus/remote_attestation.py`: 3
- `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py`: 3
- `apps/blockchain-node/src/aitbc_chain/mempool.py`: 3
- `apps/blockchain-node/src/aitbc_chain/p2p_network.py`: 3
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py`: 3
- `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py`: 3
- `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`: 3
- `apps/blockchain-node/src/aitbc_chain/sync_block_import.py`: 3
- `apps/blockchain-node/src/aitbc_chain/sync_bulk.py`: 3
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py`: 3
- `apps/trading/examples/main.py`: 3

## Tier 3 — deep complexity (ratchet-blind to in-function growth)

- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` `validate_transaction` @ 1769 (complexity 151)
- `apps/blockchain-node/src/aitbc_chain/sync_block_import.py` `_append_block` @ 487 (complexity 72)
- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` `apply_transaction` @ 2505 (complexity 60)
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py` `create_escrow` @ 1414 (complexity 58)
- `apps/blockchain-node/src/aitbc_chain/state/pure_state_transition.py` `compute_state_delta` @ 582 (complexity 52)
- `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py` `gossip_websocket` @ 449 (complexity 44)
- `apps/blockchain-node/src/aitbc_chain/consensus/remote_attestation.py` `_handle_request` @ 813 (complexity 43)
- `apps/blockchain-node/src/aitbc_chain/p2p_network.py` `_listen_to_stream` @ 489 (complexity 42)
- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` `_handle_bond_transaction` @ 3243 (complexity 41)
- `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` `_process_txs_sequential` @ 2997 (complexity 40)
- `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py` `_validate_transaction_admission` @ 110 (complexity 39)
- `apps/blockchain-node/src/aitbc_chain/consensus/remote_attestation.py` `collect_attestations` @ 2353 (complexity 37)
- `scripts/lint/no_float_money.py` `_violations_in` @ 424 (complexity 34)
- `apps/blockchain-node/src/aitbc_chain/consensus/remote_attestation.py` `_v9_check_transactions` @ 1193 (complexity 33)
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py` `_release_settle_locked_impl` @ 2055 (complexity 33)
- `apps/bridge-monitor/src/bridge_monitor/admin.py` `main` @ 97 (complexity 33)
- `scripts/monitoring/bridge-payout-audit.py` `main` @ 123 (complexity 33)
- `apps/coordinator-api/src/coordinator_api/contexts/market/routers/market_gpu.py` `buy_gpu` @ 658 (complexity 31)
- `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py` `subscription_websocket` @ 773 (complexity 30)
- `apps/trading/src/trading_service/routers/subscriptions.py` `offer_subscription_websocket` @ 117 (complexity 30)
- `apps/blockchain-node/src/aitbc_chain/app.py` `lifespan` @ 410 (complexity 29)
- `apps/blockchain-node/src/aitbc_chain/sync_bulk.py` `_resolve_fork_with_peer` @ 299 (complexity 29)
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py` `_validate_proof` @ 1294 (complexity 28)
- `apps/blockchain-node/src/aitbc_chain/state/state_transition.py` `build_escrow_context` @ 1091 (complexity 28)
- `cli/aitbc_cli/commands/dashboard.py` `shop` @ 374 (complexity 28)

## C901 volume by top-level path

- `apps`: 160
- `cli`: 45
- `scripts`: 32
- `aitbc`: 12
- `tests`: 7
- `mcp-server`: 4
- `packages`: 2
- `cli_gap_analysis.py`: 1

## Except baseline hotspots (BLE001/S110)

- `cli/aitbc_cli/commands/agent_sdk.py`: 32
- `apps/agent-coordinator/src/agent_app/storage/message_storage.py`: 29
- `cli/aitbc_cli/commands/edge.py`: 27
- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`: 26
- `dev/gpu/gpu_acceleration/apple_silicon_provider.py`: 22
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py`: 21
- `apps/coordinator-api/src/coordinator_api/contexts/market/routers/global_market_integration.py`: 21
- `cli/aitbc_cli/commands/ai.py`: 21
- `cli/aitbc_cli/commands/bridge.py`: 20
- `cli/aitbc_cli/commands/trade.py`: 20
- `apps/blockchain-node/src/aitbc_chain/main.py`: 19
- `cli/aitbc_cli/commands/exchange/trading.py`: 19
- `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`: 18
- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/services/manager.py`: 18
- `cli/aitbc_cli/core/market.py`: 18
