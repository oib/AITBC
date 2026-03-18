# Production Blockchain Setup Guide

## Overview

This guide sets up the AITBC blockchain in production mode with:
- Proper cryptographic key management (encrypted keystore)
- Fixed supply with predefined allocations (no admin minting)
- Secure configuration (localhost-only RPC, removed admin endpoints)
- Multi-chain support (devnet preserved)

## Steps

### 1. Generate Keystore for `aitbc1genesis`

Run as `aitbc` user:

```bash
sudo -u aitbc /opt/aitbc/apps/blockchain-node/.venv/bin/python /opt/aitbc/scripts/keystore.py aitbc1genesis --output-dir /opt/aitbc/keystore
```

- Enter a strong encryption password (store in password manager).
- **COPY** the printed private key (hex). Save it securely; you'll need it for `.env`.
- File: `/opt/aitbc/keystore/aitbc1genesis.json` (600)

### 2. Generate Keystore for `aitbc1treasury`

```bash
sudo -u aitbc /opt/aitbc/apps/blockchain-node/.venv/bin/python /opt/aitbc/scripts/keystore.py aitbc1treasury --output-dir /opt/aitbc/keystore
```

- Choose another strong password.
- **COPY** the printed private key.
- File: `/opt/aitbc/keystore/aitbc1treasury.json` (600)

### 3. Initialize Production Database

```bash
# Create data directory
sudo mkdir -p /opt/aitbc/data/ait-mainnet
sudo chown -R aitbc:aitbc /opt/aitbc/data/ait-mainnet

# Run init script
export DB_PATH=/opt/aitbc/data/ait-mainnet/chain.db
export CHAIN_ID=ait-mainnet
sudo -E -u aitbc /opt/aitbc/apps/blockchain-node/.venv/bin/python /opt/aitbc/scripts/init_production_genesis.py --chain-id ait-mainnet --db-path "$DB_PATH"
```

Verify:

```bash
sqlite3 /opt/aitbc/data/ait-mainnet/chain.db "SELECT address, balance FROM account ORDER BY balance DESC;"
```

Expected: 13 rows with balances from `ALLOCATIONS`.

### 4. Configure `.env` for Production

Edit `/opt/aitbc/apps/blockchain-node/.env`:

```ini
CHAIN_ID=ait-mainnet
SUPPORTED_CHAINS=ait-mainnet
DB_PATH=./data/ait-mainnet/chain.db
PROPOSER_ID=aitbc1genesis
PROPOSER_KEY=0x<PRIVATE_KEY_HEX_FROM_STEP_1>
PROPOSER_INTERVAL_SECONDS=5
BLOCK_TIME_SECONDS=2

RPC_BIND_HOST=127.0.0.1
RPC_BIND_PORT=8006
P2P_BIND_HOST=127.0.0.2
P2P_BIND_PORT=8005

MEMPOOL_BACKEND=database
MIN_FEE=0
GOSSIP_BACKEND=memory
```

Replace `<PRIVATE_KEY_HEX_FROM_STEP_1>` with the actual hex string (include `0x` prefix if present).

### 5. Restart Services

```bash
sudo systemctl daemon-reload
sudo systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
```

Check status:

```bash
sudo systemctl status aitbc-blockchain-node
sudo journalctl -u aitbc-blockchain-node -f
```

### 6. Verify RPC

Query the head:

```bash
curl "http://127.0.0.1:8006/head?chain_id=ait-mainnet" | jq
```

Expected output:

```json
{
  "height": 0,
  "hash": "0x...",
  "timestamp": "2025-01-01T00:00:00",
  "tx_count": 0
}
```

## Optional: Add Balance Query Endpoint

If you need to check account balances via RPC, I can add a simple endpoint `/account/{address}`. Request it if needed.

## Clean Up Devnet (Optional)

To free resources, you can archive the old devnet DB:

```bash
sudo mv /opt/aitbc/apps/blockchain-node/data/devnet /opt/aitbc/apps/blockchain-node/data/devnet.bak
```

## Notes

- Admin minting (`/admin/mintFaucet`) has been removed.
- RPC is bound to localhost only; external access should go through a reverse proxy with TLS and API key.
- The `aitbc1treasury` account exists but cannot spend until wallet daemon integration is complete.
- All other service accounts are watch-only. Generate additional keystores if they need to sign.
- Back up the keystore files and encryption passwords immediately.

## Troubleshooting

- **Proposer not starting**: Check `PROPOSER_KEY` format (hex, with 0x prefix sometimes required). Ensure DB is initialized.
- **DB initialization error**: Verify `DB_PATH` points to a writable location and that the directory exists.
- **RPC unreachable**: Confirm RPC bound to 127.0.0.1:8006 and firewall allows local access.
