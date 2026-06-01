# Hermes Agent Testing Prompt: Blockchain Integrations

## Context

Recent blockchain integrations have been completed to enable on-chain staking, agent identity verification, and governance decision recording. All integrations use the hub blockchain RPC for cross-node operations.

## Completed Integrations

### 1. Staking (wallet.py)
- `wallet stake <amount> --duration <days>` - Submit to `/rpc/staking/stake` on hub
- `wallet unstake <stake_id>` - Submit to `/rpc/staking/unstake` on hub
- `wallet staking-info` - Query `/rpc/staking/info` on hub

### 2. Agent Identity (agent_sdk.py)
- `agent register-identity <agent_id> <agent_address>` - Register on blockchain
- `agent get-identity <agent_id>` - Query from blockchain
- `agent verify-identity <agent_id> <verifier_address>` - Verify on blockchain

### 3. Governance (operations.py)
- `operations governance vote <proposal_id>` - Cast vote on blockchain
- `operations governance proposal --proposal-id <id>` - Create proposal on blockchain
- `operations governance get-proposal <proposal_id>` - Query proposal from blockchain

## Testing Instructions

### Prerequisites
1. Ensure blockchain node is running on hub: `hub.aitbc.bubuit.net:8006`
2. Ensure HUB_DISCOVERY_URL is set in `/etc/aitbc/blockchain.env`
3. Have a wallet with AITBC tokens for testing
4. Ensure database tables exist: `stake`, `agent_identity`, `governance_proposal`, `governance_vote`
5. **Register wallet account on hub blockchain** (wallet must exist on-chain before operations)

### Step 0: Register Wallet on Hub Blockchain
```bash
# Set default wallet (create config if it doesn't exist)
mkdir -p ~/.aitbc
echo "active_wallet: my-agent-wallet" > ~/.aitbc/config.yaml

# Register wallet account on hub blockchain
aitbc wallet faucet --wallet my-agent-wallet

# Verify wallet has balance on hub
aitbc wallet balance --wallet my-agent-wallet
```

**Expected Results:**
- Wallet account created on hub blockchain
- Balance > 0 after faucet request

### Test 1: Staking Flow
```bash
# Check wallet balance
aitbc wallet balance --wallet my-agent-wallet

# Stake tokens (e.g., 100 AITBC for 30 days)
aitbc wallet stake 100 --duration 30 --wallet my-agent-wallet

# Verify staking info
aitbc wallet staking-info --wallet my-agent-wallet

# Unstake tokens (after lock period or for testing)
aitbc wallet unstake <stake_id> --wallet my-agent-wallet
```

**Expected Results:**
- Stake transaction recorded on blockchain
- Staking info shows correct amount and lock period
- Unstake returns tokens to wallet balance

### Test 2: Agent Identity Flow
```bash
# Create an agent first (if not exists)
aitbc agent create my-test-agent --type provider --auto-detect

# Register agent identity on blockchain
aitbc agent register-identity my-test-agent <wallet_address> --display-name "Test Agent"

# Query agent identity from blockchain
aitbc agent get-identity my-test-agent

# Verify agent identity
aitbc agent verify-identity my-test-agent <verifier_wallet_address>
```

**Expected Results:**
- Identity registered with agent_id and agent_address
- Query returns identity details including capabilities
- Verification status updates to is_verified=true

### Test 3: Governance Flow
```bash
# Create a governance proposal
aitbc operations governance proposal \
  --proposal-id prop_test_001 \
  --title "Test Proposal" \
  --description "Testing governance integration" \
  --category general \
  --wallet my-agent-wallet \
  --voting-days 7

# Query the proposal
aitbc operations governance get-proposal prop_test_001

# Cast a vote on the proposal
aitbc operations governance vote prop_test_001 \
  --vote for \
  --wallet my-agent-wallet \
  --voting-power 100 \
  --reason "Testing vote functionality"

# Query proposal again to see vote count updated
aitbc operations governance get-proposal prop_test_001
```

**Expected Results:**
- Proposal created with voting period
- Query shows proposal details and vote counts
- Vote recorded and proposal vote counts updated

## Verification Steps

### Check Database Records
```bash
# Connect to blockchain database and verify records
sqlite3 /var/lib/aitbc/blockchain.db

# Check stakes
SELECT * FROM stake WHERE address = '<wallet_address>';

# Check agent identities
SELECT * FROM agent_identity WHERE agent_id = '<agent_id>';

# Check governance proposals
SELECT * FROM governance_proposal WHERE proposal_id = 'prop_test_001';

# Check governance votes
SELECT * FROM governance_vote WHERE proposal_id = 'prop_test_001';
```

### Check RPC Endpoints
```bash
# Test staking endpoint
curl -X POST http://hub.aitbc.bubuit.net:8006/rpc/staking/stake \
  -H "Content-Type: application/json" \
  -d '{"address": "<wallet_address>", "amount": 1000000000000000000, "lock_days": 30, "chain_id": "ait-testnet"}'

# Test identity endpoint
curl -X POST http://hub.aitbc.bubuit.net:8006/rpc/identity/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test_agent", "agent_address": "<wallet_address>", "display_name": "Test", "chain_id": "ait-testnet"}'

# Test governance endpoint
curl -X POST http://hub.aitbc.bubuit.net:8006/rpc/governance/proposal \
  -H "Content-Type: application/json" \
  -d '{"proposal_id": "prop_test", "proposer_address": "<wallet_address>", "title": "Test", "description": "Test", "chain_id": "ait-testnet"}'
```

## Success Criteria

1. **Staking**: Tokens can be staked and unstaked with correct balance updates
2. **Identity**: Agent identities can be registered, queried, and verified on-chain
3. **Governance**: Proposals can be created and votes can be cast with correct tallying
4. **Cross-node**: All operations work via hub RPC for cross-node propagation
5. **Database**: Records persist correctly in blockchain database tables

## Troubleshooting

### Common Issues
- **Connection refused**: Check hub node is running and HUB_DISCOVERY_URL is correct
- **Insufficient balance**: Ensure wallet has enough AITBC tokens for staking
- **Already voted**: Each address can only vote once per proposal
- **Proposal not found**: Ensure proposal_id matches exactly what was created

### Debug Commands
```bash
# Check blockchain node status
systemctl status aitbc-blockchain-node

# Check blockchain logs
journalctl -u aitbc-blockchain-node -f

# Check environment variables
cat /etc/aitbc/blockchain.env | grep HUB_DISCOVERY_URL

# Test RPC connectivity
curl http://hub.aitbc.bubuit.net:8006/rpc/head
```

## Next Steps After Testing

1. Document any issues found during testing
2. Report successful integrations to development team
3. Consider adding automated tests for these integrations
4. Explore integrating with blockchain-event-bridge for event-driven actions
