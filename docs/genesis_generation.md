# Genesis Block and Wallet Generation Guide

This guide explains how to use the unified genesis generation system for AITBC blockchain initialization.

## Overview

The unified genesis generation system combines:
- **Genesis Block Creation**: Creates the initial block for a blockchain
- **Genesis Wallet Creation**: Generates a secure genesis wallet with known private key
- **Wallet Service Integration**: Registers the genesis wallet with the wallet daemon service
- **Database Initialization**: Sets up the blockchain database with genesis data

## Prerequisites

- Python 3.13+
- AITBC blockchain node installed
- Wallet daemon service running (optional, for service integration)
- Database directory: `/var/lib/aitbc/data/`
- Keystore directory: `/var/lib/aitbc/keystore/`

## Installation

The unified genesis script is located at:
```
/opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py
```

Make it executable:
```bash
chmod +x /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py
```

## Usage

### Basic Usage

Create genesis block and wallet for mainnet:
```bash
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet
```

### Advanced Options

```bash
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet \
    --password "your_secure_password" \
    --proposer "custom_proposer_address" \
    --db-path /var/lib/aitbc/data/chain.db \
    --keystore-path /var/lib/aitbc/keystore/genesis.json \
    --genesis-path /var/lib/aitbc/data/ait-mainnet/genesis.json \
    --force \
    --register-service \
    --service-url http://localhost:8003
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--chain-id` | Chain ID for genesis | `ait-mainnet` |
| `--proposer` | Proposer address (defaults to genesis wallet) | `genesis` |
| `--create-wallet` | Create genesis wallet with secure random key | `False` |
| `--password` | Wallet password (auto-generated if not provided) | auto-generated |
| `--db-path` | Database file path | `/var/lib/aitbc/data/chain.db` |
| `--keystore-path` | Keystore file path | `/var/lib/aitbc/keystore/genesis.json` |
| `--genesis-path` | Genesis config file path | `/var/lib/aitbc/data/ait-mainnet/genesis.json` |
| `--force` | Force overwrite existing genesis | `False` |
| `--register-service` | Register genesis wallet with wallet service | `False` |
| `--service-url` | Wallet service URL | `http://localhost:8003` |

## Workflow

### Step 1: Create Genesis Wallet and Block

```bash
# Stop blockchain node if running
systemctl stop aitbc-blockchain-node.service

# Generate genesis
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet \
    --force

# Start blockchain node
systemctl start aitbc-blockchain-node.service
```

### Step 2: Verify Genesis

```bash
# Check genesis block
curl http://localhost:8006/rpc/block/0

# Check genesis wallet balance
/opt/aitbc/aitbc-cli wallet balance genesis --chain-id ait-mainnet
```

### Step 3: Register with Wallet Service (Optional)

```bash
# Ensure wallet daemon is running
systemctl status aitbc-wallet-daemon.service

# Register genesis wallet
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --register-service \
    --service-url http://localhost:8003
```

## Security Considerations

### Private Key Security

- The script generates a cryptographically secure random private key
- Private key is encrypted with AES-256-GCM
- Password is derived using PBKDF2 with 100,000 iterations
- Password is saved to `/var/lib/aitbc/keystore/.genesis_password` with 0600 permissions

### Important Security Notes

1. **Store the password securely**: The password is saved to `.genesis_password` but should be backed up to a secure location
2. **Never share the private key**: The private key should only be known by authorized personnel
3. **Use strong passwords**: If providing a custom password, use a strong, unique password
4. **Backup the keystore**: The genesis wallet file should be backed up securely
5. **Rotate keys periodically**: For production, consider key rotation policies

## Multi-Chain Support

The script supports multiple chains:

```bash
# Mainnet
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet

# Devnet
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-devnet \
    --create-wallet \
    --db-path /var/lib/aitbc/data/ait-devnet/chain.db \
    --genesis-path /var/lib/aitbc/data/ait-devnet/genesis.json

# Testnet
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-testnet \
    --create-wallet \
    --db-path /var/lib/aitbc/data/ait-testnet/chain.db \
    --genesis-path /var/lib/aitbc/data/ait-testnet/genesis.json
```

## Troubleshooting

### Database Locked Error

If you get a database locked error:
```bash
# Stop the blockchain node
systemctl stop aitbc-blockchain-node.service

# Run genesis generation
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet

# Start the blockchain node
systemctl start aitbc-blockchain-node.service
```

### Genesis Already Exists

If genesis already exists in the database:
```bash
# Use --force to overwrite
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet \
    --force
```

### Wallet Service Connection Failed

If wallet service registration fails:
```bash
# Check if wallet daemon is running
systemctl status aitbc-wallet-daemon.service

# Start wallet daemon if not running
systemctl start aitbc-wallet-daemon.service

# Verify service URL
curl http://localhost:8003/health
```

## Integration with Wallet Service

The unified genesis script can register the genesis wallet with the wallet daemon service for enhanced wallet management capabilities:

### Benefits of Wallet Service Integration

- Centralized wallet management
- Automatic wallet synchronization
- Enhanced security features
- Transaction signing delegation
- Multi-wallet support

### Registration Process

```bash
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet \
    --register-service \
    --service-url http://localhost:8003
```

The script will:
1. Create the genesis wallet
2. Register it with the wallet service
3. Store the wallet credentials securely
4. Enable wallet service operations

## Examples

### Example 1: Fresh Mainnet Setup

```bash
# Complete fresh setup for mainnet
systemctl stop aitbc-blockchain-node.service
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --create-wallet \
    --force
systemctl start aitbc-blockchain-node.service
/opt/aitbc/aitbc-cli wallet balance genesis --chain-id ait-mainnet
```

### Example 2: Devnet with Custom Password

```bash
# Devnet setup with custom password
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-devnet \
    --create-wallet \
    --password "my_secure_devnet_password" \
    --db-path /var/lib/aitbc/data/ait-devnet/chain.db \
    --genesis-path /var/lib/aitbc/data/ait-devnet/genesis.json
```

### Example 3: Register Existing Genesis with Service

```bash
# Register existing genesis wallet with service
python3 /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-mainnet \
    --register-service \
    --service-url http://localhost:8003
```

## Output Files

After running the script, the following files are created:

1. **Genesis Wallet**: `/var/lib/aitbc/keystore/genesis.json`
   - Encrypted wallet file with genesis credentials
   - Contains address, public key, encrypted private key

2. **Password File**: `/var/lib/aitbc/keystore/.genesis_password`
   - Plain text password file (0600 permissions)
   - Should be backed up securely

3. **Genesis Config**: `/var/lib/aitbc/data/{chain_id}/genesis.json`
   - Genesis block configuration
   - Account allocations
   - Chain metadata

4. **Database**: `/var/lib/aitbc/data/chain.db`
   - Blockchain database with genesis block
   - Genesis accounts
   - Chain state

## Verification

After genesis generation, verify the setup:

```bash
# Check genesis block in database
sqlite3 /var/lib/aitbc/data/chain.db "SELECT * FROM block WHERE height=0;"

# Check genesis accounts
sqlite3 /var/lib/aitbc/data/chain.db "SELECT address, balance FROM account WHERE chain_id='ait-mainnet';"

# Check wallet balance via CLI
/opt/aitbc/aitbc-cli wallet balance genesis --chain-id ait-mainnet

# Check blockchain node status
curl http://localhost:8006/health
```

## Best Practices

1. **Always backup** the genesis wallet and password before running
2. **Use --force** only when necessary, as it overwrites existing genesis
3. **Test on devnet** before applying to mainnet
4. **Document** the genesis password in a secure location
5. **Monitor** the blockchain node after genesis initialization
6. **Verify** all services are running after genesis setup
7. **Keep** the genesis script updated with the latest blockchain changes

## Support

For issues or questions:
- Check the blockchain node logs: `journalctl -u aitbc-blockchain-node.service -f`
- Check the wallet daemon logs: `journalctl -u aitbc-wallet-daemon.service -f`
- Review the script output for error messages
- Consult the AITBC documentation for additional guidance
