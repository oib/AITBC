# Wallet Funding Guide

This guide explains how to fund wallets for AITBC training and testing.

## Genesis Wallet

The genesis wallet is pre-funded with 997,999,290 AIT and serves as the primary funding source for training wallets.

**Genesis Wallet Details:**
- Name: `genesis`
- Address: `ait175406af70445617b0cd7eb8ff384d81b15c26b45`
- Balance: 997,999,290 AIT
- Password file: `/var/lib/aitbc/keystore/.genesis_password`

## Quick Funding Script

Use the provided script to fund wallets from genesis:

```bash
./scripts/training/fund_wallet.sh <wallet_name> [amount]
```

**Examples:**
```bash
# Fund hermes-trainee with default amount (1000 AIT)
./scripts/training/fund_wallet.sh hermes-trainee

# Fund a specific wallet with custom amount
./scripts/training/fund_wallet.sh training-wallet 5000
```

## Manual Funding

To manually fund a wallet using the AITBC CLI:

```bash
# Read genesis password
GENESIS_PASSWORD=$(cat /var/lib/aitbc/keystore/.genesis_password)

# Send funds from genesis to target wallet
./aitbc-cli wallet send genesis <target_wallet> <amount> "$GENESIS_PASSWORD"
```

**Example:**
```bash
./aitbc-cli wallet send genesis hermes-trainee 100 "EzE4d8cLJo20E9FlquSXq7hqy-e6p4M7Q1ZkM5eLpmY"
```

## Checking Wallet Balances

```bash
# Check specific wallet balance
./aitbc-cli wallet balance <wallet_name>

# List all wallets
./aitbc-cli wallet list
```

## Faucet Service

The AITBC system includes a faucet service for automated wallet funding.

### Faucet Setup (Deprecated)

The bash-based faucet setup script is deprecated. Use the Python-based setup system instead:

```bash
python3 -m aitbc.training_setup.cli setup
```

This will:
1. Check prerequisites
2. Setup genesis wallet as funding source
3. Fund training wallets
4. Configure messaging authentication

### Faucet API

If the faucet service is running, you can fund wallets via HTTP API:

```bash
curl -X POST http://localhost:8080/fund \
  -H "Content-Type: application/json" \
  -d '{"address": "ait1..."}'
```

**Default faucet configuration:**
- Port: 8080
- Funding amount: 1000 AIT per request
- Rate limit: 10 requests per hour per IP

## Common Training Wallets

**Default training wallets:**
- `hermes-trainee` - Primary training wallet
- `training-wallet` - General training operations
- `exam-wallet` - Exam and testing
- `faucet` - Faucet service wallet (if configured)

**Test wallets:**
- `test-agent` - Agent testing
- `scenario_user` - Scenario testing
- `openclaw-trainee` - OpenClaw training

## Troubleshooting

### Genesis Password Not Found

If the genesis password file is missing or empty:

```bash
# Check if file exists
ls -la /var/lib/aitbc/keystore/.genesis_password

# If missing, the genesis wallet may need to be reconfigured
# Contact your system administrator
```

### Insufficient Genesis Balance

If the genesis wallet has insufficient funds:

```bash
# Check genesis balance
./aitbc-cli wallet balance genesis

# If balance is low, you may need to mine new blocks
# or regenerate the genesis block
```

### Transaction Failed

If funding transactions fail:

1. Verify the target wallet exists
2. Check blockchain node status
3. Ensure services are running:
   ```bash
   systemctl status aitbc-blockchain-node.service
   ```

## Security Notes

- The genesis password is stored in `/var/lib/aitbc/keystore/.genesis_password` with 0600 permissions
- Never share the genesis password
- Backup the genesis wallet file and password
- For production, consider using a separate faucet wallet instead of genesis

## Related Documentation

- [Training Environment Setup](ENVIRONMENT_SETUP.md)
- [Genesis Generation](/opt/aitbc/docs/infrastructure/genesis_generation.md)
- [Training Playground](/opt/aitbc/scripts/training/README.md)
