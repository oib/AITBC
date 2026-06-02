# Staking Integration

Hermes agents can stake AITBC tokens to participate in consensus and earn rewards.

## CLI Commands

- `aitbc wallet stake <amount> --duration <days> --wallet <wallet>` - Stake tokens on hub blockchain
- `aitbc wallet unstake <stake_id> --wallet <wallet>` - Unstake tokens after lock period
- `aitbc wallet staking-info --wallet <wallet>` - Query staking information

## RPC Endpoints

- `POST /rpc/staking/stake` - Submit staking transaction
- `POST /rpc/staking/unstake` - Submit unstaking transaction
- `GET /rpc/staking/{address}` - Query staking info for address

## Usage Example

```bash
# Check wallet balance
aitbc wallet balance --wallet my-agent-wallet

# Stake tokens (e.g., 100 AITBC for 30 days)
aitbc wallet stake 100 --duration 30 --wallet my-agent-wallet

# Verify staking info
aitbc wallet staking-info --wallet my-agent-wallet

# Unstake tokens (after lock period)
aitbc wallet unstake <stake_id> --wallet my-agent-wallet
```

## Use Cases

- Participate in network consensus
- Earn staking rewards
- Lock tokens for long-term commitment

## RPC Endpoint Testing

```bash
# Test staking endpoint
curl -X POST http://hub.aitbc.bubuit.net:8202/rpc/staking/stake \
  -H "Content-Type: application/json" \
  -d '{"address": "<wallet_address>", "amount": 1000000000000000000, "lock_days": 30, "chain_id": "ait-hub.aitbc.bubuit.net"}'
```

## Database Verification

```bash
# Check stakes
SELECT * FROM stake WHERE address = '<wallet_address>';
```
