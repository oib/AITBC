# Blockchain Router Route Table Snapshot

**Date:** 2026-05-24
**File:** `apps/blockchain-node/src/aitbc_chain/rpc/router.py`
**Total Routes:** 58

## Block Routes (5)
- `GET /genesis_allocations` - Get genesis allocations from blockchain
- `GET /head` - Get current chain head
- `GET /blocks/{height}` - Get block by height
- `GET /blocks-range` - Get blocks in height range
- `POST /importBlock` - Import a block

## Transaction Routes (3)
- `POST /transaction` - Submit transaction
- `GET /mempool` - Get pending transactions
- `POST /transactions/marketplace` - Submit marketplace transaction
- `GET /transactions` - Query transactions

## Account Routes (5)
- `GET /account/{address}` - Get account information
- `GET /accounts/{address}` - Get account information (alias)
- `POST /register-account` - Create/register a new account
- `POST /faucet` - Request test tokens from faucet
- `GET /balance/{address}` - Get detailed balance breakdown
- `GET /balance/{address}/reconcile` - Reconcile balance

## Dispute Routes (9)
- `POST /disputes/file` - File a new dispute
- `POST /disputes/evidence` - Submit evidence for a dispute
- `POST /disputes/verify-evidence` - Verify evidence (arbitrator only)
- `POST /disputes/vote` - Submit arbitration vote (arbitrator only)
- `POST /disputes/arbitrators/authorize` - Authorize an arbitrator (admin only)
- `GET /disputes/active` - Get all active disputes
- `GET /disputes/arbitrators` - Get all authorized arbitrators
- `GET /disputes/arbitrators/{arbitrator_address}` - Get disputes for an arbitrator
- `GET /disputes/user/{user_address}` - Get disputes for a user
- `GET /disputes/{dispute_id}` - Get dispute details
- `GET /disputes/{dispute_id}/evidence` - Get evidence for a dispute
- `GET /disputes/{dispute_id}/votes` - Get arbitration votes for a dispute

## Contract Routes (11)
- `POST /contracts/deploy/messaging` - Deploy messaging contract
- `GET /contracts` - List deployed contracts
- `POST /contracts/deploy` - Deploy a smart contract
- `POST /contracts/call` - Call a contract method
- `POST /contracts/verify` - Verify a ZK proof
- `GET /contracts/messaging/state` - Get messaging contract state
- `GET /messaging/topics` - Get forum topics
- `POST /messaging/topics/create` - Create forum topic
- `GET /messaging/topics/{topic_id}/messages` - Get topic messages
- `POST /messaging/messages/post` - Post message
- `POST /messaging/messages/{message_id}/vote` - Vote on message
- `GET /messaging/messages/search` - Search messages
- `GET /messaging/agents/{agent_id}/reputation` - Get agent reputation
- `POST /messaging/messages/{message_id}/moderate` - Moderate message

## Sync Routes (3)
- `GET /export-chain` - Export full chain state
- `POST /import-chain` - Import chain state
- `POST /force-sync` - Force reorg to specified peer

## Gossip Routes (1)
- `POST /eth_getLogs` - Query smart contract event logs

## Island Routes (5)
- `POST /islands/join` - Join an island
- `POST /islands/leave` - Leave an island
- `GET /islands` - List all islands
- `GET /islands/{island_id}` - Get island details
- `POST /islands/bridge` - Request a bridge to another island

## Bridge Routes (3)
- `POST /bridge/lock` - Lock funds for cross-chain transfer
- `POST /bridge/confirm` - Confirm and release cross-chain transfer
- `GET /bridge/transfer/{transfer_id}` - Get transfer status
- `GET /bridge/pending` - List pending bridge transfers

## Staking Routes (3)
- `POST /staking/stake` - Stake tokens
- `POST /staking/unstake` - Unstake tokens
- `GET /staking/{address}` - Get staking info

## Faucet Routes (1)
- `POST /faucet` - Request test tokens from faucet

## Notes
- Total routes: 58 endpoints
- Duplicate path `/accounts/{address}` was removed (now only alias endpoint remains)
- Routes are grouped by domain for planned extraction
- All endpoints successfully extracted to domain modules
