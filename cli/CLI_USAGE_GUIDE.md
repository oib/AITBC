# AITBC Enhanced CLI - Complete Usage Guide

## Overview

The AITBC Enhanced CLI provides comprehensive wallet and blockchain management capabilities with professional-grade features and user-friendly interfaces.

## Installation

The CLI tool is located at `/opt/aitbc/cli/simple_wallet.py` and is deployed on both aitbc1 and aitbc nodes.

## Commands

### 1. Create Wallet
Create a new encrypted wallet with automatic key generation.

```bash
python /opt/aitbc/cli/simple_wallet.py create --name <wallet-name> --password-file <path-to-password-file>
```

**Examples:**
```bash
# Create wallet with password file
python /opt/aitbc/cli/simple_wallet.py create --name my-wallet --password-file /var/lib/aitbc/keystore/.password

# Create wallet with interactive password
python /opt/aitbc/cli/simple_wallet.py create --name my-wallet
```

**Output:**
```
Wallet created: my-wallet
Address: ait1abc123def456...
Keystore: /var/lib/aitbc/keystore/my-wallet.json
Wallet address: ait1abc123def456...
```

### 2. Send Transaction
Send AIT coins from one wallet to another with automatic signing.

```bash
python /opt/aitbc/cli/simple_wallet.py send --from <sender-wallet> --to <recipient-address> --amount <amount> --password-file <path-to-password-file>
```

**Examples:**
```bash
# Send 1000 AIT with default fee
python /opt/aitbc/cli/simple_wallet.py send --from genesis --to ait1abc123... --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Send with custom fee and RPC URL
python /opt/aitbc/cli/simple_wallet.py send --from my-wallet --to ait1def456... --amount 500 --fee 5 --password-file /var/lib/aitbc/keystore/.password --rpc-url http://localhost:8006
```

**Output:**
```
Transaction submitted successfully
From: ait1abc123def456...
To: ait1def456abc789...
Amount: 1000 AIT
Fee: 10 AIT
Transaction hash: 0x123abc456def...
```

### 3. List Wallets
Display all available wallets with their addresses.

```bash
python /opt/aitbc/cli/simple_wallet.py list [--format table|json]
```

**Examples:**
```bash
# Table format (default)
python /opt/aitbc/cli/simple_wallet.py list

# JSON format
python /opt/aitbc/cli/simple_wallet.py list --format json
```

**Output:**
```
Wallets:
  genesis: ait1abc123def456...
  treasury: ait1def456abc789...
  my-wallet: ait1ghi789jkl012...
```

### 4. Get Balance
Retrieve wallet balance, nonce, and address information.

```bash
python /opt/aitbc/cli/simple_wallet.py balance --name <wallet-name> [--rpc-url <url>]
```

**Examples:**
```bash
# Get balance for specific wallet
python /opt/aitbc/cli/simple_wallet.py balance --name my-wallet

# Get balance with custom RPC URL
python /opt/aitbc/cli/simple_wallet.py balance --name genesis --rpc-url http://10.1.223.40:8006
```

**Output:**
```
Wallet: my-wallet
Address: ait1ghi789jkl012...
Balance: 1500 AIT
Nonce: 5
```

### 5. Get Transactions
Retrieve wallet transaction history with detailed information.

```bash
python /opt/aitbc/cli/simple_wallet.py transactions --name <wallet-name> [--limit <number>] [--format table|json]
```

**Examples:**
```bash
# Get last 10 transactions
python /opt/aitbc/cli/simple_wallet.py transactions --name my-wallet

# Get last 5 transactions in JSON format
python /opt/aitbc/cli/simple_wallet.py transactions --name my-wallet --limit 5 --format json
```

**Output:**
```
Transactions for my-wallet:
  1. Hash: 0x123abc456def...
     Amount: 1000 AIT
     Fee: 10 AIT
     Type: transfer

  2. Hash: 0x789ghi012jkl...
     Amount: 500 AIT
     Fee: 5 AIT
     Type: transfer
```

### 6. Get Chain Information
Display blockchain network information and configuration.

```bash
python /opt/aitbc/cli/simple_wallet.py chain [--rpc-url <url>]
```

**Examples:**
```bash
# Get chain information
python /opt/aitbc/cli/simple_wallet.py chain

# Get chain information from remote node
python /opt/aitbc/cli/simple_wallet.py chain --rpc-url http://10.1.223.40:8006
```

**Output:**
```
Blockchain Information:
  Chain ID: ait-mainnet
  Supported Chains: ait-mainnet
  RPC Version: v0.2.2
  Height: 1234
```

### 7. Get Network Status
Display current network status and health information.

```bash
python /opt/aitbc/cli/simple_wallet.py network [--rpc-url <url>]
```

**Examples:**
```bash
# Get network status
python /opt/aitbc/cli/simple_wallet.py network

# Get network status in JSON format
python /opt/aitbc/cli/simple_wallet.py network --format json
```

**Output:**
```
Network Status:
  Height: 1234
  Latest Block: 0xabc123def456...
  Chain ID: ait-mainnet
  RPC Version: v0.2.2
  Timestamp: 1711706400
```

## Advanced Features

### Output Formats

Most commands support both table and JSON output formats:

```bash
# Table format (human-readable)
python /opt/aitbc/cli/simple_wallet.py list --format table

# JSON format (machine-readable)
python /opt/aitbc/cli/simple_wallet.py list --format json
```

### Remote Node Operations

Connect to different RPC endpoints:

```bash
# Local node
python /opt/aitbc/cli/simple_wallet.py balance --name my-wallet --rpc-url http://localhost:8006

# Remote node
python /opt/aitbc/cli/simple_wallet.py balance --name my-wallet --rpc-url http://10.1.223.40:8006
```

### Password Management

Multiple password input methods:

```bash
# Password file
python /opt/aitbc/cli/simple_wallet.py send --from wallet --to address --amount 100 --password-file /path/to/password

# Interactive password
python /opt/aitbc/cli/simple_wallet.py send --from wallet --to address --amount 100

# Direct password (not recommended for production)
python /opt/aitbc/cli/simple_wallet.py send --from wallet --to address --amount 100 --password mypassword
```

## Common Workflows

### 1. Complete Wallet Setup
```bash
# Create wallet
python /opt/aitbc/cli/simple_wallet.py create --name my-wallet --password-file /var/lib/aitbc/keystore/.password

# Get wallet address
WALLET_ADDR=$(python /opt/aitbc/cli/simple_wallet.py balance --name my-wallet --format json | jq -r '.address')

# Check balance
python /opt/aitbc/cli/simple_wallet.py balance --name my-wallet
```

### 2. Transaction Workflow
```bash
# Check sender balance
python /opt/aitbc/cli/simple_wallet.py balance --name sender-wallet

# Send transaction
python /opt/aitbc/cli/simple_wallet.py send --from sender-wallet --to $WALLET_ADDR --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Monitor transaction
python /opt/aitbc/cli/simple_wallet.py transactions --name sender-wallet --limit 3

# Check recipient balance
python /opt/aitbc/cli/simple_wallet.py balance --name recipient-wallet
```

### 3. Network Monitoring
```bash
# Check network status
python /opt/aitbc/cli/simple_wallet.py network

# Check chain information
python /opt/aitbc/cli/simple_wallet.py chain

# List all wallets
python /opt/aitbc/cli/simple_wallet.py list

# Check all wallet balances
for wallet in $(python /opt/aitbc/cli/simple_wallet.py list --format json | jq -r '.[].name'); do
  echo "Wallet: $wallet"
  python /opt/aitbc/cli/simple_wallet.py balance --name $wallet
  echo "---"
done
```

## Cross-Node Operations

### aitbc1 to aitbc Operations
```bash
# On aitbc1 - check network status
python /opt/aitbc/cli/simple_wallet.py network

# On aitbc - check network status
ssh aitbc 'python /opt/aitbc/cli/simple_wallet.py network'

# Send from aitbc1 to aitbc wallet
python /opt/aitbc/cli/simple_wallet.py send --from genesis --to $AITBC_WALLET_ADDR --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Check balance on aitbc
ssh aitbc "python /opt/aitbc/cli/simple_wallet.py balance --name aitbc-user"
```

## Error Handling

The CLI provides comprehensive error handling:

- **Wallet Not Found**: Clear error message when wallet doesn't exist
- **Password Errors**: Proper password validation and error messages
- **Network Errors**: RPC connectivity issues with helpful messages
- **Transaction Errors**: Detailed transaction failure information
- **JSON Parsing**: Graceful handling of malformed responses

## Security Best Practices

1. **Password Management**: Use password files instead of command-line passwords
2. **File Permissions**: Ensure keystore files have proper permissions (600)
3. **Network Security**: Use HTTPS for RPC endpoints in production
4. **Backup**: Regularly backup keystore files
5. **Validation**: Always verify transaction details before sending

## Integration with Scripts

The CLI is designed for easy integration with shell scripts:

```bash
#!/bin/bash
# Get wallet balance in script
BALANCE=$(python /opt/aitbc/cli/simple_wallet.py balance --name my-wallet --format json | jq -r '.balance')

if [ "$BALANCE" -gt "1000" ]; then
  echo "Sufficient balance for transaction"
  python /opt/aitbc/cli/simple_wallet.py send --from my-wallet --to $RECIPIENT --amount 1000 --password-file /var/lib/aitbc/keystore/.password
else
  echo "Insufficient balance: $BALANCE AIT"
fi
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Check file permissions on keystore directory
2. **Connection Refused**: Verify RPC service is running
3. **Invalid Password**: Ensure password file contains correct password
4. **Wallet Not Found**: Verify wallet name is correct

### Debug Mode

Add verbose output for debugging:

```bash
# Enable debug output (if implemented)
python /opt/aitbc/cli/simple_wallet.py --debug balance --name my-wallet
```

## Future Enhancements

Planned features for future releases:

- **Batch Operations**: Send multiple transactions in one command
- **Smart Contracts**: Deploy and interact with smart contracts
- **Staking**: Delegate and undelegate tokens
- **Governance**: Participate in governance proposals
- **NFT Support**: Create and manage NFTs
- **Multi-signature**: Create and manage multi-sig wallets

## Support

For support and issues:

1. Check the error messages for specific guidance
2. Verify network connectivity and service status
3. Review this documentation for proper usage
4. Check system logs for additional error details
