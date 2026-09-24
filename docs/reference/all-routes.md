# All Routes — consolidated service route reference

> **Generated** from live `/openapi.json` specs. Regenerate on each node with:
>
> ```bash
> /opt/aitbc/venv/bin/python /opt/aitbc/scripts/docs/gen_all_routes.py \
>     --node <node-name> --services "name:port,name:port,..."
> ```
>
> Current inventories: hub —
> `api-gateway:8201,blockchain-rpc:8202,coordinator-api:8203,explorer:8100,`   # check-ports: ignore
> `market:8102,trading:8104,governance:8105,exchange:8106,`   # check-ports: ignore
> `agent-coordinator:8107,wallet:8108,pool-hub:8210`; GPU/edge node —   # check-ports: ignore
> `gpu:8101,edge-api:8111,ffmpeg:8230,hermes:8270`.   # check-ports: ignore
>
> This lists every route each service exposes on its **local port**. To reach
> them publicly, apply the nginx/gateway prefix map in
> [`../infrastructure/PRODUCTION_ARCHITECTURE.md`](../infrastructure/PRODUCTION_ARCHITECTURE.md#-public-api-surface-nginx-on-hubhub1)
> — e.g. a coordinator route `/v1/jobs` is served publicly at `/c/v1/jobs`
> (fleet path) or `/api/v1/coordinator/jobs` (gateway, `X-Gateway-Key` required).

## Routes on hub

### api-gateway (`:8201`, AITBC API Gateway v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health |
| `GET` | `/ready` | Ready |
| `GET` | `/services` | List Services |
| `GET` | `/v2` | Api V2 Index |
| `DELETE` | `/{path}` | Proxy Request |
| `GET` | `/{path}` | Proxy Request |
| `OPTIONS` | `/{path}` | Proxy Request |
| `PATCH` | `/{path}` | Proxy Request |
| `POST` | `/{path}` | Proxy Request |
| `PUT` | `/{path}` | Proxy Request |

### blockchain-rpc (`:8202`, AITBC Blockchain Node vv0.2.2)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/ready` | Readiness probe |
| `GET` | `/rpc/account/{address}` | Get account information |
| `GET` | `/rpc/accounts` | List accounts |
| `GET` | `/rpc/accounts/{address}` | Get account information (alias) |
| `POST` | `/rpc/agent-staking/agents/{agent_wallet}/distribute` | Record earnings distribution memo |
| `POST` | `/rpc/agent-staking/claim-rewards` | Record rewards claim memo |
| `POST` | `/rpc/agent-staking/performance` | Record performance update memo |
| `POST` | `/rpc/agent-staking/stake` | Create agent stake |
| `POST` | `/rpc/agent-staking/stake/{stake_id}/add` | Add to agent stake |
| `POST` | `/rpc/agent-staking/stake/{stake_id}/complete` | Complete agent stake |
| `POST` | `/rpc/agent-staking/stake/{stake_id}/unbond` | Unbond agent stake |
| `GET` | `/rpc/ai/job/{job_id}` | Get AI job by ID |
| `POST` | `/rpc/ai/job/{job_id}/cancel` | Cancel AI job |
| `GET` | `/rpc/ai/jobs` | List AI jobs |
| `GET` | `/rpc/ai/stats` | AI service statistics |
| `POST` | `/rpc/ai/submit` | Submit AI job |
| `GET` | `/rpc/balance/{address}` | Get detailed balance breakdown |
| `GET` | `/rpc/balance/{address}/reconcile` | Reconcile balance |
| `GET` | `/rpc/block` | Get a block (head by default, or by query height) |
| `GET` | `/rpc/block/{height}` | Get block by height (singular alias) |
| `GET` | `/rpc/blocks-range` | Get blocks in height range |
| `GET` | `/rpc/blocks/{height}` | Get block by height |
| `GET` | `/rpc/bond/provider/{provider}` | List bonds for a provider |
| `GET` | `/rpc/bond/{bond_id}` | Get bond by ID |
| `POST` | `/rpc/bounty/deploy` | Deploy bounty lock |
| `POST` | `/rpc/bounty/{bounty_id}/dispute` | Dispute bounty submission |
| `POST` | `/rpc/bounty/{bounty_id}/expire` | Expire bounty and refund |
| `POST` | `/rpc/bounty/{bounty_id}/submit` | Submit bounty solution |
| `POST` | `/rpc/bounty/{bounty_id}/verify` | Verify bounty submission |
| `GET` | `/rpc/bridge/balance/{chain_id}` | Get bridge balance for a chain |
| `POST` | `/rpc/bridge/batch/confirm` | Batch confirm multiple transfers |
| `POST` | `/rpc/bridge/batch/lock` | Batch lock multiple transfers |
| `POST` | `/rpc/bridge/block-headers` | Store a remote chain block header |
| `GET` | `/rpc/bridge/block-headers/{chain_id}/{height}` | Get a block header with finality status |
| `POST` | `/rpc/bridge/confirm` | Confirm and release cross-chain transfer |
| `GET` | `/rpc/bridge/health` | Bridge health check |
| `POST` | `/rpc/bridge/lock` | Lock funds for cross-chain transfer |
| `GET` | `/rpc/bridge/oracle/status` | Bridge oracle/verification status |
| `GET` | `/rpc/bridge/pending` | List pending bridge transfers |
| `GET` | `/rpc/bridge/security/status` | Bridge security status |
| `POST` | `/rpc/bridge/settlement/create` | Create cross-chain escrow |
| `GET` | `/rpc/bridge/settlement/{escrow_id}` | Get escrow details |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/dispute` | File a dispute for an escrow |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/execute` | Execute trade on destination |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/extend-timeout` | Extend escrow timeout |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/lock` | Lock escrow funds |
| `GET` | `/rpc/bridge/settlement/{escrow_id}/proofs` | Get proof chain |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/refund` | Refund escrow |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/resolve` | Resolve a dispute |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/settle` | Settle escrow with secret |
| `GET` | `/rpc/bridge/settlement/{escrow_id}/status` | Get escrow status |
| `POST` | `/rpc/bridge/settlement/{escrow_id}/verify` | Verify lock proof |
| `GET` | `/rpc/bridge/status/{transfer_id}` | Get transfer status (alias) |
| `GET` | `/rpc/bridge/transfer/{transfer_id}` | Get transfer status |
| `GET` | `/rpc/bridge/transfer/{transfer_id}/proof` | Build bridge transfer proof |
| `POST` | `/rpc/bridge/unlock` | Refund a pending bridge transfer |
| `POST` | `/rpc/bridge/validators/register` | Register a bridge validator |
| `GET` | `/rpc/bridge/validators/{chain_id}` | Get validator set for a chain |
| `GET` | `/rpc/chain/head` | Get current chain head (compatibility alias) |
| `GET` | `/rpc/chains` | List all chain instances (v0.6.4) |
| `POST` | `/rpc/chains/start` | Start a secondary chain (v0.6.4) |
| `POST` | `/rpc/chains/stop` | Stop a secondary chain (v0.6.4) |
| `GET` | `/rpc/consensus/slashing-history` | Get slashing history |
| `GET` | `/rpc/consensus/status` | Get consensus status |
| `GET` | `/rpc/consensus/validators` | List consensus validators |
| `GET` | `/rpc/contracts` | List deployed contracts |
| `POST` | `/rpc/contracts/call` | Call a contract method |
| `POST` | `/rpc/contracts/deploy` | Deploy a smart contract |
| `POST` | `/rpc/contracts/deploy/messaging` | Deploy messaging contract |
| `GET` | `/rpc/contracts/messaging/agents/{agent_id}/reputation` | Get agent reputation |
| `POST` | `/rpc/contracts/messaging/messages/post` | Post message |
| `GET` | `/rpc/contracts/messaging/messages/search` | Search messages |
| `POST` | `/rpc/contracts/messaging/messages/{message_id}/moderate` | Moderate message |
| `POST` | `/rpc/contracts/messaging/messages/{message_id}/vote` | Vote on message |
| `GET` | `/rpc/contracts/messaging/state` | Get messaging contract state |
| `GET` | `/rpc/contracts/messaging/topics` | Get forum topics |
| `POST` | `/rpc/contracts/messaging/topics/create` | Create forum topic |
| `GET` | `/rpc/contracts/messaging/topics/{topic_id}/messages` | Get topic messages |
| `POST` | `/rpc/contracts/verify` | Verify a ZK proof |
| `POST` | `/rpc/cross-chain/bridge` | Create cross-chain bridge transaction |
| `GET` | `/rpc/cross-chain/bridge/{bridge_id}` | Get cross-chain bridge status |
| `GET` | `/rpc/cross-chain/pools` | Show cross-chain liquidity pools |
| `GET` | `/rpc/cross-chain/rates` | Get cross-chain exchange rates |
| `GET` | `/rpc/cross-chain/stats` | Show cross-chain trading statistics |
| `GET` | `/rpc/cross-chain/swap/{swap_id}` | Get cross-chain swap status |
| `GET` | `/rpc/cross-chain/swaps` | List cross-chain swaps |
| `GET` | `/rpc/disputes/active` | Get all active disputes |
| `GET` | `/rpc/disputes/arbitrators` | Get all authorized arbitrators |
| `POST` | `/rpc/disputes/arbitrators/authorize` | Authorize an arbitrator (admin only) |
| `GET` | `/rpc/disputes/arbitrators/{arbitrator_address}` | Get disputes for an arbitrator |
| `POST` | `/rpc/disputes/evidence` | Submit evidence for a dispute |
| `POST` | `/rpc/disputes/file` | File a new dispute |
| `GET` | `/rpc/disputes/user/{user_address}` | Get disputes for a user |
| `POST` | `/rpc/disputes/verify-evidence` | Verify evidence (arbitrator only) |
| `POST` | `/rpc/disputes/vote` | Submit arbitration vote (arbitrator only) |
| `GET` | `/rpc/disputes/{dispute_id}` | Get dispute details |
| `GET` | `/rpc/disputes/{dispute_id}/evidence` | Get evidence for a dispute |
| `GET` | `/rpc/disputes/{dispute_id}/votes` | Get arbitration votes for a dispute |
| `GET` | `/rpc/edge/info/{node_id}` | Query edge node registration |
| `POST` | `/rpc/edge/register` | Register edge node on-chain |
| `POST` | `/rpc/escrow/create` | Create escrow for a job |
| `GET` | `/rpc/escrow/{job_id}` | Get escrow state |
| `POST` | `/rpc/escrow/{job_id}/refund` | Refund escrow to buyer |
| `POST` | `/rpc/escrow/{job_id}/release` | Release escrow to provider |
| `POST` | `/rpc/eth_getLogs` | Query smart contract event logs |
| `GET` | `/rpc/export-chain` | Export full chain state |
| `POST` | `/rpc/force-sync` | Force reorg to specified peer |
| `GET` | `/rpc/genesis_allocations` | Get genesis allocations from blockchain |
| `POST` | `/rpc/governance/proposal` | Create governance proposal |
| `GET` | `/rpc/governance/proposal/{proposal_id}` | Get governance proposal |
| `POST` | `/rpc/governance/proposal/{proposal_id}/execute` | Execute governance proposal |
| `POST` | `/rpc/governance/vote` | Cast governance vote |
| `POST` | `/rpc/gpu/allocate` | Allocate GPU on-chain |
| `GET` | `/rpc/gpu/allocations/{gpu_id}` | Query GPU allocations |
| `GET` | `/rpc/gpu/info/{gpu_id}` | Query GPU registration |
| `POST` | `/rpc/gpu/register` | Register GPU on-chain |
| `GET` | `/rpc/gpus` | List all registered GPUs |
| `GET` | `/rpc/head` | Get current chain head |
| `POST` | `/rpc/heartbeat` | Extend subscription lease via heartbeat |
| `GET` | `/rpc/height` | Get current chain height |
| `POST` | `/rpc/identity/register` | Register agent identity |
| `POST` | `/rpc/identity/verify` | Verify agent identity |
| `GET` | `/rpc/identity/{agent_id}` | Get agent identity |
| `POST` | `/rpc/import-chain` | Import chain state |
| `POST` | `/rpc/importBlock` | Import a block |
| `GET` | `/rpc/info` | Get blockchain information |
| `GET` | `/rpc/islands` | List all islands |
| `POST` | `/rpc/islands/bridge` | Request a bridge to another island |
| `POST` | `/rpc/islands/join` | Join an island |
| `POST` | `/rpc/islands/leave` | Leave an island |
| `GET` | `/rpc/islands/{island_id}` | Get island details |
| `POST` | `/rpc/join` | Self-serve island join: issue a node-bound peer key |
| `DELETE` | `/rpc/lease/{node_id}` | Revoke subscription lease |
| `GET` | `/rpc/lease/{node_id}` | Get lease status for a subscriber |
| `POST` | `/rpc/liquidity/build-claim` | Build an unsigned LIQUIDITY_CLAIM transaction |
| `POST` | `/rpc/liquidity/build-deposit` | Build an unsigned LIQUIDITY_DEPOSIT transaction |
| `POST` | `/rpc/liquidity/build-withdraw` | Build an unsigned LIQUIDITY_WITHDRAW transaction |
| `GET` | `/rpc/liquidity/pools` | List liquidity pools |
| `GET` | `/rpc/liquidity/pools/{pool_id}` | Get a liquidity pool |
| `GET` | `/rpc/liquidity/stakes/{address}` | List liquidity stakes for an address |
| `GET` | `/rpc/liquidity/stakes/{stake_id}/rewards` | Get pending rewards for a stake |
| `POST` | `/rpc/market/create` | Create market listing |
| `DELETE` | `/rpc/market/listing/{listing_id}` | Delete market listing |
| `GET` | `/rpc/market/listing/{listing_id}` | Get market listing by ID |
| `GET` | `/rpc/market/listings` | List market items |
| `GET` | `/rpc/mempool` | Get pending transactions |
| `GET` | `/rpc/mining/miners` | List active miners |
| `POST` | `/rpc/mining/start` | Start mining |
| `GET` | `/rpc/mining/status` | Get mining status |
| `POST` | `/rpc/mining/stop` | Stop mining |
| `GET` | `/rpc/network-info` | Get network information for joining |
| `GET` | `/rpc/pending` | Get pending transactions |
| `GET` | `/rpc/proposer` | Get the current block proposer address |
| `POST` | `/rpc/register-account` | Report the on-chain state of an account address |
| `POST` | `/rpc/staking/stake` | Stake tokens |
| `POST` | `/rpc/staking/unstake` | Unstake tokens |
| `GET` | `/rpc/staking/{address}` | Get staking info |
| `GET` | `/rpc/state/delta` | Get state delta between two heights |
| `GET` | `/rpc/state/snapshot` | Get full account state snapshot |
| `GET` | `/rpc/status` | Get node status (alias for /info) |
| `POST` | `/rpc/subscribe` | Register for block subscription with lease |
| `GET` | `/rpc/subscribers` | Get all valid subscribers |
| `POST` | `/rpc/swap` | Create cross-chain swap |
| `GET` | `/rpc/sync/config` | Get sync optimization configuration (v0.6.2) |
| `POST` | `/rpc/transaction` | Submit transaction |
| `GET` | `/rpc/transaction/{tx_hash}` | Get one transaction by hash |
| `GET` | `/rpc/transactions` | Query transactions |
| `POST` | `/rpc/transactions/market` | Submit market transaction |
| `GET` | `/rpc/transactions/market/match` | Match market offers |
| `GET` | `/v1/account/{address}` | Get account information |
| `GET` | `/v1/accounts` | List accounts |
| `GET` | `/v1/accounts/{address}` | Get account information (alias) |
| `POST` | `/v1/agent-staking/agents/{agent_wallet}/distribute` | Record earnings distribution memo |
| `POST` | `/v1/agent-staking/claim-rewards` | Record rewards claim memo |
| `POST` | `/v1/agent-staking/performance` | Record performance update memo |
| `POST` | `/v1/agent-staking/stake` | Create agent stake |
| `POST` | `/v1/agent-staking/stake/{stake_id}/add` | Add to agent stake |
| `POST` | `/v1/agent-staking/stake/{stake_id}/complete` | Complete agent stake |
| `POST` | `/v1/agent-staking/stake/{stake_id}/unbond` | Unbond agent stake |
| `GET` | `/v1/ai/job/{job_id}` | Get AI job by ID |
| `POST` | `/v1/ai/job/{job_id}/cancel` | Cancel AI job |
| `GET` | `/v1/ai/jobs` | List AI jobs |
| `GET` | `/v1/ai/stats` | AI service statistics |
| `POST` | `/v1/ai/submit` | Submit AI job |
| `GET` | `/v1/balance/{address}` | Get detailed balance breakdown |
| `GET` | `/v1/balance/{address}/reconcile` | Reconcile balance |
| `GET` | `/v1/block` | Get a block (head by default, or by query height) |
| `GET` | `/v1/block/{height}` | Get block by height (singular alias) |
| `GET` | `/v1/blocks-range` | Get blocks in height range |
| `GET` | `/v1/blocks/{height}` | Get block by height |
| `GET` | `/v1/bond/provider/{provider}` | List bonds for a provider |
| `GET` | `/v1/bond/{bond_id}` | Get bond by ID |
| `POST` | `/v1/bounty/deploy` | Deploy bounty lock |
| `POST` | `/v1/bounty/{bounty_id}/dispute` | Dispute bounty submission |
| `POST` | `/v1/bounty/{bounty_id}/expire` | Expire bounty and refund |
| `POST` | `/v1/bounty/{bounty_id}/submit` | Submit bounty solution |
| `POST` | `/v1/bounty/{bounty_id}/verify` | Verify bounty submission |
| `GET` | `/v1/bridge/balance/{chain_id}` | Get bridge balance for a chain |
| `POST` | `/v1/bridge/batch/confirm` | Batch confirm multiple transfers |
| `POST` | `/v1/bridge/batch/lock` | Batch lock multiple transfers |
| `POST` | `/v1/bridge/block-headers` | Store a remote chain block header |
| `GET` | `/v1/bridge/block-headers/{chain_id}/{height}` | Get a block header with finality status |
| `POST` | `/v1/bridge/confirm` | Confirm and release cross-chain transfer |
| `GET` | `/v1/bridge/health` | Bridge health check |
| `POST` | `/v1/bridge/lock` | Lock funds for cross-chain transfer |
| `GET` | `/v1/bridge/oracle/status` | Bridge oracle/verification status |
| `GET` | `/v1/bridge/pending` | List pending bridge transfers |
| `GET` | `/v1/bridge/security/status` | Bridge security status |
| `POST` | `/v1/bridge/settlement/create` | Create cross-chain escrow |
| `GET` | `/v1/bridge/settlement/{escrow_id}` | Get escrow details |
| `POST` | `/v1/bridge/settlement/{escrow_id}/dispute` | File a dispute for an escrow |
| `POST` | `/v1/bridge/settlement/{escrow_id}/execute` | Execute trade on destination |
| `POST` | `/v1/bridge/settlement/{escrow_id}/extend-timeout` | Extend escrow timeout |
| `POST` | `/v1/bridge/settlement/{escrow_id}/lock` | Lock escrow funds |
| `GET` | `/v1/bridge/settlement/{escrow_id}/proofs` | Get proof chain |
| `POST` | `/v1/bridge/settlement/{escrow_id}/refund` | Refund escrow |
| `POST` | `/v1/bridge/settlement/{escrow_id}/resolve` | Resolve a dispute |
| `POST` | `/v1/bridge/settlement/{escrow_id}/settle` | Settle escrow with secret |
| `GET` | `/v1/bridge/settlement/{escrow_id}/status` | Get escrow status |
| `POST` | `/v1/bridge/settlement/{escrow_id}/verify` | Verify lock proof |
| `GET` | `/v1/bridge/status/{transfer_id}` | Get transfer status (alias) |
| `GET` | `/v1/bridge/transfer/{transfer_id}` | Get transfer status |
| `GET` | `/v1/bridge/transfer/{transfer_id}/proof` | Build bridge transfer proof |
| `POST` | `/v1/bridge/unlock` | Refund a pending bridge transfer |
| `POST` | `/v1/bridge/validators/register` | Register a bridge validator |
| `GET` | `/v1/bridge/validators/{chain_id}` | Get validator set for a chain |
| `GET` | `/v1/chain/head` | Get current chain head (compatibility alias) |
| `GET` | `/v1/chains` | List all chain instances (v0.6.4) |
| `POST` | `/v1/chains/start` | Start a secondary chain (v0.6.4) |
| `POST` | `/v1/chains/stop` | Stop a secondary chain (v0.6.4) |
| `GET` | `/v1/consensus/slashing-history` | Get slashing history |
| `GET` | `/v1/consensus/status` | Get consensus status |
| `GET` | `/v1/consensus/validators` | List consensus validators |
| `GET` | `/v1/contracts` | List deployed contracts |
| `POST` | `/v1/contracts/call` | Call a contract method |
| `POST` | `/v1/contracts/deploy` | Deploy a smart contract |
| `POST` | `/v1/contracts/deploy/messaging` | Deploy messaging contract |
| `GET` | `/v1/contracts/messaging/agents/{agent_id}/reputation` | Get agent reputation |
| `POST` | `/v1/contracts/messaging/messages/post` | Post message |
| `GET` | `/v1/contracts/messaging/messages/search` | Search messages |
| `POST` | `/v1/contracts/messaging/messages/{message_id}/moderate` | Moderate message |
| `POST` | `/v1/contracts/messaging/messages/{message_id}/vote` | Vote on message |
| `GET` | `/v1/contracts/messaging/state` | Get messaging contract state |
| `GET` | `/v1/contracts/messaging/topics` | Get forum topics |
| `POST` | `/v1/contracts/messaging/topics/create` | Create forum topic |
| `GET` | `/v1/contracts/messaging/topics/{topic_id}/messages` | Get topic messages |
| `POST` | `/v1/contracts/verify` | Verify a ZK proof |
| `POST` | `/v1/cross-chain/bridge` | Create cross-chain bridge transaction |
| `GET` | `/v1/cross-chain/bridge/{bridge_id}` | Get cross-chain bridge status |
| `GET` | `/v1/cross-chain/pools` | Show cross-chain liquidity pools |
| `GET` | `/v1/cross-chain/rates` | Get cross-chain exchange rates |
| `GET` | `/v1/cross-chain/stats` | Show cross-chain trading statistics |
| `GET` | `/v1/cross-chain/swap/{swap_id}` | Get cross-chain swap status |
| `GET` | `/v1/cross-chain/swaps` | List cross-chain swaps |
| `GET` | `/v1/disputes/active` | Get all active disputes |
| `GET` | `/v1/disputes/arbitrators` | Get all authorized arbitrators |
| `POST` | `/v1/disputes/arbitrators/authorize` | Authorize an arbitrator (admin only) |
| `GET` | `/v1/disputes/arbitrators/{arbitrator_address}` | Get disputes for an arbitrator |
| `POST` | `/v1/disputes/evidence` | Submit evidence for a dispute |
| `POST` | `/v1/disputes/file` | File a new dispute |
| `GET` | `/v1/disputes/user/{user_address}` | Get disputes for a user |
| `POST` | `/v1/disputes/verify-evidence` | Verify evidence (arbitrator only) |
| `POST` | `/v1/disputes/vote` | Submit arbitration vote (arbitrator only) |
| `GET` | `/v1/disputes/{dispute_id}` | Get dispute details |
| `GET` | `/v1/disputes/{dispute_id}/evidence` | Get evidence for a dispute |
| `GET` | `/v1/disputes/{dispute_id}/votes` | Get arbitration votes for a dispute |
| `GET` | `/v1/edge/info/{node_id}` | Query edge node registration |
| `POST` | `/v1/edge/register` | Register edge node on-chain |
| `POST` | `/v1/eth_getLogs` | Query smart contract event logs |
| `GET` | `/v1/export-chain` | Export full chain state |
| `POST` | `/v1/force-sync` | Force reorg to specified peer |
| `GET` | `/v1/genesis_allocations` | Get genesis allocations from blockchain |
| `POST` | `/v1/governance/proposal` | Create governance proposal |
| `GET` | `/v1/governance/proposal/{proposal_id}` | Get governance proposal |
| `POST` | `/v1/governance/proposal/{proposal_id}/execute` | Execute governance proposal |
| `POST` | `/v1/governance/vote` | Cast governance vote |
| `POST` | `/v1/gpu/allocate` | Allocate GPU on-chain |
| `GET` | `/v1/gpu/allocations/{gpu_id}` | Query GPU allocations |
| `GET` | `/v1/gpu/info/{gpu_id}` | Query GPU registration |
| `POST` | `/v1/gpu/register` | Register GPU on-chain |
| `GET` | `/v1/gpus` | List all registered GPUs |
| `GET` | `/v1/head` | Get current chain head |
| `POST` | `/v1/heartbeat` | Extend subscription lease via heartbeat |
| `GET` | `/v1/height` | Get current chain height |
| `POST` | `/v1/identity/register` | Register agent identity |
| `POST` | `/v1/identity/verify` | Verify agent identity |
| `GET` | `/v1/identity/{agent_id}` | Get agent identity |
| `POST` | `/v1/import-chain` | Import chain state |
| `POST` | `/v1/importBlock` | Import a block |
| `GET` | `/v1/info` | Get blockchain information |
| `GET` | `/v1/islands` | List all islands |
| `POST` | `/v1/islands/bridge` | Request a bridge to another island |
| `POST` | `/v1/islands/join` | Join an island |
| `POST` | `/v1/islands/leave` | Leave an island |
| `GET` | `/v1/islands/{island_id}` | Get island details |
| `POST` | `/v1/join` | Self-serve island join: issue a node-bound peer key |
| `DELETE` | `/v1/lease/{node_id}` | Revoke subscription lease |
| `GET` | `/v1/lease/{node_id}` | Get lease status for a subscriber |
| `POST` | `/v1/liquidity/build-claim` | Build an unsigned LIQUIDITY_CLAIM transaction |
| `POST` | `/v1/liquidity/build-deposit` | Build an unsigned LIQUIDITY_DEPOSIT transaction |
| `POST` | `/v1/liquidity/build-withdraw` | Build an unsigned LIQUIDITY_WITHDRAW transaction |
| `GET` | `/v1/liquidity/pools` | List liquidity pools |
| `GET` | `/v1/liquidity/pools/{pool_id}` | Get a liquidity pool |
| `GET` | `/v1/liquidity/stakes/{address}` | List liquidity stakes for an address |
| `GET` | `/v1/liquidity/stakes/{stake_id}/rewards` | Get pending rewards for a stake |
| `GET` | `/v1/mempool` | Get pending transactions |
| `GET` | `/v1/mining/miners` | List active miners |
| `POST` | `/v1/mining/start` | Start mining |
| `GET` | `/v1/mining/status` | Get mining status |
| `POST` | `/v1/mining/stop` | Stop mining |
| `GET` | `/v1/network-info` | Get network information for joining |
| `GET` | `/v1/pending` | Get pending transactions |
| `GET` | `/v1/proposer` | Get the current block proposer address |
| `POST` | `/v1/register-account` | Report the on-chain state of an account address |
| `POST` | `/v1/staking/stake` | Stake tokens |
| `POST` | `/v1/staking/unstake` | Unstake tokens |
| `GET` | `/v1/staking/{address}` | Get staking info |
| `GET` | `/v1/state/delta` | Get state delta between two heights |
| `GET` | `/v1/state/snapshot` | Get full account state snapshot |
| `GET` | `/v1/status` | Get node status (alias for /info) |
| `POST` | `/v1/subscribe` | Register for block subscription with lease |
| `GET` | `/v1/subscribers` | Get all valid subscribers |
| `POST` | `/v1/swap` | Create cross-chain swap |
| `GET` | `/v1/sync/config` | Get sync optimization configuration (v0.6.2) |
| `POST` | `/v1/transaction` | Submit transaction |
| `GET` | `/v1/transaction/{tx_hash}` | Get one transaction by hash |
| `GET` | `/v1/transactions` | Query transactions |
| `POST` | `/v1/transactions/market` | Submit market transaction |
| `GET` | `/v1/transactions/market/match` | Match market offers |

### coordinator-api (`:8203`, AITBC Coordinator API v1.0.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Service healthcheck |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/metrics` | Live JSON metrics for dashboard consumption |
| `GET` | `/rate-limit-metrics` | Rate Limit Metrics |
| `GET` | `/v1/accounts/{address}` | Get Account |
| `GET` | `/v1/admin/debug-settings` | Debug settings |
| `POST` | `/v1/admin/debug/create-test-miner` | Create a test miner for debugging |
| `POST` | `/v1/admin/disputes/auto-adjudicate` | Auto-adjudicate disputes with spot-check evidence (S-3) |
| `POST` | `/v1/admin/disputes/{job_id}/resolve` | Resolve a disputed job payment |
| `GET` | `/v1/admin/jobs` | List jobs |
| `GET` | `/v1/admin/miners` | List miners |
| `POST` | `/v1/admin/payments/{job_id}/retry-release` | Reset and retry a terminally blocked escrow release |
| `GET` | `/v1/admin/stats` | Get coordinator stats |
| `GET` | `/v1/admin/status` | Get system status |
| `GET` | `/v1/admin/sweepers` | List background sweeper tasks, their status and configuration |
| `GET` | `/v1/admin/test-key` | Test API key validation |
| `POST` | `/v1/agent-creativity/capabilities` | Create Creative Capability |
| `GET` | `/v1/agent-creativity/capabilities/{agent_id}` | List Agent Creative Capabilities |
| `POST` | `/v1/agent-creativity/capabilities/{capability_id}/enhance` | Enhance Creativity |
| `POST` | `/v1/agent-creativity/capabilities/{capability_id}/evaluate` | Evaluate Creation |
| `POST` | `/v1/agent-creativity/ideation/generate` | Generate Ideas |
| `POST` | `/v1/agent-creativity/synthesis/cross-domain` | Synthesize Cross Domain |
| `GET` | `/v1/agent-identity/address/{chain_address}/resolve/{chain_id}` | Resolve Address To Agent |
| `GET` | `/v1/agent-identity/chains/supported` | Get Supported Chains |
| `POST` | `/v1/agent-identity/identities` | Create Agent Identity |
| `POST` | `/v1/agent-identity/identities/batch-verify` | Batch Verify Identities |
| `POST` | `/v1/agent-identity/identities/import` | Import Agent Identity |
| `GET` | `/v1/agent-identity/identities/search` | Search Agent Identities |
| `GET` | `/v1/agent-identity/identities/{agent_id}` | Get Agent Identity |
| `PUT` | `/v1/agent-identity/identities/{agent_id}` | Update Agent Identity |
| `GET` | `/v1/agent-identity/identities/{agent_id}/cross-chain/mapping` | Get Cross Chain Mapping |
| `POST` | `/v1/agent-identity/identities/{agent_id}/cross-chain/register` | Register Cross Chain Identity |
| `PUT` | `/v1/agent-identity/identities/{agent_id}/cross-chain/{chain_id}` | Update Cross Chain Mapping |
| `POST` | `/v1/agent-identity/identities/{agent_id}/cross-chain/{chain_id}/verify` | Verify Cross Chain Identity |
| `POST` | `/v1/agent-identity/identities/{agent_id}/deactivate` | Deactivate Agent Identity |
| `POST` | `/v1/agent-identity/identities/{agent_id}/export` | Export Agent Identity |
| `POST` | `/v1/agent-identity/identities/{agent_id}/migrate` | Migrate Agent Identity |
| `GET` | `/v1/agent-identity/identities/{agent_id}/resolve/{chain_id}` | Resolve Agent Identity |
| `POST` | `/v1/agent-identity/identities/{agent_id}/sync-reputation` | Sync Agent Reputation |
| `GET` | `/v1/agent-identity/identities/{agent_id}/wallets` | Get All Agent Wallets |
| `POST` | `/v1/agent-identity/identities/{agent_id}/wallets` | Create Agent Wallet |
| `DELETE` | `/v1/agent-identity/identities/{agent_id}/wallets/{chain_id}` | Delete Agent Wallet |
| `GET` | `/v1/agent-identity/identities/{agent_id}/wallets/{chain_id}/balance` | Get Wallet Balance |
| `POST` | `/v1/agent-identity/identities/{agent_id}/wallets/{chain_id}/export` | Export Agent Wallet |
| `POST` | `/v1/agent-identity/identities/{agent_id}/wallets/{chain_id}/sign` | Sign Message |
| `GET` | `/v1/agent-identity/identities/{agent_id}/wallets/{chain_id}/transactions` | Get Wallet Transaction History |
| `POST` | `/v1/agent-identity/identities/{agent_id}/wallets/{chain_id}/transactions` | Execute Wallet Transaction |
| `POST` | `/v1/agent-identity/registry/cleanup-expired` | Cleanup Expired Verifications |
| `GET` | `/v1/agent-identity/registry/health` | Get Registry Health |
| `GET` | `/v1/agent-identity/registry/statistics` | Get Registry Statistics |
| `GET` | `/v1/agent-performance/analytics/{agent_id}` | Get Performance Analytics |
| `POST` | `/v1/agent-performance/capabilities` | Create Capability |
| `GET` | `/v1/agent-performance/capabilities/{agent_id}` | List Agent Capabilities |
| `POST` | `/v1/agent-performance/meta-learning/models` | Create Meta Learning Model |
| `POST` | `/v1/agent-performance/meta-learning/models/{model_id}/adapt` | Adapt Model To Task |
| `POST` | `/v1/agent-performance/optimize` | Optimize Performance |
| `POST` | `/v1/agent-performance/profiles` | Create Performance Profile |
| `GET` | `/v1/agent-performance/profiles/{agent_id}` | Get Performance Profile |
| `POST` | `/v1/agent-performance/profiles/{agent_id}/metrics` | Update Performance Metrics |
| `GET` | `/v1/agent-performance/resources` | List Resource Allocations |
| `POST` | `/v1/agent-performance/resources/allocate` | Allocate Resources |
| `POST` | `/v1/agent-performance/resources/{allocation_id}/deallocate` | Deallocate Resource |
| `GET` | `/v1/agents/executions` | List Executions |
| `GET` | `/v1/agents/executions/{execution_id}/status` | Get Execution Status |
| `POST` | `/v1/agents/integration/deployments/config` | Create Deployment Config |
| `GET` | `/v1/agents/integration/deployments/configs` | List Deployment Configs |
| `GET` | `/v1/agents/integration/deployments/configs/{config_id}` | Get Deployment Config |
| `GET` | `/v1/agents/integration/deployments/instances` | List Deployment Instances |
| `GET` | `/v1/agents/integration/deployments/instances/{instance_id}` | Get Deployment Instance |
| `POST` | `/v1/agents/integration/deployments/{config_id}/deploy` | Deploy Workflow |
| `GET` | `/v1/agents/integration/deployments/{config_id}/health` | Get Deployment Health |
| `POST` | `/v1/agents/integration/deployments/{config_id}/rollback` | Rollback Deployment |
| `POST` | `/v1/agents/integration/deployments/{config_id}/scale` | Scale Deployment |
| `POST` | `/v1/agents/integration/integrations/zk/{execution_id}` | Integrate With Zk System |
| `GET` | `/v1/agents/integration/metrics/deployments/{deployment_id}` | Get Deployment Metrics |
| `GET` | `/v1/agents/integration/production/alerts` | Get Production Alerts |
| `GET` | `/v1/agents/integration/production/dashboard` | Get Production Dashboard |
| `POST` | `/v1/agents/integration/production/deploy` | Deploy To Production |
| `GET` | `/v1/agents/integration/production/health` | Get Production Health |
| `GET` | `/v1/agents/security/audit-logs` | List Audit Logs |
| `GET` | `/v1/agents/security/audit-logs/{audit_id}` | Get Audit Log |
| `POST` | `/v1/agents/security/executions/{execution_id}/security-monitor` | Monitor Execution Security |
| `GET` | `/v1/agents/security/policies` | List Security Policies |
| `POST` | `/v1/agents/security/policies` | Create Security Policy |
| `DELETE` | `/v1/agents/security/policies/{policy_id}` | Delete Security Policy |
| `GET` | `/v1/agents/security/policies/{policy_id}` | Get Security Policy |
| `PUT` | `/v1/agents/security/policies/{policy_id}` | Update Security Policy |
| `POST` | `/v1/agents/security/sandbox/{execution_id}/cleanup` | Cleanup Sandbox |
| `POST` | `/v1/agents/security/sandbox/{execution_id}/create` | Create Sandbox |
| `GET` | `/v1/agents/security/sandbox/{execution_id}/monitor` | Monitor Sandbox |
| `GET` | `/v1/agents/security/scan` | Scan Security |
| `GET` | `/v1/agents/security/security-dashboard` | Get Security Dashboard |
| `GET` | `/v1/agents/security/security-stats` | Get Security Statistics |
| `GET` | `/v1/agents/security/trust-scores` | List Trust Scores |
| `GET` | `/v1/agents/security/trust-scores/{entity_type}/{entity_id}` | Get Trust Score |
| `POST` | `/v1/agents/security/trust-scores/{entity_type}/{entity_id}/update` | Update Trust Score |
| `POST` | `/v1/agents/security/validate-workflow/{workflow_id}` | Validate Workflow Security |
| `GET` | `/v1/agents/supported` | Get Supported Agents |
| `GET` | `/v1/agents/test` | Test Agent Endpoint |
| `GET` | `/v1/agents/workflows` | List Workflows |
| `POST` | `/v1/agents/workflows` | Create Workflow |
| `DELETE` | `/v1/agents/workflows/{workflow_id}` | Delete Workflow |
| `GET` | `/v1/agents/workflows/{workflow_id}` | Get Workflow |
| `PUT` | `/v1/agents/workflows/{workflow_id}` | Update Workflow |
| `POST` | `/v1/agents/workflows/{workflow_id}/cancel` | Cancel Workflow |
| `POST` | `/v1/agents/workflows/{workflow_id}/execute` | Execute Workflow |
| `GET` | `/v1/agents/workflows/{workflow_id}/executions` | List Workflow Executions |
| `GET` | `/v1/agents/{agent_wallet}/apy` | Get Agent Apy |
| `POST` | `/v1/agents/{agent_wallet}/distribute-earnings` | Distribute Agent Earnings |
| `GET` | `/v1/agents/{agent_wallet}/metrics` | Get Agent Metrics |
| `POST` | `/v1/agents/{agent_wallet}/performance` | Update Agent Performance |
| `GET` | `/v1/agents/{agent_wallet}/staking-pool` | Get Staking Pool |
| `POST` | `/v1/auth/nonce` | Get Login Nonce |
| `GET` | `/v1/blocks` | Get blockchain blocks |
| `GET` | `/v1/blocks/hash/{block_hash}` | Get Block By Hash |
| `GET` | `/v1/blocks/{height}` | Get Block |
| `POST` | `/v1/bounty/claim` | Claim a bounty |
| `POST` | `/v1/bounty/create` | Create a new bounty |
| `GET` | `/v1/bounty/health` | Health check for bounty service |
| `GET` | `/v1/bounty/list` | List available bounties |
| `GET` | `/v1/bounty/stats` | Get bounty statistics |
| `POST` | `/v1/bounty/submit` | Submit solution |
| `POST` | `/v1/bounty/verify` | Verify solution |
| `GET` | `/v1/bounty/{bounty_id}` | Get bounty details |
| `GET` | `/v1/confidential/access/logs` | Get Access Logs |
| `POST` | `/v1/confidential/keys/register` | Register Encryption Key |
| `POST` | `/v1/confidential/keys/rotate` | Rotate Encryption Key |
| `POST` | `/v1/confidential/payments` | Create Confidential Payment |
| `GET` | `/v1/confidential/status` | Get Confidential Status |
| `POST` | `/v1/confidential/transactions` | Create Confidential Transaction |
| `GET` | `/v1/confidential/transactions/{transaction_id}` | Get Confidential Transaction |
| `POST` | `/v1/confidential/transactions/{transaction_id}/access` | Access Confidential Data |
| `POST` | `/v1/confidential/transactions/{transaction_id}/audit` | Audit Access Confidential Data |
| `POST` | `/v1/cross-chain/bridge/create-request` | Create Bridge Request |
| `GET` | `/v1/cross-chain/bridge/liquidity-pools` | Get Liquidity Pools |
| `GET` | `/v1/cross-chain/bridge/request/{bridge_request_id}` | Get Bridge Request Status |
| `POST` | `/v1/cross-chain/bridge/request/{bridge_request_id}/cancel` | Cancel Bridge Request |
| `GET` | `/v1/cross-chain/bridge/statistics` | Get Bridge Statistics |
| `GET` | `/v1/cross-chain/bridge/whitelist` | Get Bridge Whitelist |
| `POST` | `/v1/cross-chain/bridge/whitelist/add` | Add Bridge Whitelist Entry |
| `GET` | `/v1/cross-chain/chains/supported` | Get Supported Chains |
| `GET` | `/v1/cross-chain/chains/{chain_id}/info` | Get Chain Info |
| `GET` | `/v1/cross-chain/config` | Get Cross Chain Config |
| `GET` | `/v1/cross-chain/health` | Get Cross Chain Health |
| `GET` | `/v1/cross-chain/transactions/history` | Get Transaction History |
| `POST` | `/v1/cross-chain/transactions/optimize-routing` | Optimize Transaction Routing |
| `GET` | `/v1/cross-chain/transactions/statistics` | Get Transaction Statistics |
| `POST` | `/v1/cross-chain/transactions/submit` | Submit Transaction |
| `POST` | `/v1/cross-chain/wallets/create` | Create Enhanced Wallet |
| `POST` | `/v1/cross-chain/wallets/verify-signature` | Verify Signature |
| `GET` | `/v1/cross-chain/wallets/{wallet_address}/balance` | Get Wallet Balance |
| `POST` | `/v1/cross-chain/wallets/{wallet_address}/sign` | Sign Message |
| `GET` | `/v1/cross-chain/wallets/{wallet_address}/transactions` | Get Wallet Transaction History |
| `POST` | `/v1/cross-chain/wallets/{wallet_address}/transactions` | Execute Wallet Transaction |
| `GET` | `/v1/developer-platform/analytics/overview` | Get Platform Overview |
| `GET` | `/v1/developer-platform/bounties` | List Bounties |
| `POST` | `/v1/developer-platform/bounties` | Create Bounty |
| `GET` | `/v1/developer-platform/bounties/my-submissions` | Get My Submissions |
| `GET` | `/v1/developer-platform/bounties/stats` | Get Bounty Statistics |
| `GET` | `/v1/developer-platform/bounties/{bounty_id}` | Get Bounty Details |
| `POST` | `/v1/developer-platform/bounties/{bounty_id}/review` | Review Bounty Submission |
| `POST` | `/v1/developer-platform/bounties/{bounty_id}/submit` | Submit Bounty Solution |
| `POST` | `/v1/developer-platform/certifications` | Grant Certification |
| `GET` | `/v1/developer-platform/certifications/types` | Get Certification Types |
| `GET` | `/v1/developer-platform/certifications/verify/{certification_id}` | Verify Certification |
| `GET` | `/v1/developer-platform/certifications/{wallet_address}` | Get Developer Certifications |
| `POST` | `/v1/developer-platform/claim-rewards` | Claim Rewards |
| `GET` | `/v1/developer-platform/health` | Get Platform Health |
| `GET` | `/v1/developer-platform/hubs` | Get Regional Hubs |
| `POST` | `/v1/developer-platform/hubs` | Create Regional Hub |
| `GET` | `/v1/developer-platform/hubs/{hub_id}/developers` | Get Hub Developers |
| `GET` | `/v1/developer-platform/leaderboard` | Get Leaderboard |
| `GET` | `/v1/developer-platform/profile/{wallet_address}` | Get Developer Profile |
| `PUT` | `/v1/developer-platform/profile/{wallet_address}` | Update Developer Profile |
| `POST` | `/v1/developer-platform/register` | Register Developer |
| `GET` | `/v1/developer-platform/rewards/{address}` | Get Rewards |
| `POST` | `/v1/developer-platform/stake` | Stake On Developer |
| `GET` | `/v1/developer-platform/staking-stats` | Get Staking Statistics |
| `GET` | `/v1/developer-platform/staking/{address}` | Get Staking Info |
| `GET` | `/v1/developer-platform/stats/{wallet_address}` | Get Developer Stats |
| `POST` | `/v1/developer-platform/unstake` | Unstake Tokens |
| `GET` | `/v1/developers` | List Developers |
| `POST` | `/v1/developers` | Register Developer |
| `GET` | `/v1/developers/{wallet_address}` | Get Developer |
| `PUT` | `/v1/developers/{wallet_address}` | Update Developer |
| `GET` | `/v1/disputes/` | List disputes |
| `POST` | `/v1/disputes/arbitrators/register` | Register as arbitrator |
| `POST` | `/v1/disputes/evidence` | Submit evidence |
| `POST` | `/v1/disputes/file` | File a dispute |
| `GET` | `/v1/disputes/health` | Health check |
| `POST` | `/v1/disputes/vote` | Cast arbitrator vote |
| `GET` | `/v1/disputes/{dispute_id}` | Get dispute details |
| `GET` | `/v1/economic-proposals` | List Proposals |
| `POST` | `/v1/economic-proposals` | Create Proposal |
| `GET` | `/v1/economic-proposals/{proposal_id}` | Get Proposal |
| `POST` | `/v1/economic-proposals/{proposal_id}/execute` | Execute Proposal |
| `POST` | `/v1/economic-proposals/{proposal_id}/votes` | Vote On Proposal |
| `POST` | `/v1/edge-gpu/discover` | Discover Edge Gpus |
| `GET` | `/v1/edge-gpu/metrics` | Get All Metrics |
| `POST` | `/v1/edge-gpu/metrics` | Submit Metrics |
| `GET` | `/v1/edge-gpu/metrics/{gpu_id}` | Get Gpu Metrics |
| `POST` | `/v1/edge-gpu/optimize` | Optimize Inference |
| `GET` | `/v1/edge-gpu/profiles` | List Profiles |
| `POST` | `/v1/exchange/confirm-payment/{payment_id}` | Confirm Payment |
| `POST` | `/v1/exchange/create-payment` | Create Payment |
| `GET` | `/v1/exchange/market-stats` | Get Market Stats |
| `GET` | `/v1/exchange/payment-status/{payment_id}` | Get Payment Status |
| `GET` | `/v1/exchange/rates` | Get Exchange Rates |
| `GET` | `/v1/explorer/addresses` | List address summaries |
| `GET` | `/v1/explorer/blocks` | List recent blocks |
| `GET` | `/v1/explorer/blocks/by-hash/{block_hash}` | Get block details by hash |
| `GET` | `/v1/explorer/receipts` | List job receipts |
| `GET` | `/v1/explorer/transactions` | List recent transactions |
| `GET` | `/v1/explorer/transactions/by-hash/{tx_hash}` | Get transaction details by hash |
| `GET` | `/v1/explorer/transactions/{tx_hash}` | Get transaction details by hash |
| `POST` | `/v1/fhe/add` | Homomorphic addition |
| `POST` | `/v1/fhe/context/generate` | Generate FHE context |
| `GET` | `/v1/fhe/context/{context_id}` | Get context info |
| `POST` | `/v1/fhe/decrypt` | Decrypt data |
| `POST` | `/v1/fhe/encrypt` | Encrypt data |
| `GET` | `/v1/fhe/health` | Health check |
| `POST` | `/v1/fhe/inference` | Encrypted inference |
| `POST` | `/v1/fhe/multiply-scalar` | Homomorphic scalar multiplication |
| `GET` | `/v1/governance-enhanced/analytics/governance` | Get Governance Analytics |
| `GET` | `/v1/governance-enhanced/analytics/regional-health/{region}` | Get Regional Governance Health |
| `GET` | `/v1/governance-enhanced/compliance/check/{user_address}` | Check Compliance Status |
| `GET` | `/v1/governance-enhanced/health` | Get Governance System Health |
| `GET` | `/v1/governance-enhanced/jurisdictions` | Get Supported Jurisdictions |
| `POST` | `/v1/governance-enhanced/profiles/create` | Create Governance Profile |
| `POST` | `/v1/governance-enhanced/profiles/delegate` | Delegate Votes |
| `GET` | `/v1/governance-enhanced/profiles/{user_id}` | Get Governance Profile |
| `GET` | `/v1/governance-enhanced/regional-councils` | Get Regional Councils |
| `POST` | `/v1/governance-enhanced/regional-councils` | Create Regional Council |
| `POST` | `/v1/governance-enhanced/regional-proposals` | Create Regional Proposal |
| `POST` | `/v1/governance-enhanced/regional-proposals/{proposal_id}/vote` | Vote On Regional Proposal |
| `GET` | `/v1/governance-enhanced/staking/calculate-rewards` | Calculate Staking Rewards |
| `POST` | `/v1/governance-enhanced/staking/distribute-rewards/{pool_id}` | Distribute Staking Rewards |
| `GET` | `/v1/governance-enhanced/staking/pools` | Get Developer Staking Pools |
| `POST` | `/v1/governance-enhanced/staking/pools` | Create Staking Pool |
| `GET` | `/v1/governance-enhanced/status` | Get Governance Platform Status |
| `POST` | `/v1/governance-enhanced/treasury/allocate` | Allocate Treasury Funds |
| `GET` | `/v1/governance-enhanced/treasury/balance` | Get Treasury Balance |
| `GET` | `/v1/governance-enhanced/treasury/transactions` | Get Treasury Transactions |
| `POST` | `/v1/governance/analytics/reports` | Generate Transparency Report |
| `POST` | `/v1/governance/profiles` | Init Governance Profile |
| `POST` | `/v1/governance/profiles/{profile_id}/delegate` | Delegate Voting Power |
| `POST` | `/v1/governance/proposals` | Create Proposal |
| `POST` | `/v1/governance/proposals/{proposal_id}/execute` | Execute Proposal |
| `POST` | `/v1/governance/proposals/{proposal_id}/process` | Process Proposal |
| `POST` | `/v1/governance/proposals/{proposal_id}/vote` | Cast Vote |
| `POST` | `/v1/governance/slash-appeals` | Submit Slash Appeal |
| `GET` | `/v1/grants` | List Grants |
| `POST` | `/v1/grants` | Create Grant |
| `GET` | `/v1/grants/{grant_id}` | Get Grant |
| `POST` | `/v1/grants/{grant_id}/disburse` | Disburse Grant |
| `GET` | `/v1/grants/{grant_id}/milestones` | List Milestones |
| `POST` | `/v1/grants/{grant_id}/milestones` | Create Milestone |
| `POST` | `/v1/grants/{grant_id}/process` | Process Grant |
| `POST` | `/v1/grants/{grant_id}/vote` | Vote Grant |
| `POST` | `/v1/hipaa/consent` | Grant Consent |
| `POST` | `/v1/hipaa/consent/{consent_id}/revoke` | Revoke Consent |
| `POST` | `/v1/hipaa/phi/access` | Access Phi |
| `POST` | `/v1/hipaa/phi/delete` | Right To Delete |
| `POST` | `/v1/inference/batch` | Batch inference |
| `POST` | `/v1/inference/generate` | Generate text |
| `POST` | `/v1/inference/generate/stream` | Generate text (streaming) |
| `GET` | `/v1/inference/health` | Health check |
| `GET` | `/v1/inference/models` | List available models |
| `POST` | `/v1/inference/models/{model_name}/pull` | Pull model |
| `POST` | `/v1/ipfs/batch-upload` | Batch Upload Memories |
| `POST` | `/v1/ipfs/create-deal` | Create Filecoin Deal |
| `DELETE` | `/v1/ipfs/delete` | Delete Memory |
| `GET` | `/v1/ipfs/health` | Health Check |
| `POST` | `/v1/ipfs/island/swarm-key` | Get Island Swarm Key |
| `GET` | `/v1/ipfs/list/{agent_id}` | List Agent Memories |
| `POST` | `/v1/ipfs/retrieve` | Retrieve Memory |
| `GET` | `/v1/ipfs/stats` | Get Storage Stats |
| `POST` | `/v1/ipfs/upload` | Upload Memory |
| `GET` | `/v1/islands/` | List Islands |
| `POST` | `/v1/islands/bridge` | Request Bridge |
| `POST` | `/v1/islands/join` | Join Island |
| `POST` | `/v1/islands/leave` | Leave Island |
| `GET` | `/v1/islands/{island_id}` | Get Island |
| `GET` | `/v1/jobs` | List jobs with filtering |
| `POST` | `/v1/jobs` | Submit a job |
| `GET` | `/v1/jobs/history` | Get job history |
| `GET` | `/v1/jobs/{job_id}` | Get job status |
| `POST` | `/v1/jobs/{job_id}/accept` | Accept a result and release payment |
| `POST` | `/v1/jobs/{job_id}/cancel` | Cancel job |
| `GET` | `/v1/jobs/{job_id}/payment` | Get payment for a job |
| `GET` | `/v1/jobs/{job_id}/receipt` | Get latest signed receipt |
| `GET` | `/v1/jobs/{job_id}/receipts` | List signed receipts |
| `POST` | `/v1/jobs/{job_id}/reject` | Reject a result and open a dispute |
| `GET` | `/v1/jobs/{job_id}/result` | Get job result |
| `GET` | `/v1/knowledge/graphs` | List Knowledge Graphs |
| `POST` | `/v1/knowledge/graphs` | Create Knowledge Graph |
| `GET` | `/v1/knowledge/graphs/{graph_id}` | Get Knowledge Graph |
| `POST` | `/v1/knowledge/graphs/{graph_id}/join` | Join Knowledge Graph |
| `POST` | `/v1/knowledge/graphs/{graph_id}/nodes` | Contribute Knowledge |
| `GET` | `/v1/knowledge/graphs/{graph_id}/query` | Query Knowledge Graph |
| `POST` | `/v1/login` | Login User |
| `POST` | `/v1/logout` | Logout User |
| `GET` | `/v1/market/bonds/{bond_id}` | Get a bond record by ID |
| `POST` | `/v1/market/gpu/bid` | Bid Gpu |
| `GET` | `/v1/market/gpu/list` | List Gpus |
| `POST` | `/v1/market/gpu/purchase` | Buy Gpu |
| `POST` | `/v1/market/gpu/quote` | Quote Gpu |
| `POST` | `/v1/market/gpu/register` | Register Gpu |
| `POST` | `/v1/market/gpu/sell` | Sell Gpu |
| `DELETE` | `/v1/market/gpu/{gpu_id}` | Delete Gpu |
| `GET` | `/v1/market/gpu/{gpu_id}` | Get Gpu Details |
| `POST` | `/v1/market/gpu/{gpu_id}/book` | Book Gpu |
| `POST` | `/v1/market/gpu/{gpu_id}/confirm` | Confirm Gpu Booking |
| `POST` | `/v1/market/gpu/{gpu_id}/release` | Release Gpu |
| `GET` | `/v1/market/gpu/{gpu_id}/reviews` | Get Gpu Reviews |
| `POST` | `/v1/market/gpu/{gpu_id}/reviews` | Add Gpu Review |
| `GET` | `/v1/market/miner-offers` | List all miner offers |
| `GET` | `/v1/market/native-energy/floor` | Get Native Energy Floor |
| `POST` | `/v1/market/native-energy/profile` | Register Native Energy Profile |
| `GET` | `/v1/market/native-energy/profile/{resource_id}` | Get Native Energy Profile |
| `GET` | `/v1/market/native-energy/rate` | Get Native Energy Rate |
| `POST` | `/v1/market/native-energy/rate` | Publish Native Energy Rate |
| `GET` | `/v1/market/offers` | List market offers |
| `GET` | `/v1/market/orders` | List Orders |
| `GET` | `/v1/market/plugins` | List market plugins |
| `GET` | `/v1/market/pricing/{model}` | Get Pricing |
| `POST` | `/v1/market/providers/{provider_id}/bonds` | Create or update a provider bond |
| `POST` | `/v1/market/providers/{provider_id}/bonds/lock` | Lock a provider bond |
| `POST` | `/v1/market/providers/{provider_id}/bonds/release` | Release a locked provider bond |
| `POST` | `/v1/market/providers/{provider_id}/bonds/slash` | Slash a provider bond |
| `POST` | `/v1/market/providers/{provider_id}/capacity` | Publish updated provider capacity |
| `GET` | `/v1/market/providers/{provider_id}/eligibility` | Check provider bond eligibility |
| `GET` | `/v1/market/stats` | Get market summary statistics |
| `POST` | `/v1/market/sync-offers` | Create offers from registered miners |
| `GET` | `/v1/media/download/{token}` | Download a media file |
| `POST` | `/v1/media/upload` | Upload a media file |
| `POST` | `/v1/miners/heartbeat` | Send miner heartbeat |
| `POST` | `/v1/miners/poll` | Poll for next job |
| `POST` | `/v1/miners/register` | Register or update miner |
| `POST` | `/v1/miners/{job_id}/fail` | Submit job failure |
| `POST` | `/v1/miners/{job_id}/result` | Submit job result |
| `DELETE` | `/v1/miners/{miner_id}` | Deregister miner |
| `PUT` | `/v1/miners/{miner_id}/capabilities` | Update miner capabilities |
| `POST` | `/v1/miners/{miner_id}/earnings` | Get miner earnings |
| `POST` | `/v1/miners/{miner_id}/jobs` | List jobs for a miner |
| `POST` | `/v1/miners/{miner_id}/jobs/{job_id}/complete` | Complete job execution |
| `POST` | `/v1/miners/{miner_id}/jobs/{job_id}/fail` | Report job failure |
| `GET` | `/v1/ml-zk/circuits` | List Ml Circuits |
| `POST` | `/v1/ml-zk/prove/modular` | Prove Modular Ml |
| `POST` | `/v1/ml-zk/prove/training` | Prove Ml Training |
| `POST` | `/v1/ml-zk/verify/inference` | Verify Ml Inference |
| `POST` | `/v1/ml-zk/verify/training` | Verify Ml Training |
| `GET` | `/v1/monitoring/dashboard` | Enhanced Services Dashboard |
| `GET` | `/v1/monitoring/dashboard/metrics` | System Metrics |
| `GET` | `/v1/monitoring/dashboard/summary` | Services Summary |
| `GET` | `/v1/monitoring/metrics` | Full monitoring metrics |
| `GET` | `/v1/multi-modal-rl/health` | Health |
| `GET` | `/v1/multi-modal-rl/jobs` | List Jobs |
| `POST` | `/v1/multi-modal-rl/jobs` | Submit Job |
| `GET` | `/v1/multi-modal-rl/jobs/{job_id}` | Get Job |
| `POST` | `/v1/multi-modal-rl/jobs/{job_id}/cancel` | Cancel Job |
| `GET` | `/v1/multi-modal-rl/jobs/{job_id}/result` | Get Job Result |
| `GET` | `/v1/offers` | List all market offers (Fixed) |
| `GET` | `/v1/oracle/health` | Health check |
| `GET` | `/v1/oracle/oracle/health` | Oracle health check |
| `POST` | `/v1/oracle/price` | Set price (admin) |
| `GET` | `/v1/oracle/price/{pair}` | Get price for pair |
| `GET` | `/v1/oracle/prices` | Get all prices |
| `POST` | `/v1/payments` | Create payment for a job |
| `POST` | `/v1/payments/send` | Send Payment |
| `GET` | `/v1/payments/{payment_id}` | Get payment details |
| `GET` | `/v1/payments/{payment_id}/receipt` | Get payment receipt |
| `POST` | `/v1/payments/{payment_id}/refund` | Refund payment |
| `POST` | `/v1/payments/{payment_id}/release` | Release payment from escrow |
| `GET` | `/v1/portfolio/health` | Get Portfolio Health |
| `GET` | `/v1/portfolio/summary` | Get Portfolio Summary Only |
| `GET` | `/v1/portfolio/unified` | Get Unified Portfolio |
| `POST` | `/v1/register` | Register User |
| `GET` | `/v1/reputation/cross-chain/analytics` | Get Cross Chain Analytics |
| `POST` | `/v1/reputation/cross-chain/events` | Submit Cross Chain Event |
| `GET` | `/v1/reputation/cross-chain/leaderboard` | Get Cross Chain Leaderboard |
| `GET` | `/v1/reputation/events/{agent_id}` | Get Reputation Events |
| `GET` | `/v1/reputation/feedback/{agent_id}` | Get Agent Feedback |
| `POST` | `/v1/reputation/feedback/{agent_id}` | Add Community Feedback |
| `POST` | `/v1/reputation/job-completion` | Record Job Completion |
| `GET` | `/v1/reputation/leaderboard` | Get Reputation Leaderboard |
| `GET` | `/v1/reputation/metrics` | Get Reputation Metrics |
| `GET` | `/v1/reputation/profile/{agent_id}` | Get Reputation Profile |
| `POST` | `/v1/reputation/profile/{agent_id}` | Create Reputation Profile |
| `PUT` | `/v1/reputation/profile/{agent_id}/region` | Update Region |
| `PUT` | `/v1/reputation/profile/{agent_id}/specialization` | Update Specialization |
| `GET` | `/v1/reputation/trust-score/{agent_id}` | Get Trust Score Breakdown |
| `GET` | `/v1/reputation/{agent_id}/cross-chain` | Get Cross Chain Reputation |
| `POST` | `/v1/reputation/{agent_id}/cross-chain/sync` | Sync Cross Chain Reputation |
| `GET` | `/v1/rewards/analytics` | Get Reward Analytics |
| `POST` | `/v1/rewards/batch-process` | Batch Process Pending Rewards |
| `POST` | `/v1/rewards/calculate-and-distribute` | Calculate And Distribute Reward |
| `GET` | `/v1/rewards/distributions/{agent_id}` | Get Reward Distributions |
| `GET` | `/v1/rewards/leaderboard` | Get Reward Leaderboard |
| `GET` | `/v1/rewards/milestones/{agent_id}` | Get Agent Milestones |
| `GET` | `/v1/rewards/profile` | Get Reward Profile No Id |
| `GET` | `/v1/rewards/profile/{agent_id}` | Get Reward Profile |
| `POST` | `/v1/rewards/profile/{agent_id}` | Create Reward Profile |
| `POST` | `/v1/rewards/simulate-reward` | Simulate Reward Calculation |
| `GET` | `/v1/rewards/tier-progress/{agent_id}` | Get Tier Progress |
| `GET` | `/v1/rewards/tiers` | Get Reward Tiers |
| `GET` | `/v1/services` | List available services |
| `POST` | `/v1/services/blender/render` | Render using Blender |
| `POST` | `/v1/services/ffmpeg/transcode` | Transcode video using FFmpeg |
| `POST` | `/v1/services/llm/inference` | Run LLM inference |
| `POST` | `/v1/services/llm/stream` | Stream LLM inference |
| `POST` | `/v1/services/stable-diffusion/generate` | Generate images using Stable Diffusion |
| `POST` | `/v1/services/stable-diffusion/img2img` | Image-to-image generation |
| `POST` | `/v1/services/whisper/transcribe` | Transcribe audio using Whisper |
| `POST` | `/v1/services/whisper/translate` | Translate audio using Whisper |
| `GET` | `/v1/services/{name}` | Get a service's status |
| `POST` | `/v1/services/{name}/test` | Test a service's availability |
| `POST` | `/v1/stake` | Create Stake |
| `GET` | `/v1/stake/{stake_id}` | Get Stake |
| `POST` | `/v1/stake/{stake_id}/add` | Add To Stake |
| `POST` | `/v1/stake/{stake_id}/complete` | Complete Unbonding |
| `GET` | `/v1/stake/{stake_id}/rewards` | Get Stake Rewards |
| `POST` | `/v1/stake/{stake_id}/unbond` | Unbond Stake |
| `GET` | `/v1/stakes` | Get Stakes |
| `POST` | `/v1/staking/claim-rewards` | Claim Staking Rewards |
| `GET` | `/v1/staking/leaderboard` | Get Staking Leaderboard |
| `GET` | `/v1/staking/my-positions` | Get My Staking Positions |
| `GET` | `/v1/staking/my-rewards` | Get My Staking Rewards |
| `GET` | `/v1/staking/risk-assessment/{agent_wallet}` | Get Risk Assessment |
| `GET` | `/v1/staking/stats` | Get Staking Stats |
| `GET` | `/v1/state/dump` | Get State Dump |
| `GET` | `/v1/status` | Blockchain Status |
| `GET` | `/v1/supply` | Get Supply |
| `GET` | `/v1/sync-status` | Blockchain Sync Status |
| `POST` | `/v1/tasks/ollama` | Submit Ollama Task |
| `POST` | `/v1/tee/attestations` | Submit Attestation |
| `GET` | `/v1/tee/attestations/{attestation_id}` | Get Attestation |
| `POST` | `/v1/tee/enclaves` | Register Enclave |
| `GET` | `/v1/tee/enclaves/{enclave_id}` | Get Enclave |
| `GET` | `/v1/trading/agents/{agent_id}/summary` | Get Trading Summary |
| `GET` | `/v1/trading/analytics` | Get Trading Analytics |
| `GET` | `/v1/trading/matches` | List Trade Matches |
| `GET` | `/v1/trading/matches/{match_id}` | Get Trade Match |
| `GET` | `/v1/trading/negotiations` | List Negotiations |
| `POST` | `/v1/trading/negotiations` | Initiate Negotiation |
| `GET` | `/v1/trading/negotiations/{negotiation_id}` | Get Negotiation |
| `GET` | `/v1/trading/requests` | List Trade Requests |
| `POST` | `/v1/trading/requests` | Create Trade Request |
| `GET` | `/v1/trading/requests/{request_id}` | Get Trade Request |
| `GET` | `/v1/trading/requests/{request_id}/matches` | Get Trade Matches |
| `POST` | `/v1/trading/requests/{request_id}/matches` | Find Matches |
| `POST` | `/v1/trading/simulate-match` | Simulate Trade Matching |
| `GET` | `/v1/transactions/{tx_hash}` | Get Transaction |
| `GET` | `/v1/users/me` | Get Current User |
| `GET` | `/v1/users/{user_id}/balance` | Get User Balance |
| `GET` | `/v1/users/{user_id}/transactions` | Get User Transactions |
| `GET` | `/v1/validators` | Get Validators |
| `POST` | `/v1/web-vitals` | Collect Web Vitals |
| `GET` | `/v1/web-vitals/health` | Web Vitals Health |
| `POST` | `/v1/zk/generate` | Generate ZK proof |
| `GET` | `/v1/zk/health` | ZK service health check |
| `GET` | `/v1/zk/health/computation-correct` | computation_correct ZK gate health check |
| `GET` | `/v1/zk/info` | Get circuit information |
| `POST` | `/v1/zk/receipt/verify` | Verify a job receipt's stored ZK proof |
| `POST` | `/v1/zk/verify` | Verify ZK proof |

### explorer (`:8100`, AITBC Blockchain Explorer API v2.0.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/analytics/activity` | Api Activity Timeline |
| `GET` | `/api/analytics/network-stats` | Api Network Stats |
| `GET` | `/api/analytics/overview` | Analytics Overview |
| `GET` | `/api/analytics/provider-reputation/{provider_id}` | Api Provider Reputation |
| `GET` | `/api/analytics/top-addresses` | Api Top Addresses |
| `GET` | `/api/blocks/by-address/{address}` | Api Blocks By Address |
| `GET` | `/api/blocks/by-hash/{hash}` | Api Block By Hash |
| `GET` | `/api/blocks/latest` | Api Latest Blocks |
| `GET` | `/api/blocks/non-empty` | Api Non Empty Blocks |
| `GET` | `/api/blocks/{height}` | Api Block |
| `GET` | `/api/chain/head` | Api Chain Head |
| `GET` | `/api/chains` | List Chains |
| `GET` | `/api/export/blocks` | Export Blocks |
| `GET` | `/api/export/search` | Export Search |
| `GET` | `/api/search/blocks` | Search Blocks |
| `GET` | `/api/search/transactions` | Search Transactions |
| `GET` | `/api/transactions/by-hash/{hash}` | Api Transaction By Hash |
| `GET` | `/api/transactions/search` | Api Search Transactions |
| `GET` | `/api/transactions/{tx_hash}` | Api Transaction |
| `GET` | `/health` | Health |

### market (`:8102`, AITBC Market Service v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health |
| `GET` | `/live` | Live |
| `GET` | `/metrics` | Metrics |
| `GET` | `/ready` | Ready |
| `POST` | `/v1/knowledge-graph` | Create Graph |
| `GET` | `/v1/knowledge-graph/{graph_id}` | Query Graph |
| `POST` | `/v1/knowledge-graph/{graph_id}/edges` | Add Edge |
| `POST` | `/v1/knowledge-graph/{graph_id}/nodes` | Add Node |
| `GET` | `/v1/market` | Get Market Overview |
| `GET` | `/v1/market/access/{access_key}` | Get Market Access Token |
| `GET` | `/v1/market/analytics` | Get Analytics |
| `POST` | `/v1/market/bids/{bid_id}/complete` | Complete Bid |
| `POST` | `/v1/market/dynamic-pricing` | Calculate Dynamic Pricing |
| `GET` | `/v1/market/edge-advertise` | List Edge Nodes |
| `POST` | `/v1/market/edge-advertise` | Edge Advertise |
| `GET` | `/v1/market/edge/{node_id}/health` | Get Edge Health |
| `POST` | `/v1/market/ipfs/rental-token` | Register Ipfs Rental Token |
| `GET` | `/v1/market/ipfs/rental/{access_key}` | Get Ipfs Rental Token |
| `GET` | `/v1/market/jobs` | List Market Jobs |
| `POST` | `/v1/market/jobs` | Create Market Job |
| `GET` | `/v1/market/jobs/usage` | Get Market Job Usage |
| `GET` | `/v1/market/jobs/{job_id}` | Get Market Job |
| `GET` | `/v1/market/jobs/{job_id}/access` | Get Market Job Access |
| `POST` | `/v1/market/jobs/{job_id}/cancel` | Cancel Market Job |
| `POST` | `/v1/market/jobs/{job_id}/pin-confirm` | Confirm Market Job Pin |
| `POST` | `/v1/market/jobs/{job_id}/refund` | Refund Market Job Payment |
| `POST` | `/v1/market/jobs/{job_id}/release` | Release Market Job Payment |
| `POST` | `/v1/market/match` | Match Request |
| `GET` | `/v1/market/offer` | List Software Offers |
| `POST` | `/v1/market/offer` | Register Offer |
| `GET` | `/v1/market/offer-by-id/{offer_id}` | Get Offer By Id |
| `DELETE` | `/v1/market/offer/{plugin_id}` | Unregister Offer |
| `GET` | `/v1/market/offer/{plugin_id}` | Get Software Offer |
| `GET` | `/v1/market/offer/{plugin_id}/health` | Get Software Offer Health |
| `POST` | `/v1/market/offer/{service_id}/rate` | Rate Service |
| `GET` | `/v1/market/offer/{service_id}/ratings` | Get Service Ratings |
| `GET` | `/v1/market/offers` | Get Offers |
| `POST` | `/v1/market/offers` | Create Offer |
| `GET` | `/v1/market/offers/{offer_id}` | Get Offer |
| `POST` | `/v1/market/offers/{offer_id}/book` | Book Offer |
| `POST` | `/v1/market/offers/{offer_id}/cancel` | Cancel Offer |
| `GET` | `/v1/market/offers/{offer_id}/history` | Get Offer History |
| `POST` | `/v1/market/parameters/apply` | Apply Market Parameter |
| `GET` | `/v1/market/performance` | Get Market Performance |
| `GET` | `/v1/market/plugins` | Get Plugins |
| `POST` | `/v1/market/plugins` | Register Plugin |
| `POST` | `/v1/market/ratings/mark-synced` | Mark Ratings Synced |
| `POST` | `/v1/market/ratings/sync` | Sync Ratings |
| `GET` | `/v1/market/ratings/unsynced` | Get Unsynced Ratings |
| `GET` | `/v1/market/status` | Market Status |
| `GET` | `/v1/transactions` | Get Transactions |
| `POST` | `/v1/transactions` | Submit Transaction |

### trading (`:8104`, AITBC Trading Service v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/blocks` | Get Blocks Api |
| `GET` | `/health` | Health |
| `GET` | `/live` | Live |
| `GET` | `/metrics` | Metrics |
| `GET` | `/ready` | Ready |
| `GET` | `/v1/blocks` | Get Blocks |
| `GET` | `/v1/blocks/{block_id}` | Get Block |
| `POST` | `/v1/exchange/confirm-payment/{payment_id}` | Confirm Exchange Payment |
| `POST` | `/v1/exchange/create-payment` | Create Exchange Payment |
| `GET` | `/v1/exchange/market-stats` | Get Market Stats |
| `GET` | `/v1/exchange/payment-status/{payment_id}` | Get Exchange Payment Status |
| `GET` | `/v1/exchange/rates` | Get Exchange Rates |
| `GET` | `/v1/exchange/wallet/balance` | Get Exchange Wallet Balance |
| `GET` | `/v1/exchange/wallet/info` | Get Exchange Wallet Info |
| `GET` | `/v1/explorer/blocks` | Get Blocks V1 |
| `GET` | `/v1/explorer/receipts` | Get Receipts V1 |
| `GET` | `/v1/explorer/transactions/{tx_hash}` | Get Transaction Explorer |
| `GET` | `/v1/receipts` | Get Receipts |
| `GET` | `/v1/trading/agreements` | Get Agreements |
| `POST` | `/v1/trading/agreements` | Create Agreement |
| `GET` | `/v1/trading/analytics` | Get Analytics |
| `GET` | `/v1/trading/chains` | List Chains |
| `POST` | `/v1/trading/chains/register` | Register Chain |
| `GET` | `/v1/trading/chains/{chain_id}/health` | Get Chain Health |
| `GET` | `/v1/trading/inter-chain` | List Inter Chain Trades |
| `POST` | `/v1/trading/inter-chain/create` | Create Inter Chain Trade |
| `GET` | `/v1/trading/inter-chain/history` | Get Inter Chain Trade History |
| `POST` | `/v1/trading/inter-chain/match-all` | Match All Pending Trades |
| `GET` | `/v1/trading/inter-chain/{trade_id}` | Get Inter Chain Trade |
| `POST` | `/v1/trading/inter-chain/{trade_id}/match` | Match Inter Chain Trade |
| `GET` | `/v1/trading/inter-chain/{trade_id}/status` | Get Inter Chain Trade Status |
| `GET` | `/v1/trading/matches` | Get Matches |
| `POST` | `/v1/trading/matches` | Create Match |
| `GET` | `/v1/trading/offers/cache` | Get Cached Offers |
| `POST` | `/v1/trading/offers/discover` | Discover Offers |
| `POST` | `/v1/trading/offers/heartbeat` | Offer Heartbeat |
| `GET` | `/v1/trading/offers/search` | Search Offers |
| `POST` | `/v1/trading/offers/subscribe` | Subscribe To Offers |
| `GET` | `/v1/trading/offers/subscription-status` | Get Subscription Status |
| `POST` | `/v1/trading/offers/sync` | Sync Offers |
| `GET` | `/v1/trading/offers/sync-status` | Get Offer Sync Status |
| `GET` | `/v1/trading/requests` | Get Requests |
| `POST` | `/v1/trading/requests` | Create Request |
| `GET` | `/v1/trading/requests/{request_id}` | Get Request |
| `GET` | `/v1/trading/status` | Trading Status |
| `POST` | `/v1/trading/trades/{trade_id}/lock-escrow` | Lock Escrow |
| `POST` | `/v1/trading/trades/{trade_id}/settle` | Settle Trade |
| `GET` | `/v1/trading/trades/{trade_id}/settlement-status` | Settlement Status |
| `GET` | `/v1/transactions` | Get Transactions |
| `POST` | `/v1/transactions` | Submit Transaction |
| `GET` | `/v1/transactions/{tx_hash}` | Get Transaction |

### governance (`:8105`, AITBC Governance Service v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health |
| `GET` | `/live` | Live |
| `GET` | `/metrics` | Metrics |
| `GET` | `/ready` | Ready |
| `GET` | `/v1/governance/analytics` | Get Analytics |
| `POST` | `/v1/governance/delegate` | Delegate Voting Power |
| `POST` | `/v1/governance/execute` | Execute Proposal |
| `GET` | `/v1/governance/params` | Get Governance Params |
| `GET` | `/v1/governance/profiles` | Get Profiles |
| `POST` | `/v1/governance/profiles` | Create Profile |
| `GET` | `/v1/governance/profiles/{profile_id}` | Get Profile |
| `GET` | `/v1/governance/proposals` | Get Proposals |
| `POST` | `/v1/governance/proposals` | Create Proposal |
| `GET` | `/v1/governance/proposals/{proposal_id}` | Get Proposal |
| `POST` | `/v1/governance/proposals/{proposal_id}/aggregate-votes` | Aggregate Votes |
| `POST` | `/v1/governance/proposals/{proposal_id}/close` | Close Proposal Endpoint |
| `POST` | `/v1/governance/proposals/{proposal_id}/execute` | Execute Proposal V2 |
| `POST` | `/v1/governance/proposals/{proposal_id}/execute-cross-chain` | Execute Cross Chain |
| `POST` | `/v1/governance/proposals/{proposal_id}/propagate` | Propagate Proposal |
| `POST` | `/v1/governance/stake` | Stake Tokens |
| `GET` | `/v1/governance/status` | Governance Status |
| `GET` | `/v1/governance/treasury` | Get Treasury |
| `GET` | `/v1/governance/votes` | Get Votes |
| `POST` | `/v1/governance/votes` | Create Vote |
| `GET` | `/v1/governance/voting-power/{address}` | Get Voting Power V2 |
| `GET` | `/v1/transactions` | Get Transactions |
| `POST` | `/v1/transactions` | Submit Transaction |

### exchange (`:8106`, AITBC Trade Exchange v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `DELETE` | `/{full_path}` | Dispatch Write |
| `GET` | `/{full_path}` | Dispatch Read |
| `HEAD` | `/{full_path}` | Dispatch Read |
| `OPTIONS` | `/{full_path}` | Dispatch Read |
| `POST` | `/{full_path}` | Dispatch Write |
| `PUT` | `/{full_path}` | Dispatch Write |

### agent-coordinator (`:8107`, AITBC Agent Coordinator v1.0.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/` | Root |
| `POST` | `/api/v1/agent/auth/login` | Agent Login |
| `POST` | `/api/v1/agent/auth/nonce` | Issue Login Nonce |
| `GET` | `/api/v1/agent/auth/session` | Agent Session |
| `POST` | `/api/v1/agent/coin-requests/execute` | Remote Execute Coin Request |
| `POST` | `/api/v1/agent/coin-requests/register` | Register Coin Request |
| `POST` | `/api/v1/agent/keys/register` | Register Public Key |
| `GET` | `/api/v1/agent/keys/{agent_id}` | Get Public Key |
| `GET` | `/api/v1/agent/messages/agents/capability/{capability}` | Get Agents By Capability |
| `GET` | `/api/v1/agent/messages/agents/service/{service}` | Get Agents By Service |
| `POST` | `/api/v1/agent/messages/broadcast` | Broadcast Message |
| `GET` | `/api/v1/agent/messages/discover` | Discover Agents |
| `GET` | `/api/v1/agent/messages/history` | Get Message History |
| `GET` | `/api/v1/agent/messages/id/{message_id}` | Get Message |
| `POST` | `/api/v1/agent/messages/id/{message_id}/read` | Mark Message Read |
| `GET` | `/api/v1/agent/messages/inbox` | Get Inbox |
| `GET` | `/api/v1/agent/messages/load-balancer/stats` | Get Load Balancer Stats |
| `PUT` | `/api/v1/agent/messages/load-balancer/strategy` | Set Load Balancing Strategy |
| `GET` | `/api/v1/agent/messages/peers` | Get All Peers |
| `POST` | `/api/v1/agent/messages/peers/add` | Add Peer |
| `POST` | `/api/v1/agent/messages/peers/remove` | Remove Peer |
| `GET` | `/api/v1/agent/messages/peers/{agent_id}` | Get Agent Peers |
| `GET` | `/api/v1/agent/messages/registry/stats` | Get Registry Stats |
| `POST` | `/api/v1/agent/messages/send` | Send Encrypted Message |
| `POST` | `/api/v1/agent/messages/subscribe` | Subscribe To Topic |
| `GET` | `/api/v1/agent/messages/subscriptions/{agent_id}` | Get Agent Subscriptions |
| `POST` | `/api/v1/agent/messages/unsubscribe` | Unsubscribe From Topic |
| `GET` | `/api/v1/agent/messages/{agent_id}` | Get Messages For Agent Compatibility |
| `GET` | `/api/v1/agent/workflows` | List workflows |
| `POST` | `/api/v1/agent/workflows` | Create workflow |
| `GET` | `/api/v1/agent/workflows/executions` | List executions |
| `POST` | `/api/v1/agent/workflows/executions/{execution_id}/cancel` | Cancel execution |
| `POST` | `/api/v1/agent/workflows/{workflow_id}/execute` | Execute workflow |
| `GET` | `/api/v1/agent/workflows/{workflow_id}/status` | Get workflow status |
| `GET` | `/api/v1/agent/ws/status` | Websocket Status |
| `POST` | `/api/v1/auth/api-key/generate` | Generate Api Key |
| `POST` | `/api/v1/auth/api-key/validate` | Validate Api Key |
| `DELETE` | `/api/v1/auth/api-key/{api_key}` | Revoke Api Key |
| `POST` | `/api/v1/auth/login` | Login |
| `POST` | `/api/v1/auth/refresh` | Refresh Token |
| `POST` | `/api/v1/auth/validate` | Validate Token |
| `GET` | `/health` | Health Check |
| `GET` | `/v1/advanced-features/status` | Get Advanced Features Status |
| `POST` | `/v1/agents/discover` | Discover Agents |
| `GET` | `/v1/agents/nonce` | Issue Registration Nonce |
| `POST` | `/v1/agents/register` | Register Agent |
| `GET` | `/v1/agents/{agent_id}` | Get Agent |
| `POST` | `/v1/agents/{agent_id}/heartbeat` | Agent Heartbeat |
| `PUT` | `/v1/agents/{agent_id}/identity` | Rotate Agent Identity |
| `PUT` | `/v1/agents/{agent_id}/status` | Update Agent Status |
| `POST` | `/v1/ai/learning/experience` | Record Learning Experience |
| `POST` | `/v1/ai/learning/predict` | Predict Performance |
| `POST` | `/v1/ai/learning/recommend` | Recommend Action |
| `GET` | `/v1/ai/learning/statistics` | Get Learning Statistics |
| `POST` | `/v1/ai/ml-model/create` | Create Ml Model |
| `POST` | `/v1/ai/ml-model/{model_id}/predict` | Predict With Ml Model |
| `POST` | `/v1/ai/ml-model/{model_id}/train` | Train Ml Model |
| `POST` | `/v1/ai/neural-network/create` | Create Neural Network |
| `POST` | `/v1/ai/neural-network/{network_id}/predict` | Predict With Neural Network |
| `POST` | `/v1/ai/neural-network/{network_id}/train` | Train Neural Network |
| `GET` | `/v1/ai/statistics` | Get Ai Statistics |
| `GET` | `/v1/alerts` | Get Alerts |
| `GET` | `/v1/alerts/rules` | Get Alert Rules |
| `GET` | `/v1/alerts/stats` | Get Alert Stats |
| `POST` | `/v1/alerts/{alert_id}/resolve` | Resolve Alert |
| `GET` | `/v1/auth/stats` | Get Permission Stats |
| `PUT` | `/v1/consensus/algorithm` | Set Consensus Algorithm |
| `POST` | `/v1/consensus/node/register` | Register Consensus Node |
| `PUT` | `/v1/consensus/node/{node_id}/status` | Update Node Status |
| `POST` | `/v1/consensus/proposal/create` | Create Consensus Proposal |
| `GET` | `/v1/consensus/proposal/{proposal_id}` | Get Proposal Status |
| `POST` | `/v1/consensus/proposal/{proposal_id}/vote` | Cast Consensus Vote |
| `GET` | `/v1/consensus/statistics` | Get Consensus Statistics |
| `GET` | `/v1/metrics` | Get Prometheus Metrics |
| `GET` | `/v1/metrics/health` | Get Health Metrics |
| `GET` | `/v1/metrics/summary` | Get Metrics Summary |
| `GET` | `/v1/protected/admin` | Admin Only Endpoint |
| `GET` | `/v1/protected/operator` | Operator Endpoint |
| `GET` | `/v1/roles` | List All Roles |
| `GET` | `/v1/roles/{role}` | Get Role Permissions |
| `GET` | `/v1/sla` | Get Sla Status |
| `POST` | `/v1/sla/{sla_id}/record` | Record Sla Metric |
| `GET` | `/v1/system/health` | Get System Health |
| `GET` | `/v1/system/status` | Get System Status |
| `GET` | `/v1/tasks/escrow-config` | Get Escrow Config |
| `POST` | `/v1/tasks/escrow/expire-stale` | Expire Stale Escrows |
| `GET` | `/v1/tasks/escrow/{escrow_id}` | Get Escrow Status |
| `GET` | `/v1/tasks/queues` | Get Queue Sizes |
| `GET` | `/v1/tasks/queues/stats` | Get Queue Stats |
| `POST` | `/v1/tasks/queues/{priority}/clear` | Clear Queue |
| `GET` | `/v1/tasks/status` | Get Task Status |
| `POST` | `/v1/tasks/submit` | Submit Task |
| `POST` | `/v1/tasks/{task_id}/complete` | Complete Task |
| `GET` | `/v1/tasks/{task_id}/escrow` | Get Task Escrow |
| `POST` | `/v1/tasks/{task_id}/fail` | Fail Task |
| `GET` | `/v1/users/{user_id}/permissions` | Get User Permissions |
| `POST` | `/v1/users/{user_id}/permissions/grant` | Grant User Permission |
| `DELETE` | `/v1/users/{user_id}/permissions/{permission}` | Revoke User Permission |
| `GET` | `/v1/users/{user_id}/role` | Get User Role |
| `POST` | `/v1/users/{user_id}/role` | Assign User Role |

### wallet (`:8108`, AITBC Wallet Daemon v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/exchange/price.json` | Exchange Price Json |
| `GET` | `/health` | Health Check |
| `GET` | `/ready` | Ready Check |
| `POST` | `/v1/bridge/deposit` | Bridge Deposit |
| `GET` | `/v1/bridge/deposit/{tx_hash}` | Bridge Get Deposit |
| `GET` | `/v1/bridge/deposits` | Bridge List Deposits |
| `GET` | `/v1/bridge/estimate` | Bridge Estimate |
| `POST` | `/v1/bridge/poll` | Trigger Bridge Poll |
| `POST` | `/v1/bridge/polling` | Set Bridge Polling |
| `GET` | `/v1/bridge/price` | Get Bridge Price |
| `GET` | `/v1/bridge/status` | Get Bridge V1 Status |
| `POST` | `/v1/bridge/withdraw/build` | Bridge Withdraw Build |
| `POST` | `/v1/bridge/withdraw/estimate` | Bridge Withdraw Estimate |
| `POST` | `/v1/bridge/withdraw/submit` | Bridge Withdraw Submit |
| `GET` | `/v1/bridge/withdraw/{ait_tx_hash}` | Bridge Get Withdraw |
| `GET` | `/v1/bridge/withdrawals` | Bridge List Withdrawals |
| `GET` | `/v1/exchange/calculate` | Calculate Exchange |
| `GET` | `/v1/exchange/deposits` | List Deposits |
| `GET` | `/v1/exchange/deposits/{deposit_id}` | Get Deposit |
| `POST` | `/v1/exchange/deposits/{deposit_id}/complete` | Complete Deposit |
| `POST` | `/v1/exchange/deposits/{deposit_id}/verify` | Verify Deposit |
| `GET` | `/v1/exchange/history` | Get Price History |
| `GET` | `/v1/exchange/price` | Get Price |
| `GET` | `/v1/exchange/status` | Get Bridge Status |
| `GET` | `/v1/receipts/{job_id}` | Verify latest receipt for a job |
| `GET` | `/v1/receipts/{job_id}/history` | Verify all historical receipts for a job |
| `POST` | `/v1/rpc` | JSON-RPC endpoint |
| `GET` | `/v1/wallets` | List wallets |
| `POST` | `/v1/wallets` | Create wallet |
| `GET` | `/v1/wallets/{wallet_id}/balance` | Get wallet balance from blockchain |
| `POST` | `/v1/wallets/{wallet_id}/send` | Send transaction |
| `POST` | `/v1/wallets/{wallet_id}/sign` | Sign payload |
| `POST` | `/v1/wallets/{wallet_id}/unlock` | Unlock wallet |

### pool-hub (`:8210`, AITBC Pool Hub v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Pool Hub health status |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/v1/match` | Find top miners for a job |
| `POST` | `/v1/miners/heartbeat` | Miner Heartbeat |
| `POST` | `/v1/miners/register` | Register Miner |
| `GET` | `/v1/miners/status` | Miner Status |
| `POST` | `/v1/parameters/apply` | Apply Parameter Change |
| `GET` | `/v1/parameters/list` | List Governance Parameters |
| `GET` | `/v1/services/` | List Service Configs |
| `GET` | `/v1/services/templates/{service_type}` | Get Service Template |
| `POST` | `/v1/services/validate/{service_type}` | Validate Service Config |
| `DELETE` | `/v1/services/{service_type}` | Delete Service Config |
| `GET` | `/v1/services/{service_type}` | Get Service Config |
| `PATCH` | `/v1/services/{service_type}` | Patch Service Config |
| `POST` | `/v1/services/{service_type}` | Create Or Update Service Config |
| `POST` | `/v1/sla/billing/invoice/generate` | Generate Invoice |
| `POST` | `/v1/sla/billing/sync` | Sync Billing Usage |
| `GET` | `/v1/sla/billing/usage` | Get Billing Usage |
| `POST` | `/v1/sla/billing/usage/record` | Record Usage |
| `POST` | `/v1/sla/capacity/alerts/configure` | Configure Capacity Alerts |
| `GET` | `/v1/sla/capacity/forecast` | Get Capacity Forecast |
| `GET` | `/v1/sla/capacity/recommendations` | Get Scaling Recommendations |
| `GET` | `/v1/sla/capacity/snapshots` | Get Capacity Snapshots |
| `GET` | `/v1/sla/metrics` | Get All Sla Metrics |
| `POST` | `/v1/sla/metrics/collect` | Collect Sla Metrics |
| `GET` | `/v1/sla/metrics/{miner_id}` | Get Miner Sla Metrics |
| `GET` | `/v1/sla/status` | Get Sla Status |
| `GET` | `/v1/sla/violations` | Get Sla Violations |
| `POST` | `/v1/validation/batch` | Validate Multiple Services |
| `GET` | `/v1/validation/compatible-services` | Get Compatible Services |
| `GET` | `/v1/validation/hardware-profile` | Get Hardware Profile |
| `POST` | `/v1/validation/service/{service_id}` | Validate Service |

## Routes on node2

### gpu (`:8101`, AITBC GPU Service v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health |
| `GET` | `/live` | Live |
| `GET` | `/ready` | Ready |
| `GET` | `/v1/gpu/discover` | Gpu Discover |
| `POST` | `/v1/gpu/queue` | Queue Gpu Job |
| `GET` | `/v1/gpu/queue/{gpu_id}` | List Gpu Queue |
| `POST` | `/v1/gpu/queue/{gpu_id}/next` | Next Gpu Queue |
| `POST` | `/v1/gpu/queue/{job_id}/complete` | Complete Gpu Queue |
| `POST` | `/v1/gpu/register` | Register Gpu |
| `GET` | `/v1/gpu/status` | Gpu Status |
| `DELETE` | `/v1/gpu/{gpu_id}` | Delete Gpu |
| `GET` | `/v1/gpu/{gpu_id}` | Get Gpu |
| `PUT` | `/v1/gpu/{gpu_id}` | Update Gpu |
| `GET` | `/v1/market/edge-gpu/metrics/{gpu_id}` | Get Edge Gpu Metrics |
| `POST` | `/v1/market/edge-gpu/optimize/inference/{gpu_id}` | Optimize Inference |
| `GET` | `/v1/market/edge-gpu/profiles` | Get Consumer Gpu Profiles |
| `POST` | `/v1/market/edge-gpu/scan/{miner_id}` | Scan Edge Gpus |
| `POST` | `/v1/miners/heartbeat` | Miner Heartbeat |
| `POST` | `/v1/miners/poll` | Poll Jobs |
| `POST` | `/v1/miners/register` | Register Miner |
| `POST` | `/v1/miners/{job_id}/fail` | Submit Job Failure |
| `POST` | `/v1/miners/{job_id}/result` | Submit Job Result |
| `DELETE` | `/v1/miners/{miner_id}` | Deregister Miner |
| `PUT` | `/v1/miners/{miner_id}/capabilities` | Update Miner Capabilities |
| `POST` | `/v1/miners/{miner_id}/earnings` | Get Miner Earnings |
| `GET` | `/v1/miners/{miner_id}/gpus` | Get Miner Gpus |
| `GET` | `/v1/transactions` | Get Transactions |
| `POST` | `/v1/transactions` | Submit Transaction |

### edge-api (`:8111`, Edge API Service v0.1.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Health Check |
| `GET` | `/ready` | Readiness Check |
| `GET` | `/v1/database/` | List Databases |
| `POST` | `/v1/database/init` | Init Database |
| `DELETE` | `/v1/database/{database_id}` | Delete Database |
| `GET` | `/v1/database/{database_id}` | Get Database |
| `POST` | `/v1/database/{database_id}/sync` | Sync Database |
| `GET` | `/v1/edge-gpu/balance` | Edge Gpu Balance |
| `POST` | `/v1/edge-gpu/transfer` | Edge Gpu Transfer |
| `GET` | `/v1/gpu/` | List Gpus |
| `POST` | `/v1/gpu/advertise` | Advertise To Market |
| `POST` | `/v1/gpu/scan` | Scan Gpus |
| `DELETE` | `/v1/gpu/{gpu_id}` | Remove Gpu Listing |
| `GET` | `/v1/gpu/{gpu_id}` | Get Gpu Listing |
| `GET` | `/v1/gpu/{gpu_id}/metrics` | Get Gpu Metrics |
| `GET` | `/v1/islands/` | List Islands |
| `POST` | `/v1/islands/bridge` | Request Bridge |
| `GET` | `/v1/islands/by-region/{region}` | List Memberships By Region |
| `POST` | `/v1/islands/join` | Join Island |
| `POST` | `/v1/islands/leave` | Leave Island |
| `GET` | `/v1/islands/{island_id}` | Get Island |
| `GET` | `/v1/metrics/` | List Metrics |
| `POST` | `/v1/metrics/` | Record Metrics |
| `DELETE` | `/v1/metrics/{metric_id}` | Delete Metrics |
| `GET` | `/v1/metrics/{metric_id}` | Get Metrics |
| `GET` | `/v1/serve/requests` | List Compute Requests |
| `POST` | `/v1/serve/requests` | Submit Compute Request |
| `GET` | `/v1/serve/requests/{request_id}` | Get Compute Request |
| `POST` | `/v1/serve/requests/{request_id}/cancel` | Cancel Compute Request |
| `GET` | `/v1/serve/requests/{request_id}/result` | Get Compute Result |

### ffmpeg (`:8230`, AITBC FFmpeg Service v1.0.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/capabilities` | Capabilities |
| `GET` | `/health` | Health |
| `POST` | `/process` | Process Video |

### hermes (`:8270`, AITBC Hermes Agent Service v1.0.0)

| Method | Path | Summary |
|---|---|---|
| `GET` | `/capabilities` | Capabilities |
| `GET` | `/health` | Health |
| `POST` | `/run` | Run Hermes |
