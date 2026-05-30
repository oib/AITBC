# Wallet Setup

This guide covers creating and managing AITBC wallets.

## Create Wallet

```bash
# Generate new wallet
/opt/aitbc/venv/bin/aitbc wallet create my-wallet
```

## Get Wallet Address

```bash
# List wallets
/opt/aitbc/venv/bin/aitbc wallet list

# Show wallet details
/opt/aitbc/venv/bin/aitbc wallet show my-wallet
```

## Check Balance

```bash
# Check balance via RPC
curl -s http://localhost:8006/rpc/account/<your-address>
```

## Wallet Security

- Keep your wallet private keys secure
- Never share private keys
- Use strong passwords for wallet encryption
- Backup wallet files regularly
- Store backups in secure locations

## See Also

- [Coin Requests](coin-requests.md)
- [Blockchain Setup](blockchain-setup.md)
