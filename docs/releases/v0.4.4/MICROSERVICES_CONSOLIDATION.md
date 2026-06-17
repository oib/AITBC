# Microservices Consolidation - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 consolidates the GPU service microservice back into the monolithic architecture. This decision was made to reduce operational complexity, improve performance, and align GPU registration with blockchain-based transaction patterns.

## Changes

### GPU Service Removal

#### Deleted Components
- GPU service directory with all configuration files
- Systemd service definitions
- Database setup scripts
- Domain models: GPUArchitecture, GPURegistry, ConsumerGPUProfile, EdgeGPUMetrics, GPUBooking, GPUReview
- Service layer: EdgeGPUService
- API routers
- pyproject.toml dependency configuration

#### Migration to Blockchain-Based Registration

GPU registration now submits GPU_REGISTER blockchain transactions instead of using a separate microservice database.

### GPU Registration via Blockchain

#### Transaction Payload

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

#### Registration Process

1. **Transaction Submission**: GPU registration submits GPU_REGISTER blockchain transaction
2. **Detailed Payload**: Includes GPU specs and provider address
3. **Dual Storage**: Blockchain + local database for redundancy
4. **Hub Endpoint**: Uses HUB_BLOCKCHAIN_URL from environment
5. **Nonce Management**: Fetched from hub before transaction submission
6. **Transaction Hash**: Stored in local database for tracking

#### Environment Configuration

```bash
# blockchain.env
HUB_BLOCKCHAIN_URL=http://hub.aitbc.bubuit.net:8202
```

## Migration Guide

### Export Existing GPU Registrations

```bash
# Export existing GPU registrations from local database
aitbc gpu export > gpu_registrations.json
```

### Re-register via Blockchain

```bash
# Re-register via blockchain transactions
aitbc gpu register --from-file gpu_registrations.json
```

### Stop GPU Service

```bash
systemctl stop aitbc-gpu-service
systemctl disable aitbc-gpu-service
rm /etc/systemd/system/aitbc-gpu-service.service
```

### Restart Services

```bash
# Reload systemd
systemctl daemon-reload

# Restart affected services
systemctl restart aitbc-blockchain-node
```

## Breaking Changes

- GPU service microservice removed
- GPU service database and models removed
- Use blockchain GPU_REGISTER transactions instead

## Testing Results

- ✅ GPU registration via blockchain transactions
- ✅ GPU_REGISTER transaction payload validation
- ✅ Dual storage (blockchain + local database)
- ✅ GPU service removal verified

## Performance Improvements

- **Consolidated architecture**: Reduced microservices overhead
- **Blockchain-based**: Audit trail via blockchain transactions
- **Simplified operations**: One less service to manage

## Security Considerations

- GPU registration via blockchain provides audit trail
- Transaction hash stored in local database for tracking
- Hub endpoint authentication required

## Documentation

- Migration guide for existing GPU providers
- GPU registration API documentation updated

---

*Last Updated: 2026-06-03*
