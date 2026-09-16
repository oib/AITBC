# Verification Guide

This guide provides methods to verify that blockchain operations are correctly recorded.

## Database Verification

To verify that blockchain operations are correctly recorded, query the blockchain database:

```bash
# Connect to blockchain database
sqlite3 /var/lib/aitbc/blockchain.db

# Check stakes
SELECT * FROM stake WHERE address = '<wallet_address>';

# Check agent identities
SELECT * FROM agent_identity WHERE agent_id = '<agent_id>';

# Check governance proposals
SELECT * FROM governance_proposal WHERE proposal_id = 'prop_test_001';

# Check governance votes
SELECT * FROM governance_vote WHERE proposal_id = 'prop_test_001';

# Check GPU registrations
SELECT * FROM gpu_registration WHERE gpu_id = 'GPU-ba5c6553-6396-ab66-5706-17e6de30a93a';

# Check GPU allocations
SELECT * FROM gpu_allocation WHERE gpu_id = 'GPU-ba5c6553-6396-ab66-5706-17e6de30a93a';
```

## RPC Endpoint Testing

Direct RPC endpoint testing for integration verification. **All mutating `/rpc/*` endpoints require `X-API-Key` (GAP-56)** — set `BLOCKCHAIN_RPC_API_KEY` from `/etc/aitbc/blockchain-secrets.env` on any node, and note that staking/governance calls additionally need a wallet-signed `signature` + fresh `nonce`/`timestamp` body (see the CLI/MCP callers).

### Staking

```bash
curl -X POST http://hub.aitbc.bubuit.net:8202/rpc/staking/stake \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"address": "<wallet_address>", "amount": 1000000000000000000, "lock_days": 30, "chain_id": "ait-hub.aitbc.bubuit.net", "signature": "<sig>", "nonce": <n>, "timestamp": <unix>}'
```

### Identity

```bash
curl -X POST http://hub.aitbc.bubuit.net:8202/rpc/identity/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"agent_id": "test_agent", "agent_address": "<wallet_address>", "display_name": "Test", "chain_id": "ait-hub.aitbc.bubuit.net"}'
```

### Governance

```bash
# Test governance endpoint via the blockchain RPC
curl -X POST http://hub.aitbc.bubuit.net:8202/rpc/governance/proposal \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"proposal_id": "prop_test", "proposer_address": "<wallet_address>", "title": "Test", "description": "Test", "chain_id": "ait-hub.aitbc.bubuit.net"}'
```

### GPU Resources

```bash
# GPU registration via the blockchain RPC
curl -X POST http://hub.aitbc.bubuit.net:8202/rpc/gpu/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"gpu_id": "GPU-test", "miner_id": "miner-001", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": 0.5, "registered_by": "<wallet_address>", "chain_id": "ait-hub.aitbc.bubuit.net"}'

# GPU query via the blockchain RPC
curl -X GET "http://hub.aitbc.bubuit.net:8202/rpc/gpu/info/GPU-test?chain_id=ait-hub.aitbc.bubuit.net"

# GPU list via the blockchain RPC
curl -X GET "http://hub.aitbc.bubuit.net:8202/rpc/gpus?chain_id=ait-hub.aitbc.bubuit.net"
```

## CLI Verification

### Staking — CLI Verification

```bash
# Check staking info
aitbc wallet --wallet-name my-agent-wallet staking-info
```

### Identity — Check staking info

```bash
# Query agent identity
aitbc agent get-identity --agent-id my-test-agent
```

### Governance — Query agent identity

```bash
# Query proposal
aitbc governance get --proposal-id prop_test_001
```

### GPU Resources — Query proposal

```bash
# Query GPU registration
aitbc gpu-onchain query --gpu-id GPU-ba5c6553-6396-ab66-5706-17e6de30a93a

# List GPUs
aitbc gpu-onchain list

# Query allocations
aitbc gpu-onchain allocations --gpu-id GPU-ba5c6553-6396-ab66-5706-17e6de30a93a
```
