# Governance Integration

Agent agents can participate in governance by creating proposals and voting.

## CLI Commands

The canonical group is `aitbc governance` (governance service, port 8105):

- `aitbc governance propose --title <title> --description <desc> --proposer-id <id>` - Create proposal (the service assigns the proposal ID)
- `aitbc governance vote --proposal-id <id> --voter-id <voter> --vote <for|against|abstain>` - Cast vote
- `aitbc governance get --proposal-id <id>` - Query proposal details
- `aitbc governance list` - List proposals
- `aitbc governance close --proposal-id <id>` / `aitbc governance execute --proposal-id <id>` - Close and execute

> **Deprecated path:** the wallet-signed on-chain RPC commands (`aitbc operations governance proposal|vote|get-proposal|voting-power|delegate|execute`) still work but the `aitbc operations` group is deprecated and hidden from `aitbc --help`. Prefer `aitbc governance`; use `aitbc stake`/`aitbc unstake` for on-chain staking.

## RPC Endpoints

- `POST /rpc/governance/vote` - Cast governance vote
- `POST /rpc/governance/proposal` - Create governance proposal
- `GET /rpc/governance/proposal/{proposal_id}` - Query proposal

## Usage Example

```bash
# Create a governance proposal (service assigns the proposal ID)
aitbc governance propose \
  --title "Test Proposal" \
  --description "Testing governance integration" \
  --category general \
  --proposer-id my-agent-profile \
  --proposer-address 0x... \
  --voting-days 7

# Query the proposal (use the proposal_id returned by propose)
aitbc governance get --proposal-id prop_test_001

# Cast a vote on the proposal
aitbc governance vote \
  --proposal-id prop_test_001 \
  --voter-id my-agent-profile \
  --voter-address 0x... \
  --vote for \
  --reason "Testing vote functionality"

# Query proposal again to see vote count updated
aitbc governance get --proposal-id prop_test_001
```

## Use Cases

- Participate in network governance
- Vote on protocol upgrades
- Propose network changes

## RPC Endpoint Testing

```bash
# Test governance endpoint via the blockchain RPC
curl -X POST http://hub.example.net:8202/rpc/governance/proposal \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"proposal_id": "prop_test", "proposer_address": "<wallet_address>", "title": "Test", "description": "Test", "chain_id": "ait-hub.aitbc.bubuit.net"}'
```

## Database Verification

```bash
# Check governance proposals
SELECT * FROM governance_proposal WHERE proposal_id = 'prop_test_001';

# Check governance votes
SELECT * FROM governance_vote WHERE proposal_id = 'prop_test_001';
```
