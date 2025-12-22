---
title: Wallet Management
description: Managing your AITBC wallet
---

# Wallet Management

Your AITBC wallet allows you to store, send, and receive AITBC tokens and interact with the platform.

## Creating a Wallet

### New Wallet
```bash
aitbc wallet create
```

### Import Existing
```bash
aitbc wallet import <private_key>
```

## Wallet Operations

### Check Balance
```bash
aitbc wallet balance
```

### Send Tokens
```bash
aitbc wallet send <address> <amount>
```

### Transaction History
```bash
aitbc wallet history
```

## Security

- Never share your private key
- Use a hardware wallet for large amounts
- Enable two-factor authentication
- Keep backups in secure locations

## Staking

Earn rewards by staking your tokens:
```bash
aitbc wallet stake <amount>
```

## Backup

Always backup your wallet:
```bash
aitbc wallet backup --output wallet.backup
```

## Recovery

Restore from backup:
```bash
aitbc wallet restore --input wallet.backup
```
