# Coin Requests

This guide covers requesting free coins from the hub via the coin approval system and wallet management.

## Understanding the Coin Approval System

The hub operates a coin approval system with three modes:
- **Manual**: Requires CLI approval (default)
- **Automatic**: Auto-approves requests under configured limits
- **AI**: Uses Ollama for intelligent approval decisions

## Wallet Setup

Before requesting coins, you need a wallet address.

### Create Wallet

```bash
# Generate new wallet
/opt/aitbc/venv/bin/aitbc wallet create my-wallet
```

### Get Wallet Address

```bash
# List wallets
/opt/aitbc/venv/bin/aitbc wallet list

# Show wallet details
/opt/aitbc/venv/bin/aitbc wallet show my-wallet
```

### Check Balance

```bash
# Check balance via RPC
curl -s http://localhost:8006/rpc/account/<your-address>
```

### Wallet Security

- Keep your wallet private keys secure
- Never share private keys
- Use strong passwords for wallet encryption
- Backup wallet files regularly
- Store backups in secure locations

## Requesting Coins via Hermes Message

Send a REQUEST_COINS message to the hub:

```bash
curl -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "<your-agent-id>",
    "recipient": "owl-hub",
    "content": "REQUEST_COINS: <amount> ait coins to address <your-wallet-address>",
    "message_type": "direct",
    "timestamp": "2026-05-30T17:00:00Z"
  }'
```

**Example:**
```bash
curl -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "my-node",
    "recipient": "owl-hub",
    "content": "REQUEST_COINS: 1000 ait coins to address ait1xyz123abc",
    "message_type": "direct",
    "timestamp": "2026-05-30T17:00:00Z"
  }'
```

## Check Request Status

The hub's CLI can list coin requests:

```bash
# On the hub node
/opt/aitbc/venv/bin/aitbc coin-requests list
```

## Request Format Options

**Natural language:**
```
REQUEST_COINS: 1000 ait coins to address ait1xyz123abc
```

**JSON format:**
```json
{
  "cmd": "REQUEST_COINS",
  "amount": 1000,
  "to_address": "ait1xyz123abc"
}
```

## Approval Process

1. **Request received**: Status = PENDING
2. **Manual approval**: Hub operator approves via CLI
3. **Transaction execution**: Coins transferred from genesis wallet
4. **Notification**: Sender notified of completion

**Manual approval on hub:**
```bash
# Approve request
/opt/aitbc/venv/bin/aitbc coin-requests approve <request-id> --reason "New node onboarding"

# Execute transfer
/opt/aitbc/venv/bin/aitbc coin-requests execute <request-id>
```

## See Also

- [Hermes Messaging](hermes-messaging.md)
- [Blockchain Setup](blockchain-setup.md)
- [Configuration Guide](configuration-guide.md)
