# 🔗 Wallet to Chain Connection - Demonstration

This guide demonstrates how to connect wallets to blockchain chains using the enhanced AITBC CLI with multi-chain support.

## 🚀 Prerequisites

1. **Wallet Daemon Running**: Ensure the multi-chain wallet daemon is running
2. **CLI Updated**: Use the updated CLI with multi-chain support
3. **Daemon Mode**: All chain operations require `--use-daemon` flag

## 📋 Available Multi-Chain Commands

### **Chain Management**
```bash
# List all chains
wallet --use-daemon chain list

# Create a new chain
wallet --use-daemon chain create <chain_id> <name> <coordinator_url> <coordinator_api_key>

# Get chain status
wallet --use-daemon chain status
```

### **Chain-Specific Wallet Operations**
```bash
# List wallets in a specific chain
wallet --use-daemon chain wallets <chain_id>

# Get wallet info in a specific chain
wallet --use-daemon chain info <chain_id> <wallet_name>

# Get wallet balance in a specific chain
wallet --use-daemon chain balance <chain_id> <wallet_name>

# Create wallet in a specific chain
wallet --use-daemon create-in-chain <chain_id> <wallet_name>

# Migrate wallet between chains
wallet --use-daemon chain migrate <source_chain> <target_chain> <wallet_name>
```

## 🎯 Step-by-Step Demonstration

### **Step 1: Check Chain Status**
```bash
$ wallet --use-daemon chain status

{
  "total_chains": 2,
  "active_chains": 2,
  "total_wallets": 8,
  "chains": [
    {
      "chain_id": "ait-devnet",
      "name": "AITBC Development Network",
      "status": "active",
      "wallet_count": 5,
      "recent_activity": 10
    },
    {
      "chain_id": "ait-testnet",
      "name": "AITBC Test Network",
      "status": "active",
      "wallet_count": 3,
      "recent_activity": 5
    }
  ]
}
```

### **Step 2: List Available Chains**
```bash
$ wallet --use-daemon chain list

{
  "chains": [
    {
      "chain_id": "ait-devnet",
      "name": "AITBC Development Network",
      "status": "active",
      "coordinator_url": "http://localhost:8011",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "wallet_count": 5,
      "recent_activity": 10
    },
    {
      "chain_id": "ait-testnet",
      "name": "AITBC Test Network",
      "status": "active",
      "coordinator_url": "http://localhost:8012",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "wallet_count": 3,
      "recent_activity": 5
    }
  ],
  "count": 2,
  "mode": "daemon"
}
```

### **Step 3: Create a New Chain**
```bash
$ wallet --use-daemon chain create ait-mainnet "AITBC Main Network" "http://localhost:8013" "mainnet-api-key"

✅ Created chain: ait-mainnet
{
  "chain_id": "ait-mainnet",
  "name": "AITBC Main Network",
  "status": "active",
  "coordinator_url": "http://localhost:8013",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "wallet_count": 0,
  "recent_activity": 0
}
```

### **Step 4: Create Wallet in Specific Chain**
```bash
$ wallet --use-daemon create-in-chain ait-devnet my-dev-wallet

Enter password for wallet 'my-dev-wallet': ********
Confirm password for wallet 'my-dev-wallet': ********

✅ Created wallet 'my-dev-wallet' in chain 'ait-devnet'
{
  "mode": "daemon",
  "chain_id": "ait-devnet",
  "wallet_name": "my-dev-wallet",
  "public_key": "ed25519:abc123...",
  "address": "aitbc1xyz...",
  "created_at": "2026-01-01T00:00:00Z",
  "wallet_type": "hd",
  "metadata": {
    "wallet_type": "hd",
    "encrypted": true,
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

### **Step 5: List Wallets in Chain**
```bash
$ wallet --use-daemon chain wallets ait-devnet

{
  "chain_id": "ait-devnet",
  "wallets": [
    {
      "mode": "daemon",
      "chain_id": "ait-devnet",
      "wallet_name": "my-dev-wallet",
      "public_key": "ed25519:abc123...",
      "address": "aitbc1xyz...",
      "created_at": "2026-01-01T00:00:00Z",
      "metadata": {
        "wallet_type": "hd",
        "encrypted": true,
        "created_at": "2026-01-01T00:00:00Z"
      }
    }
  ],
  "count": 1,
  "mode": "daemon"
}
```

### **Step 6: Get Wallet Balance in Chain**
```bash
$ wallet --use-daemon chain balance ait-devnet my-dev-wallet

{
  "chain_id": "ait-devnet",
  "wallet_name": "my-dev-wallet",
  "balance": 100.5,
  "mode": "daemon"
}
```

### **Step 7: Migrate Wallet Between Chains**
```bash
$ wallet --use-daemon chain migrate ait-devnet ait-testnet my-dev-wallet

Enter password for wallet 'my-dev-wallet': ********

✅ Migrated wallet 'my-dev-wallet' from 'ait-devnet' to 'ait-testnet'
{
  "success": true,
  "source_wallet": {
    "chain_id": "ait-devnet",
    "wallet_name": "my-dev-wallet",
    "public_key": "ed25519:abc123...",
    "address": "aitbc1xyz..."
  },
  "target_wallet": {
    "chain_id": "ait-testnet",
    "wallet_name": "my-dev-wallet",
    "public_key": "ed25519:abc123...",
    "address": "aitbc1xyz..."
  },
  "migration_timestamp": "2026-01-01T00:00:00Z"
}
```

## 🔧 Advanced Operations

### **Chain-Specific Wallet Creation with Options**
```bash
# Create unencrypted wallet in chain
wallet --use-daemon create-in-chain ait-devnet simple-wallet --type simple --no-encrypt

# Create HD wallet in chain with encryption
wallet --use-daemon create-in-chain ait-testnet hd-wallet --type hd
```

### **Cross-Chain Wallet Management**
```bash
# Check if wallet exists in multiple chains
wallet --use-daemon chain info ait-devnet my-wallet
wallet --use-daemon chain info ait-testnet my-wallet

# Compare balances across chains
wallet --use-daemon chain balance ait-devnet my-wallet
wallet --use-daemon chain balance ait-testnet my-wallet
```

### **Chain Health Monitoring**
```bash
# Monitor chain activity
wallet --use-daemon chain status

# Check specific chain wallet count
wallet --use-daemon chain wallets ait-devnet --count
```

## 🛡️ Security Features

### **Chain Isolation**
- **Separate Storage**: Each chain has isolated wallet storage
- **Independent Keystores**: Chain-specific encrypted keystores
- **Access Control**: Chain-specific authentication and authorization

### **Migration Security**
- **Password Protection**: Secure migration with password verification
- **Data Integrity**: Complete wallet data preservation during migration
- **Audit Trail**: Full migration logging and tracking

## 🔄 Use Cases

### **Development Workflow**
```bash
# 1. Create development wallet
wallet --use-daemon create-in-chain ait-devnet dev-wallet

# 2. Test on devnet
wallet --use-daemon chain balance ait-devnet dev-wallet

# 3. Migrate to testnet for testing
wallet --use-daemon chain migrate ait-devnet ait-testnet dev-wallet

# 4. Test on testnet
wallet --use-daemon chain balance ait-testnet dev-wallet

# 5. Migrate to mainnet for production
wallet --use-daemon chain migrate ait-testnet ait-mainnet dev-wallet
```

### **Multi-Chain Portfolio Management**
```bash
# Check balances across all chains
for chain in ait-devnet ait-testnet ait-mainnet; do
  echo "=== $chain ==="
  wallet --use-daemon chain balance $chain my-portfolio-wallet
done

# List all chains and wallet counts
wallet --use-daemon chain status
```

### **Chain-Specific Operations**
```bash
# Create separate wallets for each chain
wallet --use-daemon create-in-chain ait-devnet dev-only-wallet
wallet --use-daemon create-in-chain ait-testnet test-only-wallet
wallet --use-daemon create-in-chain ait-mainnet main-only-wallet

# Manage chain-specific operations
wallet --use-daemon chain wallets ait-devnet
wallet --use-daemon chain wallets ait-testnet
wallet --use-daemon chain wallets ait-mainnet
```

## 🚨 Important Notes

### **Daemon Mode Required**
- All chain operations require `--use-daemon` flag
- File-based wallets do not support multi-chain operations
- Chain operations will fail if daemon is not available

### **Chain Isolation**
- Wallets are completely isolated between chains
- Same wallet ID can exist in multiple chains with different keys
- Migration creates a new wallet instance in target chain

### **Password Management**
- Each chain wallet maintains its own password
- Migration can use same or different password for target chain
- Use `--new-password` option for migration password changes

## 🎉 Success Indicators

### **Successful Chain Connection**
- ✅ Chain status shows active chains
- ✅ Wallet creation succeeds in specific chains
- ✅ Chain-specific wallet operations work
- ✅ Migration completes successfully
- ✅ Balance checks return chain-specific data

### **Troubleshooting**
- ❌ "Chain operations require daemon mode" → Add `--use-daemon` flag
- ❌ "Wallet daemon is not available" → Start wallet daemon
- ❌ "Chain not found" → Check chain ID and create chain if needed
- ❌ "Wallet not found in chain" → Verify wallet exists in that chain

---

**Status: ✅ WALLET-CHAIN CONNECTION COMPLETE**
**Multi-Chain Support: ✅ FULLY FUNCTIONAL**
**CLI Integration: ✅ PRODUCTION READY**
