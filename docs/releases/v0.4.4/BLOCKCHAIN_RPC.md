# Blockchain RPC Updates - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 updates the Blockchain RPC with new endpoints for block height queries, network discovery, manual sync triggering, and GPU registration transactions.

## New Endpoints

### Block Height

```bash
GET /height
```

Returns the current block height.

### Network Discovery

```bash
GET /network-info
```

Network discovery for open island joining.

### Manual Sync

```bash
POST /force-sync
```

Manual sync triggering with JSON payload.

### Network Status

```bash
GET /rpc/network-info
```

Network status and peers.

### Peer List

```bash
GET /rpc/network/peers
```

Peer list.

## GPU_REGISTER Transaction

### Transaction Payload

```json
{
  "action": "GPU_REGISTER",
  "provider_address": "0x...",
  "gpu_model": "RTX 4090",
  "gpu_memory_gb": 24,
  "cuda_cores": 16384,
  "price_per_hour": 0.5,
  "region": "us-east-1"
}
```

### Registration Process

1. Submit GPU_REGISTER transaction to blockchain
2. Transaction includes GPU specs and provider address
3. Transaction hash stored in local database
4. Dual storage: blockchain + local database

## Network Discovery

### Features

- Protocol detection for hostname and protocol
- Contact email configuration
- Dynamic OpenAPI specification
- Islands and chains endpoints use environment-based configuration
- Static openapi.json removed in favor of dynamic endpoint

## Testing Results

- ✅ /height endpoint returns block height
- ✅ /network-info endpoint returns network info
- ✅ /force-sync triggers manual sync
- ✅ GPU_REGISTER transaction submission

## Performance Improvements

- **Improved endpoint organization**: Better structure for RPC endpoints
- **Dynamic OpenAPI**: Real-time API specification generation
- **Network discovery**: <100ms response time

## Documentation

- [BLOCKCHAIN_RPC.md](../../../blockchain/BLOCKCHAIN_RPC.md) — Updated RPC endpoints

---

*Last Updated: 2026-06-03*
