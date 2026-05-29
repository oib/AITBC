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
sudo systemctl status aitbc-wallet

# Check wallet logs
sudo journalctl -u aitbc-wallet -n 50

# Test wallet endpoint
curl http://localhost:8071/health
```

**Solutions:**
1. Check wallet file integrity
```bash
# Verify wallet file exists
ls -la /var/lib/aitbc/wallet/

# Check wallet file permissions
chmod 600 /var/lib/aitbc/wallet/wallet.dat
```

2. Restart wallet daemon
```bash
sudo systemctl restart aitbc-wallet
```

3. Check key derivation
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
# Check wallet keys
curl http://localhost:8071/v1/keys

# Check transaction logs
sudo journalctl -u aitbc-wallet -n 50 | grep -i transaction
```

**Solutions:**
1. Verify private key
```bash
# Check private key exists
ls -la /var/lib/aitbc/wallet/private_key

# Regenerate keys if needed
curl -X POST http://localhost:8071/v1/keys/regenerate
```

2. Check key permissions
```bash
# Secure private key
chmod 600 /var/lib/aitbc/wallet/private_key
chown aitbc:aitbc /var/lib/aitbc/wallet/private_key
```

## See Also

- [Security Issues](security-issues.md) - Authentication and key management issues
- [Service Management](service-management.md) - General service troubleshooting
- [Blockchain Issues](blockchain-issues.md) - Blockchain-related wallet issues
