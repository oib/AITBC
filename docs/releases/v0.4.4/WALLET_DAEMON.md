# Wallet Daemon Enhancements - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 enhances the wallet daemon with a new balance endpoint, automatic genesis wallet import, improved metadata merging, and updated systemd service configuration.

## New Features

### Balance Endpoint

#### API Endpoint

```bash
GET /v1/wallet/balance
```

#### Response

```json
{
  "address": "0x...",
  "balance": 1000.5,
  "chain_id": "ait-hub.aitbc.bubuit.net"
}
```

### Genesis Wallet Auto-Import

#### Import Process

1. Genesis wallet auto-imported from node.env on startup
2. GENESIS_PRIVATE_KEY and GENESIS_ADDRESS read from node.env
3. Hex private key converted to base64 for wallet import
4. Lifespan context manager triggers import during FastAPI startup
5. Check if genesis wallet already exists before importing

#### Environment Configuration

```bash
# node.env
GENESIS_PRIVATE_KEY=0x...
GENESIS_ADDRESS=0x...
```

### Metadata Merging Improvements

- Wallet metadata merging handles non-dict metadata types
- Ledger and keystore metadata merged correctly
- Address extraction from metadata fallbacks when primary field missing
- Secret key length validation updated to hardcoded 32 bytes

### Systemd Service Updates

- Updated to use /opt/aitbc installation paths
- Root user and virtual environment configuration
- PYTHONPATH includes /opt/aitbc
- Environment files (blockchain.env, node.env) loaded

### CLI Integration

- CLI balance command prioritizes wallet daemon queries
- Faster balance queries via cached wallet daemon

## Testing Results

- ✅ Balance endpoint returns correct balance
- ✅ Genesis wallet auto-import on startup
- ✅ Metadata merging with non-dict types
- ✅ CLI balance command uses wallet daemon

## Performance Improvements

- **Wallet balance query**: <50ms (vs 200ms direct RPC)
- **Cached queries**: Balance endpoint caches results
- **Faster startup**: Genesis wallet auto-import on daemon startup

## Security Considerations

- Genesis private key stored in node.env (file permissions restricted)
- Wallet metadata merging validates types
- Secret key length validation (32 bytes)

## Documentation

- [WALLET_DAEMON.md](../../../wallet/WALLET_DAEMON.md) — Balance endpoint documentation

---

*Last Updated: 2026-06-03*
