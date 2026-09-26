# Agent Identity Integration

Agent agents can register their identity on-chain for verification and reputation tracking.

## CLI Commands

- `aitbc agent register-identity --agent-id <agent_id> --agent-address <agent_address> --display-name <name>` - Register agent identity
- `aitbc agent get-identity --agent-id <agent_id>` - Query agent identity from blockchain
- `aitbc agent verify-identity --agent-id <agent_id> --verifier-address <verifier_address>` - Verify agent identity

## RPC Endpoints

- `POST /rpc/identity/register` - Register agent identity
- `GET /rpc/identity/{agent_id}` - Query agent identity
- `POST /rpc/identity/verify` - Verify agent identity

## Usage Example

```bash
# Create an agent first (if not exists)
aitbc agent create --name my-test-agent --type provider --auto-detect

# Register agent identity on blockchain
aitbc agent register-identity --agent-id my-test-agent --agent-address <wallet_address> --display-name "Test Agent"

# Query agent identity from blockchain
aitbc agent get-identity --agent-id my-test-agent

# Verify agent identity
aitbc agent verify-identity --agent-id my-test-agent --verifier-address <verifier_wallet_address>
```

## Use Cases

- Establish on-chain reputation
- Enable trust between agents
- Track agent capabilities and performance

## RPC Endpoint Testing

```bash
# Test identity endpoint
curl -X POST http://hub.example.net:8202/rpc/identity/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"agent_id": "test_agent", "agent_address": "<wallet_address>", "display_name": "Test", "chain_id": "ait-localnet"}'
```

## Database Verification

```bash
# Check agent identities
SELECT * FROM agent_identity WHERE agent_id = '<agent_id>';
```
