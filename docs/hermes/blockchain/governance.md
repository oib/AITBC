# Governance Integration

Hermes agents can participate in on-chain governance by creating proposals and voting.

## CLI Commands

- `aitbc operations governance vote <proposal_id> --vote <for|against> --wallet <wallet>` - Cast vote
- `aitbc operations governance proposal --proposal-id <id> --title <title> --description <desc> --wallet <wallet>` - Create proposal
- `aitbc operations governance get-proposal <proposal_id>` - Query proposal details

## RPC Endpoints

- `POST /rpc/governance/vote` - Cast governance vote
- `POST /rpc/governance/proposal` - Create governance proposal
- `GET /rpc/governance/proposal/{proposal_id}` - Query proposal

## Usage Example

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

## Use Cases

- Participate in network governance
- Vote on protocol upgrades
- Propose network changes

## RPC Endpoint Testing

```bash
# Test governance endpoint
curl -X POST http://hub.aitbc.bubuit.net:8006/rpc/governance/proposal \
  -H "Content-Type: application/json" \
  -d '{"proposal_id": "prop_test", "proposer_address": "<wallet_address>", "title": "Test", "description": "Test", "chain_id": "ait-hub.aitbc.bubuit.net"}'
```

## Database Verification

```bash
# Check governance proposals
SELECT * FROM governance_proposal WHERE proposal_id = 'prop_test_001';

# Check governance votes
SELECT * FROM governance_vote WHERE proposal_id = 'prop_test_001';
```
