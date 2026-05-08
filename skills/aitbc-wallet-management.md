# AITBC Wallet Management Skill

## Trigger Conditions
Activate when user requests wallet operations: creation, listing, balance checking, wallet information retrieval, import, export, or deletion.

## Purpose
Create, list, import, export, and manage AITBC blockchain wallets with deterministic validation.

## Prerequisites
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Python venv activated for CLI operations
- Keystore directory at `/var/lib/aitbc/keystore/`
- SSH access to follower node (aitbc1) for cross-node operations
- Default wallet password: from `/var/lib/aitbc/keystore/.genesis_password`

## Operations

### Create Wallet
```bash
./aitbc-cli create --name <wallet_name> --password <password>
```

### Import Wallet
```bash
./aitbc-cli import --name <wallet_name> --private-key <hex_key> --password <password>
```

### Export Wallet
```bash
./aitbc-cli export --name <wallet_name> --password <password>
```

### List Wallets
```bash
./aitbc-cli list

# With JSON format
./aitbc-cli list --format json
```

### Check Wallet Balance
```bash
./aitbc-cli balance --name <wallet_name>
```

### Delete Wallet
```bash
./aitbc-cli delete --name <wallet_name>
```

### Rename Wallet
```bash
./aitbc-cli rename --old <old_name> --new <new_name>
```

### Get Transaction History
```bash
./aitbc-cli transactions --name <wallet_name> --limit <limit> --format [table|json]
```

## Common Pitfalls

1. **Wallet Not Found:** Check wallet name spelling, verify keystore directory at `/var/lib/aitbc/keystore/`
2. **Invalid Password:** Verify password, check password file at `/var/lib/aitbc/keystore/.genesis_password`
3. **Invalid Private Key:** Ensure private key is valid hex string (64 hex characters for Ed25519)
4. **Wallet Already Exists:** Choose a different wallet name or delete existing wallet first
5. **Insufficient Balance:** Check wallet balance before sending transactions
6. **Keystore Encryption:** CLI supports AES-256-GCM and Fernet encryption
7. **Cross-Node Issues:** Verify SSH connectivity for operations on remote nodes

## Verification Checklist
- [ ] Wallet created successfully and appears in list
- [ ] Wallet balance retrieved correctly
- [ ] Private key export works with correct password
- [ ] Import from private key creates valid wallet
- [ ] Wallet deletion removes wallet from list
- [ ] Transaction history shows past transactions

## Wallet Naming Conventions
- Use alphanumeric characters, hyphens, and underscores only
- Avoid special characters and spaces
- Use descriptive names (e.g., "genesis", "hermes-trainee", "trading-wallet")
- Max length: 64 characters

## Security Considerations
- Never share private keys
- Store passwords securely (use password file when possible)
- Backup keystore directory regularly
- Use strong passwords (minimum 12 characters)
- Enable encryption for sensitive wallets

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **Keystore Location:** `/var/lib/aitbc/keystore/`
- **Password File:** `/var/lib/aitbc/keystore/.genesis_password`
