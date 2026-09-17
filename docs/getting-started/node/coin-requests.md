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
aitbc wallet create --name my-wallet
```

### Get Wallet Address

```bash
# List wallets
aitbc wallet list

# Show wallet details
aitbc wallet info --name my-wallet
```

### Check Balance

```bash
# Check balance via RPC
curl -s http://localhost:8202/rpc/account/<your-address>
```

### Wallet Security

- Keep your wallet private keys secure
- Never share private keys
- Use strong passwords for wallet encryption
- Backup wallet files regularly
- Store backups in secure locations

## Requesting Coins via Agent Message

Coin requests go through the **Agent Coordinator** (port 8107), not the
coordinator-api on 8203 — the old `/v1/agent/messages/send` route no longer
exists. Use the CLI:

```bash
# Request free coins from the hub over the agent WebSocket
aitbc agent-msg request-coins --wallet my-wallet --amount 1000

# Or the one-time initial grant flow
aitbc coin-requests request
```

**Example:**

```bash
aitbc agent-msg request-coins --wallet my-wallet --amount 1000
```

The receiving address comes from the wallet; first requests auto-grant up to
3 AIT, larger or repeat requests go to manual approval on the hub.

The CLI formats and signs the `REQUEST_COINS` message for you. To send the
raw message yourself instead:

```bash
aitbc agent-msg send \
  'REQUEST_COINS: 1000 ait coins to address 0x71C7656EC7ab88b098defB751B7401B5f6d8976F' \
  --to-agent owl-hub
```

## Check Request Status

The hub's CLI can list coin requests:

```bash
# On the hub node
aitbc coin-requests list
```

## Request Format Options

**Natural language:**

```
REQUEST_COINS: 1000 ait coins to address 0x71C7656EC7ab88b098defB751B7401B5f6d8976F
```

**JSON format:**

```json
{
  "cmd": "REQUEST_COINS",
  "amount": 1000,
  "to_address": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"
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
aitbc coin-requests approve --request-id <request-id> --reason "New node onboarding"

# Execute transfer
aitbc coin-requests execute --request-id <request-id>
```

## See Also

- [Agent Messaging](agent-messaging.md)
- [Blockchain Setup](blockchain-setup.md)
- [Configuration Guide](configuration-guide.md)
