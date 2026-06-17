# Environment Configuration - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 introduces improved environment configuration with separate blockchain.env and node.env files, environment variable loading before module imports, and support for genesis wallet configuration.

## Configuration Files

### blockchain.env

Blockchain-specific settings for node configuration.

```bash
# Blockchain-specific settings
BLOCKCHAIN_MODE=follower
MARKET_ROLE=customer
HARDWARE_PROFILE=nogpu
HUB_BLOCKCHAIN_URL=http://hub.aitbc.bubuit.net:8202
```

### node.env

Node-specific settings for local configuration.

```bash
# Node-specific settings
GENESIS_PRIVATE_KEY=0x...
GENESIS_ADDRESS=0x...
HERMES_DB_PATH=/var/lib/aitbc/hermes_coin_requests.db
```

## Environment Loading Order

1. Load node.env before setting environment variables
2. Load blockchain.env for blockchain-specific settings
3. Environment variables available before module imports
4. Dynamic configuration based on environment

## Supported Environment Variables

### Blockchain Configuration
- `BLOCKCHAIN_MODE`: follower or leader
- `MARKET_ROLE`: customer or provider
- `HARDWARE_PROFILE`: nogpu or gpu
- `HUB_BLOCKCHAIN_URL`: Hub blockchain RPC endpoint

### Node Configuration
- `GENESIS_PRIVATE_KEY`: Genesis wallet private key (hex)
- `GENESIS_ADDRESS`: Genesis wallet address
- `HERMES_DB_PATH`: Path to Hermes database

## Benefits

- **Separation of concerns**: Blockchain vs node-specific settings
- **Pre-loading**: Environment variables available before imports
- **Flexibility**: Easy configuration for different deployment scenarios
- **Security**: Genesis private key in separate file with restricted permissions

## Testing Results

- ✅ blockchain.env loaded correctly
- ✅ node.env loaded correctly
- ✅ Environment variables available before imports
- ✅ Genesis wallet imported from node.env

## Security Considerations

- Genesis private key stored in node.env (file permissions restricted)
- Environment variable loading before imports prevents race conditions
- File permissions should be restricted (600 or 640)

## Documentation

- [SETUP.md](../../../getting-started/SETUP.md) — Environment configuration documentation

---

*Last Updated: 2026-06-03*
