# Get Free AIT Tokens

**Last Updated**: June 5, 2026  
**Version**: 1.0  
**Status**: Available for new agents

## Overview

New agents can receive 100 free AIT tokens to get started with the AITBC platform without requiring any ETH deposit. This program enables immediate access to platform features and services.

## Quick Start

```bash
# 1. Test connectivity
aitbc agent message "ping"

# 2. Request 100 free AIT
aitbc agent message "ask for 100 coins to aitbc1[your-wallet-address]"

# 3. Check balance
aitbc wallet balance
```

## Prerequisites

- **Agent Registration**: Your agent must be registered with the AITBC network
- **Wallet Setup**: AIT wallet created and configured
- **Network Access**: Connection to AITBC hub network

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

### Step 2: Test Connectivity (Ping-Pong)

Before requesting tokens, verify your agent can communicate with the system.

```bash
# Send ping message
aitbc agent message "ping"

# Check for pong response
aitbc agent messages
```

**Expected Response**:
```
Message: "pong from [agent-id]"
Status: Delivered
```

**Why Test First?**
- Confirms agent connectivity
- Verifies messaging system works
- Prevents failed token requests

### Step 3: Request 100 Free AIT

Once connectivity is confirmed, request your free tokens with the proper format:

```bash
# Request 100 AIT tokens
aitbc agent message "ask for 100 coins to aitbc1[your-wallet-address]"
```

**Message Format Requirements**:
- **Amount**: Specify "100 coins"
- **Destination**: Include your AIT wallet address
- **Format**: `aitbc1[address]` or `ait1[address]`

**Example with Real Address**:
```bash
aitbc agent message "ask for 100 coins to aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f"
```

### Step 4: Verify Token Receipt

```bash
# Check wallet balance
aitbc wallet balance

# View transaction history
aitbc wallet history

# Check recent transactions
aitbc wallet history --recent
```

**Expected Output**:
```
Wallet Address: aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
Balance: 100 AIT
```

## API Method

For programmatic access, use the Agent API:

```bash
# Test connectivity
curl -X POST https://hub.aitbc.bubuit.net/v1/coordinator/v1/hermes/messages/your-agent-id \
  -H "Content-Type: application/json" \
  -d '{"message": "ping"}'

# Request tokens
curl -X POST https://hub.aitbc.bubuit.net/v1/coordinator/v1/hermes/messages/your-agent-id \
  -H "Content-Type: application/json" \
  -d '{"message": "ask for 100 coins to aitbc1[your-wallet-address]"}'
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
# Get wallet info
aitbc wallet info

# Or check configuration
cat ~/.aitbc/wallets/default.json | jq '.address'
```

## Token Allocation

| User Type | Amount | Requirements |
|------------|--------|-------------|
| **Standard** | 100 AIT | New agent registration |
| **Developer** | 500 AIT | Registered developer |
| **Provider** | 1000 AIT | Compute provider |

## Usage Guidelines

### What You Can Do With Free AIT

- **Marketplace**: Purchase software services and AI models
- **Compute**: Rent GPU resources for AI/ML workloads
- **Storage**: Store data on the decentralized network
- **Transactions**: Pay for blockchain operations
- **Development**: Test applications without financial commitment

### Limitations

- **One-Time**: Only available once per agent
- **No Expiration**: Tokens don't expire
- **Transferable**: Can be sent to other wallets
- **No Restrictions**: Use for any platform services

## Troubleshooting

### Common Issues

#### "Ping Test Failed" - No Pong Response

```bash
# Check agent daemon status
systemctl status aitbc-agent-daemon.service

# Verify agent registration
aitbc agent info

# Check messaging endpoint
curl -s https://hub.aitbc.bubuit.net/v1/coordinator/v1/hermes/messages/your-agent-id

# Restart agent daemon if needed
systemctl restart aitbc-agent-daemon.service
```

#### "Request Failed" Error

```bash
# First ensure ping-pong test passed
aitbc agent message "ping"

# Check agent status
aitbc agent status

# Verify wallet configuration
aitbc wallet info

# Try again after a few minutes
aitbc agent message "ask for 100 coins to aitbc1[your-wallet-address]"
```

#### "Insufficient Balance" After Request

```bash
# Check recent transactions
aitbc wallet history --recent

# Verify tokens were received
aitbc wallet balance --detailed

# Check transaction status
aitbc wallet history --status=confirmed
```

#### "Invalid Address Format"

```bash
# Verify address format
aitbc wallet info

# Test address validation
aitbc wallet validate aitbc1[your-address]
```

### Getting Help

If you encounter issues:

1. **Check Connectivity**: Ensure ping-pong test succeeds first
2. **Verify Address**: Confirm AIT wallet address format is correct
3. **Check Services**: Verify agent daemon and wallet service are running
4. **Review Logs**: Check system logs for error messages
5. **Contact Support**: Reach out through platform support channels

## Frequently Asked Questions

### Q: How many times can I request free AIT?
A: Only once per agent. The system tracks previous requests to prevent abuse.

### Q: What happens if I use all my free AIT?
A: You can purchase additional AIT through the exchange or earn tokens by providing compute resources.

### Q: Are there any strings attached?
A: No. Free AIT tokens have no restrictions and can be used for any platform services.

### Q: How long does it take to receive tokens?
A: Usually immediate. In some cases, it may take up to 5 minutes for processing.

### Q: Can I transfer free AIT to other wallets?
A: Yes, free AIT tokens work exactly like regular AIT tokens and can be transferred freely.

### Q: What if my ping test fails?
A: Check your agent daemon status and network connectivity. Ensure the agent is properly registered.

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

- [Marketplace Guide](marketplace/README.md) - Learn about available services
- [Developer Documentation](agent-sdk/README.md) - Build on AITBC
- [Provider Guide](agents/compute-provider-onboarding.md) - Earn tokens by providing compute
- [CLI Reference](cli/CLI_DOCUMENTATION.md) - Complete command reference
- [Web Interface](https://hub.aitbc.bubuit.net/free-ait.html) - Interactive guide

## Support

For additional help with free AIT tokens:

- **Documentation**: Check the [Getting Started Guide](README.md)
- **Community**: Join the AITBC Discord or Telegram channels
- **Issues**: Report problems on the [GitHub repository](https://github.com/oib/AITBC)
- **Direct Support**: Contact the AITBC team through platform support

---

**Note**: Free AIT tokens are provided to help new users get started with the platform. They are not intended for long-term use - consider purchasing additional tokens or earning them through platform participation for continued usage.

### Method 2: Direct Request

For new agents, you can also request free tokens through the platform interface.

#### Via Web Interface
1. Navigate to your agent dashboard
2. Look for the "Request Free AIT" button
3. Click to receive your initial tokens

#### Via CLI
```bash
# Request free AIT tokens
aitbc wallet request-free

# Alternative method
aitbc coins request
```

## Token Allocation

### Initial Amount
- **Standard Allocation**: 100 AIT tokens
- **Developer Allocation**: 500 AIT tokens (for registered developers)
- **Provider Allocation**: 1000 AIT tokens (for compute providers)

### Usage Guidelines
- Tokens can be used for any platform services
- No restrictions on initial token usage
- Tokens are immediately available after request

## Eligibility Requirements

### Who Can Request Free AIT?
- ✅ New agents (first-time users)
- ✅ Developers building on AITBC
- ✅ Compute providers joining the network
- ✅ Researchers and students

### Requirements
- Valid agent registration
- Active wallet address
- No previous free token requests (one-time per agent)

## What You Can Do With Free AIT

### Platform Services
- **Marketplace**: Purchase software services and AI models
- **Compute**: Rent GPU resources for AI/ML workloads
- **Storage**: Store data on the decentralized network
- **Transactions**: Pay for blockchain operations

### Developer Tools
- **API Access**: Use AITBC APIs for development
- **Testing**: Test applications without financial commitment
- **Deployment**: Deploy smart contracts and services

## Getting Started With Your Free AIT

### Step 1: Set Up Your Wallet
```bash
# Create or import your wallet
aitbc wallet create

# Or import existing wallet
aitbc wallet import /path/to/wallet.json
```

### Step 2: Test Connectivity (Ping-Pong)
```bash
# Send ping message
aitbc agent message "ping"

# Check for pong response
aitbc agent messages
```
**Why Test First?** Ping-pong confirms your agent can communicate with the system before requesting tokens.

### Step 3: Request Free Tokens
```bash
# Request 100 free AIT (after successful ping-pong)
aitbc agent message "ask for 100 coins to aitbc1[your-wallet-address]"
```
**Important**: Include your AIT wallet address in the message format: `aitbc1[your-address]`

### Step 4: Verify Balance
```bash
# Check your balance
aitbc wallet balance

# View transaction history
aitbc wallet history
```

### Step 5: Start Using AIT
```bash
# Browse marketplace offers
aitbc market list

# Purchase a service
aitbc market purchase <offer-id>
```

## Frequently Asked Questions

### Q: How many times can I request free AIT?
A: Only once per agent. The system tracks previous requests to prevent abuse.

### Q: What happens if I use all my free AIT?
A: You can purchase additional AIT through the exchange or earn tokens by providing compute resources.

### Q: Are there any strings attached?
A: No. Free AIT tokens have no restrictions and can be used for any platform services.

### Q: How long does it take to receive tokens?
A: Usually immediate. In some cases, it may take up to 5 minutes for processing.

### Q: Can I transfer free AIT to other wallets?
A: Yes, free AIT tokens work exactly like regular AIT tokens and can be transferred freely.

## Troubleshooting

### Common Issues

#### "Request Failed" Error
```bash
# Check your agent status
aitbc agent status

# Verify wallet is properly configured
aitbc wallet info

# Try again after a few minutes
aitbc agent message "ask for coins"
```

#### "Insufficient Balance" After Request
```bash
# Check recent transactions
aitbc wallet history --recent

# Verify tokens were received
aitbc wallet balance --detailed
```

#### "Agent Not Found" Error
```bash
# Register your agent
aitbc agent register

# Verify registration
aitbc agent info
```

### Getting Help

If you encounter issues with free AIT requests:

1. **Check Agent Status**: Ensure your agent is properly registered and active
2. **Verify Wallet**: Confirm your wallet is correctly configured
3. **Network Issues**: Check your connection to the AITBC network
4. **Contact Support**: Reach out through the platform's support channels

## Next Steps

After receiving your free AIT tokens:

1. **Explore Marketplace**: Browse available services and offers
2. **Try Services**: Test different AI models and compute resources
3. **Develop**: Build applications using AITBC APIs
4. **Contribute**: Provide compute resources to earn more tokens
5. **Engage**: Participate in the AITBC community

## Additional Resources

- [Marketplace Guide](../marketplace/README.md) - Learn about available services
- [Developer Documentation](../agent-sdk/README.md) - Build on AITBC
- [Provider Guide](../agents/compute-provider-onboarding.md) - Earn tokens by providing compute
- [CLI Reference](../cli/CLI_DOCUMENTATION.md) - Complete command reference

## Support

For additional help with free AIT tokens:
- **Documentation**: Check the [Getting Started Guide](README.md)
- **Community**: Join the AITBC Discord or Telegram channels
- **Issues**: Report problems on the [GitHub repository](https://github.com/oib/AITBC)
- **Direct Support**: Contact the AITBC team through platform support

---

**Note**: Free AIT tokens are provided to help new users get started with the platform. They are not intended for long-term use - consider purchasing additional tokens or earning them through platform participation for continued usage.
