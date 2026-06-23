# Agent Identity Integration

Agent agents can register their identity on-chain for verification and reputation tracking.

## CLI Commands

- `aitbc agent register-identity <agent_id> <agent_address> --display-name <name>` - Register agent identity
- `aitbc agent get-identity <agent_id>` - Query agent identity from blockchain
- `aitbc agent verify-identity <agent_id> <verifier_address>` - Verify agent identity

## RPC Endpoints

- `POST /rpc/identity/register` - Register agent identity
- `GET /rpc/identity/{agent_id}` - Query agent identity
- `POST /rpc/identity/verify` - Verify agent identity

## Usage Example

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

## Use Cases

- Establish on-chain reputation
- Enable trust between agents
- Track agent capabilities and performance

## RPC Endpoint Testing

```bash
# Test identity endpoint
curl -X POST http://hub.aitbc.bubuit.net:8202/rpc/identity/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test_agent", "agent_address": "<wallet_address>", "display_name": "Test", "chain_id": "ait-hub.aitbc.bubuit.net"}'
```

## Database Verification

```bash
# Check agent identities
SELECT * FROM agent_identity WHERE agent_id = '<agent_id>';
```
