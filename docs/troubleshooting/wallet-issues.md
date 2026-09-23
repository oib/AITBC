# Wallet Daemon Issues

This guide covers wallet daemon problems including unresponsive wallet, transaction signing failures, and key management.

## Wallet Not Responding

**Symptoms:**

- Wallet daemon unresponsive
- Transactions not signing
- Balance not updating

**Diagnosis:**

```bash
# Check wallet daemon status
systemctl status aitbc-wallet

# Check wallet logs
journalctl -u aitbc-wallet -n 50

# Test wallet endpoint
curl http://localhost:8108/health
```

**Solutions:**

1. Check wallet file integrity

```bash
# Verify wallet file exists
ls -la /var/lib/aitbc/wallet/

# Check wallet file permissions
chmod 600 /var/lib/aitbc/wallet/wallet.dat
```

1. Restart wallet daemon

```bash
systemctl restart aitbc-wallet
```

1. Check key derivation

```bash
# Verify key derivation path
python -c "from aitbc_crypto import Wallet; w = Wallet(); print(w.address)"
```

## Transaction Signing Failed

**Symptoms:**

- Transactions fail to sign
- Invalid signature errors
- Key not found errors

**Diagnosis:**

```bash
# List wallets (the daemon exposes /v1/wallets*, not /v1/keys)
curl http://localhost:8108/v1/wallets

# Check transaction logs
journalctl -u aitbc-wallet -n 50 | grep -i transaction
```

**Solutions:**

1. Verify private key

```bash
# Check private key exists
ls -la /var/lib/aitbc/wallet/private_key

# There is no key-regeneration endpoint — a wallet's key cannot be
# regenerated in place. Create a new wallet instead (admin API key required):
curl -X POST http://localhost:8108/v1/wallets \
  -H "Content-Type: application/json" -H "X-API-Key: $ADMIN_API_KEY" \
  -d '{"chain_id": "ait-mainnet", "wallet_id": "replacement-wallet", "password": "..."}'
```

1. Check key permissions

```bash
# Secure private key
chmod 600 /var/lib/aitbc/wallet/private_key
chown aitbc:aitbc /var/lib/aitbc/wallet/private_key
```

## See Also

- [Security Issues](security-issues.md) - Authentication and key management issues
- [Service Management](service-management.md) - General service troubleshooting
- [Blockchain Issues](blockchain-issues.md) - Blockchain-related wallet issues
