# AITBC CLI - Complete Usage Guide

## Overview

The AITBC CLI provides comprehensive blockchain and wallet management capabilities with professional-grade features and user-friendly interfaces.

## Installation

The CLI tool is located at `/opt/aitbc/aitbc-cli` and is deployed on both aitbc and aitbc1 nodes. The tool is accessible via the `aitbc` alias after sourcing your shell configuration.

## Commands

The AITBC CLI provides 27 commands for comprehensive blockchain management:

### Available Commands
- `create` - Create a new wallet
- `send` - Send AIT
- `list` - List wallets
- `balance` - Get wallet balance
- `transactions` - Get wallet transactions
- `chain` - Get blockchain information
- `network` - Get network status
- `analytics` - Blockchain analytics and statistics
- `marketplace` - Marketplace operations
- `ai-ops` - AI compute operations
- `mining` - Mining operations and status
- `agent` - AI agent workflow and execution management
- `openclaw` - OpenClaw agent ecosystem operations
- `workflow` - Workflow automation and management
- `resource` - Resource management and optimization
- `system` - System status and information
- `blockchain` - Blockchain operations
- `wallet` - Wallet operations
- `all-balances` - Show all wallet balances
- `import` - Import wallet from private key
- `export` - Export private key from wallet
- `delete` - Delete wallet
- `rename` - Rename wallet
- `batch` - Send multiple transactions
- `market-list` - List marketplace items
- `market-create` - Create marketplace listing
- `ai-submit` - Submit AI compute job
- `simulate` - Simulate blockchain scenarios and test environments

### 1. List Wallets
Display all available wallets with their addresses.

```bash
aitbc list
```

**Output:**
```
Wallets:
  openclaw-backup: ait1cebd266469be5f85b5f0052f1556b5d708b42de9
  openclaw-trainee: ait10a252a31c79939c689bf392e960afc7861df5ee9
```

### 2. Get Balance
Retrieve wallet balance, nonce, and address information.

```bash
aitbc balance --name <wallet-name>
```

**Examples:**
```bash
# Get balance for specific wallet
aitbc balance --name openclaw-backup
```

**Output:**
```
Wallet: openclaw-backup
Address: ait1cebd266469be5f85b5f0052f1556b5d708b42de9
Balance: 0 AIT
Nonce: 0
```

### 3. Get Chain Information
Display blockchain network information and configuration.

```bash
aitbc chain
```

**Output:**
```
Blockchain Information:
  Chain ID: ait-mainnet
  Supported Chains: ait-mainnet
  Height: 22502
  Latest Block: 0x4d6cfbf2c3e758...
  Proposer: none
```

### 4. Get Network Status
Display current network status and health information.

```bash
aitbc network
```

**Output:**
```
Network Status:
  Height: 22502
  Latest Block: 0x4d6cfbf2c3e758...
  Chain ID: ait-mainnet
  Tx Count: 0
  Timestamp: 2026-03-31T13:24:55.238626
```

### 5. System Status
Get comprehensive system status and information.

```bash
aitbc system
```

**Output:**
```
System operation completed
```

### 6. Analytics
Get blockchain analytics and statistics.

```bash
aitbc analytics
```

**Output:**
```
Blockchain Analytics (blocks):
  Current Height: 22502
  Latest Block: 0x4d6cfbf2c3e75831e93a6f400ac3c8ccef86c17b5b3a1e0cf88013e6173f9cf2
  Timestamp: 2026-03-31T13:24:55.238626
  Tx Count: 0
  Status: Active
```

### 7. Marketplace Operations
List marketplace items and create listings.

```bash
# List marketplace items
aitbc marketplace --action list

# Create marketplace listing
aitbc marketplace --action create --name <name> --price <price> --description <description>
```

**Output:**
```
Marketplace list:
  Items: [{'name': 'AI Compute Hour', 'price': 100, 'provider': 'GPU-Miner-1'}, ...]
  Total Items: 3
```

### 8. Wallet Operations
Comprehensive wallet management.

```bash
# Wallet operations
aitbc wallet

# All balances
aitbc all-balances
```

## Advanced Features

### Output Formats

Most commands support both table and JSON output formats:

```bash
# Table format (human-readable)
/opt/aitbc/aitbc-cli wallet list --format table

# JSON format (machine-readable)
/opt/aitbc/aitbc-cli wallet list --format json
```

### Remote Node Operations

Connect to different RPC endpoints:

```bash
# Local node
/opt/aitbc/aitbc-cli wallet balance my-wallet --rpc-url http://localhost:8006

# Remote node
/opt/aitbc/aitbc-cli wallet balance my-wallet --rpc-url http://10.1.223.40:8006
```

### Password Management

Multiple password input methods:

```bash
# Password file
/opt/aitbc/aitbc-cli wallet send wallet --to address --amount 100 --password-file /path/to/password

# Interactive password
/opt/aitbc/aitbc-cli wallet send wallet --to address --amount 100

# Direct password (not recommended for production)
/opt/aitbc/aitbc-cli wallet send wallet --to address --amount 100 --password mypassword
```

## Common Workflows

### 1. Complete Wallet Setup
```bash
# Create wallet
/opt/aitbc/aitbc-cli wallet create my-wallet --password-file /var/lib/aitbc/keystore/.password

# Get wallet address
WALLET_ADDR=$(/opt/aitbc/aitbc-cli wallet balance my-wallet --format json | jq -r '.address')

# Check balance
/opt/aitbc/aitbc-cli wallet balance my-wallet
```

### 2. Transaction Workflow
```bash
# Check sender balance
/opt/aitbc/aitbc-cli wallet balance sender-wallet

# Send transaction
/opt/aitbc/aitbc-cli wallet send sender-wallet --to $WALLET_ADDR --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Monitor transaction
/opt/aitbc/aitbc-cli wallet transactions sender-wallet --limit 3

# Check recipient balance
/opt/aitbc/aitbc-cli wallet balance recipient-wallet
```

### 3. Network Monitoring
```bash
# Check network status
/opt/aitbc/aitbc-cli network status

# Check chain information
/opt/aitbc/aitbc-cli blockchain info

# List all wallets
/opt/aitbc/aitbc-cli wallet list

# Check all wallet balances
for wallet in $(/opt/aitbc/aitbc-cli wallet list --format json | jq -r '.[].name'); do
  echo "Wallet: $wallet"
  /opt/aitbc/aitbc-cli wallet balance $wallet
  echo "---"
done
```

## Cross-Node Operations

### aitbc1 to aitbc Operations
```bash
# On aitbc1 - check network status
/opt/aitbc/aitbc-cli network status

# On aitbc - check network status
ssh aitbc '/opt/aitbc/aitbc-cli network status'

# Send from aitbc1 to aitbc wallet
/opt/aitbc/aitbc-cli wallet send genesis --to $AITBC_WALLET_ADDR --amount 1000 --password-file /var/lib/aitbc/keystore/.password

# Check balance on aitbc
ssh aitbc "/opt/aitbc/aitbc-cli wallet balance aitbc-user"
```

## Error Handling

The CLI provides comprehensive error handling with specific exception types:

### Improved Error Handling (April 2026)
Recent improvements to error handling across all services:

- **Specific Exception Types**: Replaced generic `except Exception` with specific exception types
- **Network Errors**: `ConnectionError`, `Timeout`, `HTTPError` for network operations
- **File Operations**: `FileNotFoundError`, `PermissionError`, `IOError` for file access
- **Data Processing**: `JSONDecodeError`, `KeyError`, `StopIteration` for data operations
- **System Errors**: `OSError`, `psutil.Error` for system operations

### Service Error Handling
All services now have improved error handling:

- **monitor.py**: Handles JSON decode errors, file not found, permission errors
- **real_marketplace_launcher.py**: Handles subprocess errors, file access errors
- **blockchain_http_launcher.py**: Handles subprocess errors, connection issues
- **gpu_marketplace_launcher.py**: Handles subprocess errors, system errors
- **miner_management.py**: Handles network errors, JSON decode errors, data processing errors

### CLI Error Messages
The CLI provides clear, actionable error messages:

- **Wallet Not Found**: Clear error message when wallet doesn't exist
- **Invalid Parameters**: Detailed parameter validation errors
- **Network Errors**: RPC connectivity issues with helpful messages
- **Transaction Errors**: Detailed transaction failure information
- **System Errors**: System-level error information with context

## Security Best Practices

1. **Password Management**: Use password files instead of command-line passwords
2. **File Permissions**: Ensure keystore files have proper permissions (600)
3. **Network Security**: Use HTTPS for RPC endpoints in production
4. **Backup**: Regularly backup keystore files
5. **Validation**: Always verify transaction details before sending

## Performance Optimizations

### Database Connection Pooling (April 2026)
Recent performance improvements to database operations:

- **Connection Pooling**: Configured for PostgreSQL/MySQL (pool_size=10, max_overflow=20)
- **Connection Validation**: pool_pre_ping=True to verify connections before use
- **Connection Recycling**: pool_recycle=3600 to recycle connections after 1 hour
- **SQLite Optimization**: StaticPool for SQLite with timeout configuration

### Cache Management (April 2026)
Enhanced cache system with memory management:

- **Memory Limits**: Configured max_size=1000, max_memory_mb=100
- **Automatic Eviction**: Oldest entries evicted when size limit reached
- **Memory Monitoring**: Periodic memory limit checking and garbage collection
- **Performance Tracking**: Cache hit rate and statistics monitoring

### Performance Metrics
The system now tracks comprehensive performance metrics:

- **Cache Hit Rate**: Monitors cache effectiveness
- **Operation Timing**: Tracks execution time for all operations
- **Error Rates**: Monitors error frequency and types
- **Resource Usage**: Tracks memory and CPU usage patterns

### Optimization Recommendations

1. **Use Cache**: Leverage caching for frequently accessed data
2. **Connection Pooling**: Database connections are pooled for efficiency
3. **Batch Operations**: Use batch commands when possible
4. **Monitor Performance**: Use analytics command to check system performance

## Integration with Scripts

The CLI is designed for easy integration with shell scripts:

```bash
#!/bin/bash
# Get wallet balance in script
BALANCE=$(/opt/aitbc/aitbc-cli wallet balance my-wallet --format json | jq -r '.balance')

if [ "$BALANCE" -gt "1000" ]; then
  echo "Sufficient balance for transaction"
  /opt/aitbc/aitbc-cli wallet send my-wallet --to $RECIPIENT --amount 1000 --password-file /var/lib/aitbc/keystore/.password
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
/opt/aitbc/aitbc-cli --debug balance --name my-wallet
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
