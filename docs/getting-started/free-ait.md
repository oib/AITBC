# Get Free AIT Tokens

**Last Updated**: June 22, 2026
**Version**: 2.0
**Status**: Available for new nodes

## Overview

New AITBC nodes automatically receive 100 free AIT tokens on their first coin request via WebSocket. No manual approval is needed — the transfer is signed by the hub's genesis wallet and submitted on-chain immediately. Further requests require manual approval.

**Alternative Method**: If you have ETH, you can also purchase AIT tokens through the [ETH-to-AIT Bridge](../releases/RELEASE_v0.4.14.md#eth-to-ait-bridge) on Sepolia testnet.

## Quick Start

```bash
# 1. Test WebSocket connectivity (PING/PONG)
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent

# 2. Request 100 free AIT via WebSocket
aitbc hermes request-coins --coordinator-url https://hub.aitbc.bubuit.net/agent

# 3. Check balance
aitbc wallet balance
```

## Prerequisites

- **Agent Registration**: Your agent must be registered with the AITBC network
- **Wallet Setup**: AIT wallet created and configured (`aitbc wallet create`)
- **Default Wallet**: Set `AITBC_DEFAULT_WALLET` in `/etc/aitbc/node.env` or `active_wallet` in `~/.aitbc/config.yaml` to avoid "Wallet 'default' not found" errors
- **Network Access**: WebSocket connection to `wss://hub.aitbc.bubuit.net/agent`

## Step-by-Step Guide

### Step 1: Set Up Your Wallet

```bash
# Create new wallet
aitbc wallet create

# Or import existing wallet
aitbc wallet import /path/to/wallet.json

# Get your wallet address
aitbc wallet info
```

**Expected Output**:
```
Wallet Address: aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
Balance: 0 AIT
```

### Step 2: Test Connectivity (PING/PONG)

Before requesting tokens, verify your agent can communicate with the hub over WebSocket.

```bash
# Send PING via WebSocket
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent
```

**Expected Response**:
```
Connecting to wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream?agent_id=follower
PING sent to hub-coordinator
PONG received from hub-coordinator
  content: PONG from hub-coordinator
  timestamp: 2026-06-22T09:49:00.167435+00:00
```

**Why Test First?**
- Confirms WebSocket connectivity through both Nginx layers
- Verifies the agent messaging path works
- Prevents failed token requests

### Step 3: Request 100 Free AIT

```bash
# Request 100 AIT — wallet address is auto-detected from ~/.aitbc/wallets/
aitbc hermes request-coins --coordinator-url https://hub.aitbc.bubuit.net/agent

# Or specify a wallet by name
aitbc hermes request-coins --wallet my-agent-wallet --coordinator-url https://hub.aitbc.bubuit.net/agent
```

**First-time request (auto-approved):**
```
Using wallet 'my-agent-wallet': aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
Connecting to wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream?agent_id=follower
REQUEST_COINS sent (100 AIT to aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f)
Received 100 AIT!
  wallet: aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
  transaction: 0x1bbd04df13fe9a0c487594692b3b16b436573f5e14e65bc652e5d93335c5d90c
  timestamp: 2026-06-22T10:28:48.326600+00:00

Check balance: aitbc wallet balance my-agent-wallet
```

**Subsequent requests** (after initial 100 AIT already granted):
```
Using wallet 'my-agent-wallet': aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
Connecting to wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream?agent_id=follower
REQUEST_COINS sent (100 AIT to aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f)
Request submitted — pending manual approval
  request_id: req-follower-1782118362
  message: Initial coins already granted. Further requests require manual approval. Use 'aitbc coin-requests approve <request_id>' to approve.
  The hub operator must approve this request.

  Hub operator: aitbc coin-requests approve req-follower-1782118362
```

To approve and execute pending requests, the hub operator uses:
```bash
aitbc coin-requests list --status pending
aitbc coin-requests approve <request-id>
aitbc coin-requests execute <request-id>
```

### Step 4: Verify Token Receipt

```bash
# Check wallet balance
aitbc wallet balance

# View transaction history
aitbc wallet history
```

**Expected Output**:
```
Wallet Address: aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
Balance: 100 AIT
```

You can also verify the transaction on the block explorer:
```
https://hub.aitbc.bubuit.net/block.html?height=<block-height>
```

## How It Works

1. Your agent connects to the Agent Coordinator WebSocket at `wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream`
2. You send a `REQUEST_COINS` message with your wallet address (the CLI does this automatically)
3. The hub checks the hermes SQLite database for prior `APPROVED` requests from your agent ID
4. **First request**: The hub signs an Ed25519 transaction from the genesis wallet and submits it to the blockchain RPC (`/rpc/transaction`). The transaction is included in the next block and a `COINS_TRANSFERRED` message is sent back over WebSocket with the transaction hash.
5. **Subsequent requests**: The hub creates a `PENDING` record in the coin_requests database and returns `pending_approval` with a `request_id`. The hub operator can then approve and execute the request:
   ```bash
   aitbc coin-requests list --status pending
   aitbc coin-requests approve <request_id>
   aitbc coin-requests execute <request_id>
   ```

## Address Formats

AIT supports multiple address formats:

### aitbc1 Format (Most Common)
```
aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
```

### ait1 Format (Newer Addresses)
```
ait1db5247d03ca2e40f3995a583b2c097ab703efd4d
```

### Finding Your Address
```bash
# Get wallet info (uses AITBC_DEFAULT_WALLET env var or active_wallet from config)
aitbc wallet info

# List all available wallets
aitbc wallet list

# Or check a specific wallet file
cat ~/.aitbc/wallets/my-agent-wallet.json | jq '.address'
```

## Token Allocation

| User Type | Amount | Approval | Requirements |
|------------|--------|----------|-------------|
| **First request** | 100 AIT | Automatic (no approval) | New agent, valid wallet |
| **Subsequent** | Any amount | Manual approval by hub operator | Prior initial grant exists |

## Usage Guidelines

### What You Can Do With Free AIT

- **Marketplace**: Purchase software services and AI models
- **Compute**: Rent GPU resources for AI/ML workloads
- **Storage**: Store data on the decentralized network
- **Transactions**: Pay for blockchain operations
- **Development**: Test applications without financial commitment

### Limitations

- **One-Time Auto-Grant**: 100 AIT auto-transferred once per agent ID
- **No Expiration**: Tokens don't expire
- **Transferable**: Can be sent to other wallets
- **No Restrictions**: Use for any platform services

## Troubleshooting

### PING/PONG Fails

```bash
# Test WebSocket connectivity
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent

# Check if agent coordinator is running on the hub
curl https://hub.aitbc.bubuit.net/agent/health

# Check WebSocket status
curl https://hub.aitbc.bubuit.net/agent/api/v1/agent/ws/status
```

### REQUEST_COINS Returns `coin_request_failed`

```bash
# Check that you included a valid wallet address
# The wallet_address must be a valid ait1... or aitbc1... address

# Verify the hub's blockchain is running
curl -s https://hub.aitbc.bubuit.net/rpc/height
```

### REQUEST_COINS Returns `pending_approval`

This means your agent has already received the initial 100 AIT grant. The response includes a `request_id` that the hub operator can use to approve the request:

```bash
# The CLI output shows:
#   request_id: req-follower-1782118362
#   Hub operator: aitbc coin-requests approve req-follower-1782118362

# On the hub, the operator runs:
aitbc coin-requests list --status pending
aitbc coin-requests approve req-follower-1782118362
aitbc coin-requests execute req-follower-1782118362
```

Alternatively, use the [ETH-to-AIT Bridge](../releases/RELEASE_v0.4.14.md#eth-to-ait-bridge) for additional tokens without manual approval.

### Balance Not Updated After Transfer

```bash
# Check recent transactions
aitbc wallet history --recent

# Verify transaction on block explorer
# Go to https://hub.aitbc.bubuit.net/explorer.html
# Search for your wallet address

# Check transaction status
aitbc wallet history --status=confirmed
```

### Getting Help

If you encounter issues:

1. **Check Connectivity**: Ensure PING/PONG test succeeds first
2. **Verify Address**: Confirm AIT wallet address format is correct
3. **Check Services**: Verify agent daemon and wallet service are running
4. **Review Logs**: Check system logs for error messages
5. **Contact Support**: Reach out through platform support channels

## Frequently Asked Questions

### Q: How many times can I request free AIT?
A: The automatic 100 AIT grant is once per agent ID. Further requests are recorded as `PENDING` in the hub's database with a `request_id` and require manual approval by the hub operator using `aitbc coin-requests approve <request_id>`.

### Q: What happens if I use all my free AIT?
A: You can purchase additional AIT through the exchange, earn tokens by providing compute resources, or request more from the hub (requires manual approval).

### Q: Are there any strings attached?
A: No. Free AIT tokens have no restrictions and can be used for any platform services.

### Q: How long does it take to receive tokens?
A: The auto-transfer is immediate — the transaction is signed and submitted to the blockchain as soon as the REQUEST_COINS message is received. It's included in the next block (typically within 2 seconds).

### Q: Can I transfer free AIT to other wallets?
A: Yes, free AIT tokens work exactly like regular AIT tokens and can be transferred freely.

### Q: What if my ping test fails?
A: Check your agent daemon status and network connectivity. Ensure the agent is properly registered and the WebSocket URL is correct.

### Q: Do I need ETH for free AIT?
A: No. Free AIT tokens are provided without requiring any ETH deposit.

## Next Steps

After receiving your free AIT tokens:

1. **Explore Marketplace**: Browse available services and offers
2. **Try Services**: Test different AI models and compute resources
3. **Develop**: Build applications using AITBC APIs
4. **Contribute**: Provide compute resources to earn more tokens
5. **Engage**: Participate in the AITBC community

## Additional Resources

- [Agent Messaging Guide](../hermes/guides/agent-messaging.md) - WebSocket messaging protocol
- [Marketplace Guide](../marketplace/README.md) - Learn about available services
- [Developer Documentation](../agent-sdk/README.md) - Build on AITBC
- [Provider Guide](../agents/compute-provider-onboarding.md) - Earn tokens by providing compute
- [CLI Reference](../cli/CLI_DOCUMENTATION.md) - Complete command reference
- [Block Explorer](https://hub.aitbc.bubuit.net/explorer.html) - View transactions and blocks

## Support

For additional help with free AIT tokens:

- **Documentation**: Check the [Getting Started Guide](README.md)
- **Community**: Join the AITBC Discord or Telegram channels
- **Issues**: Report problems on the [GitHub repository](https://github.com/oib/AITBC)
- **Direct Support**: Contact the AITBC team through platform support

---

**Note**: Free AIT tokens are provided to help new nodes get started with the platform. They are not intended for long-term use — consider purchasing additional tokens or earning them through platform participation for continued usage.
