# Staking Integration

Agent agents can stake the network tokens to participate in consensus and earn rewards.

## CLI Commands

- `aitbc wallet --wallet-name <wallet> stake --amount <amount> --duration <days>` - Stake tokens on hub blockchain
- `aitbc wallet --wallet-name <wallet> unstake --stake-id <stake_id>` - Unstake tokens after lock period
- `aitbc wallet --wallet-name <wallet> staking-info` - Query staking information

## RPC Endpoints

- `POST /rpc/staking/stake` - Submit staking transaction
- `POST /rpc/staking/unstake` - Submit unstaking transaction
- `GET /rpc/staking/{address}` - Query staking info for address

## Usage Example

```bash
# Check wallet balance
aitbc wallet balance --name my-agent-wallet

# Stake tokens (e.g., 100 AITBC for 30 days)
aitbc wallet --wallet-name my-agent-wallet stake --amount 100 --duration 30

# Verify staking info
aitbc wallet --wallet-name my-agent-wallet staking-info

# Unstake tokens (after lock period)
aitbc wallet --wallet-name my-agent-wallet unstake --stake-id <stake_id>
```

## Use Cases

- Participate in network consensus
- Earn staking rewards
- Lock tokens for long-term commitment

## RPC Endpoint Testing

```bash
# Test staking endpoint — signature, nonce and timestamp are ALL required
# (this route is signature-authenticated; no X-API-Key is needed):
#   signature: over {"address", "amount", "chain_id", "action": "stake", "nonce", "timestamp"}
#   nonce:     must equal the account's current on-chain nonce
#   timestamp: unix seconds, within 300 s of server time (STAKE_AUTH_MAX_AGE_SECONDS)
curl -X POST https://hub.aitbc.bubuit.net/rpc/staking/stake \
  -H "Content-Type: application/json" \
  -d '{"address": "<wallet_address>", "amount": 1000000000000000000, "lock_days": 30, "chain_id": "ait-hub.aitbc.bubuit.net", "signature": "<sig>", "nonce": <account_nonce>, "timestamp": <unix_seconds>}'
```

## Database Verification

```bash
# Check stakes (tables are chain-scoped — DB at $AITBC_DATA_DIR/data/<chain_id>/chain.db)
sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
  "SELECT * FROM stake WHERE chain_id = 'ait-hub.aitbc.bubuit.net' AND address = '<wallet_address>';"
```
