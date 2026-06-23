# AITBC Service User Strategy

**Date**: June 7, 2026
**Status**: ✅ Recommended
**Purpose**: Streamlined service user strategy based on network exposure

## Overview

This document describes the recommended service user strategy for AITBC services, grouping services by network exposure rather than creating individual users for each service. This approach reduces user count while maintaining security benefits.

## User Strategy

### User Categories

**1. aitbc-public** - Public Exposure Services
- **Purpose**: Services that bind to 0.0.0.0 (publicly accessible)
- **Security Level**: High (requires rate limiting, authentication)
- **Services**: API Gateway, Edge, Whisper, etc.

**2. aitbc-internal** - Internal Services
- **Purpose**: Services that bind to 127.0.0.1 (localhost only)
- **Security Level**: Medium (internal network only)
- **Services**: Most microservices, AI services, etc.

**3. Specialized Users** - Specific Requirements
- **aitbc-gpu** - GPU service (needs video group)
- **aitbc-wallet** - Wallet service (keystore access)
- **aitbc-blockchain** - Blockchain services (P2P, RPC, node)
- **aitbc-coordinator** - Coordinator API (special config)

### User Distribution

| User | Service Count | Security Level | Binding |
|------|---------------|----------------|---------|
| **aitbc-public** | 4-6 | High | 0.0.0.0 |
| **aitbc-internal** | 15-18 | Medium | 127.0.0.1 |
| **aitbc-gpu** | 1 | Medium | 127.0.0.1 |
| **aitbc-wallet** | 1 | High | 0.0.0.0 |
| **aitbc-blockchain** | 3-4 | High | 0.0.0.0 |
| **aitbc-coordinator** | 1 | Medium | 127.0.0.1 |

**Total Users**: 6-7 (vs 8 individual users + 18 root services)

## Service Classification

### Public Exposure Services (0.0.0.0)

**High Security Risk - Use aitbc-public user:**
- `aitbc-api-gateway.service` - API Gateway (0.0.0.0:8201)
- `aitbc-edge.service` - Edge API (0.0.0.0:8111)
- `aitbc-whisper.service` - Whisper (0.0.0.0:8110)
- `aitbc-wallet.service` - Wallet (0.0.0.0:8108) - **Keep specialized user**
- `aitbc-blockchain-p2p.service` - P2P (0.0.0.0:8200)
- `aitbc-blockchain-event-bridge.service` - Event Bridge (0.0.0.0:8205)

**Security Requirements:**
- Rate limiting (already implemented)
- Authentication (JWT/API keys)
- TLS/SSL (nginx proxy)
- Regular security updates

### Internal Services (127.0.0.1)

**Medium Security Risk - Use aitbc-internal user:**
- `aitbc-gpu.service` - GPU service (127.0.0.1:8101) - **Keep specialized user**
- `aitbc-marketplace.service` - Marketplace (127.0.0.1:8102)
- `aitbc-agent.service` - Agent (127.0.0.1:8107)
- `aitbc-trading.service` - Trading (127.0.0.1:8104)
- `aitbc-governance.service` - Governance (127.0.0.1:8105)
- `aitbc-exchange.service` - Exchange (127.0.0.1:8106)
- `aitbc-agent-coordinator.service` - Agent Coordinator (127.0.0.1:8107)
- `aitbc-plugin.service` - Plugin (127.0.0.1:8109)
- `aitbc-coordinator-api.service` - Coordinator API (127.0.0.1:8203) - **Keep specialized user**
- `aitbc-blockchain-rpc.service` - Blockchain RPC (127.0.0.1:8202) - **Keep specialized user**

**AI Services (127.0.0.1):**
- `aitbc-ai.service` - AI service (0.0.0.0:8005) - **Public, use aitbc-public**
- `aitbc-learning.service` - Learning (127.0.0.1:8012)
- `aitbc-multimodal.service` - Multimodal (127.0.0.1:8020)
- `aitbc-modality-optimization.service` - Modality (127.0.0.1:8021)

**Agent Services:**
- `aitbc-agent-management.service` - Agent management
- Other agent services

**Other Services:**
- `aitbc-monitoring.service` - Monitoring
- `aitbc-ffmpeg.service` - FFmpeg
- `aitbc-miner.service` - Miner
- Other services

### Specialized Users

**aitbc-gpu** - GPU Service
- **Reason**: Needs access to video group for GPU operations
- **Current Status**: ✅ Configured and running
- **Binding**: 127.0.0.1:8101

**aitbc-wallet** - Wallet Service
- **Reason**: Needs access to keystore and wallet files
- **Current Status**: ✅ Configured and running
- **Binding**: 0.0.0.0:8108

**aitbc-blockchain** - Blockchain Services
- **Reason**: P2P networking, high security requirements
- **Services**: blockchain-node, blockchain-rpc, blockchain-p2p
- **Status**: User created, not yet configured

**aitbc-coordinator** - Coordinator API
- **Reason**: Special configuration, database access
- **Status**: User created, not yet configured

## Migration Plan

### Phase 1: Create New Users
- ✅ aitbc-public (public exposure services)
- ✅ aitbc-internal (internal services)

### Phase 2: Reconfigure Isolated Services
**Keep Current Configuration:**
- aitbc-gpu (specialized user)
- aitbc-marketplace (keep as aitbc-marketplace or migrate to aitbc-internal)
- aitbc-agent (keep as aitbc-agent or migrate to aitbc-internal)
- aitbc-agent-coordinator (keep as aitbc-agent or migrate to aitbc-internal)
- aitbc-wallet (specialized user)

**Migrate to aitbc-internal:**
- aitbc-marketplace.service → aitbc-internal
- aitbc-agent.service → aitbc-internal
- aitbc-agent-coordinator.service → aitbc-internal

### Phase 3: Configure Public Services
**Migrate to aitbc-public:**
- aitbc-api-gateway.service → aitbc-public
- aitbc-edge.service → aitbc-public
- aitbc-whisper.service → aitbc-public
- aitbc-blockchain-p2p.service → aitbc-public
- aitbc-blockchain-event-bridge.service → aitbc-public

### Phase 4: Configure Blockchain Services
**Migrate to aitbc-blockchain:**
- aitbc-blockchain-node.service → aitbc-blockchain
- aitbc-blockchain-rpc.service → aitbc-blockchain
- aitbc-blockchain-p2p.service → aitbc-blockchain

### Phase 5: Configure Remaining Services
**Migrate to aitbc-internal:**
- All remaining internal services

## Security Benefits

### Reduced User Count
- **Before**: 8 individual users + 18 root services = 26 users
- **After**: 6-7 users for 26 services
- **Reduction**: ~75% reduction in user count

### Security Segmentation
- **Public services**: Isolated in aitbc-public user
- **Internal services**: Isolated in aitbc-internal user
- **Specialized services**: Dedicated users for specific needs
- **Compromise containment**: Limited to exposure category

### Management Simplicity
- **Easier permission management**: 3 main categories
- **Simplified auditing**: Clear security boundaries
- **Easier troubleshooting**: Clear user-service mapping
- **Reduced complexity**: Fewer users to manage

## Implementation Steps

### Example: Migrating a Service to aitbc-internal

```bash
# 1. Update service file
sed -i 's/User=aitbc-marketplace/User=aitbc-internal/' /etc/systemd/system/aitbc-marketplace.service
sed -i 's/Group=aitbc-services/Group=aitbc-services/' /etc/systemd/system/aitbc-marketplace.service

# 2. Update file ownership
chown -R aitbc-internal:aitbc-services /opt/aitbc/apps/marketplace

# 3. Reload and restart
systemctl daemon-reload
systemctl restart aitbc-marketplace.service

# 4. Verify
ps aux | grep marketplace_service
```

### Example: Migrating a Service to aitbc-public

```bash
# 1. Update service file
sed -i 's/User=root/User=aitbc-public/' /etc/systemd/system/aitbc-api-gateway.service
sed -i 's/Group=root/Group=aitbc-services/' /etc/systemd/system/aitbc-api-gateway.service

# 2. Update file ownership
chown -R aitbc-public:aitbc-services /opt/aitbc/apps/api-gateway

# 3. Reload and restart
systemctl daemon-reload
systemctl restart aitbc-api-gateway.service

# 4. Verify
ps aux | grep api_gateway
```

## Current Status

### Currently Isolated Services (5)
- aitbc-gpu.service → aitbc-gpu ✅
- aitbc-marketplace.service → aitbc-marketplace ✅
- aitbc-agent.service → aitbc-agent ✅
- aitbc-agent-coordinator.service → aitbc-agent ✅
- aitbc-wallet.service → aitbc-wallet ✅

### Recommended Changes

**Consolidate Internal Services:**
- aitbc-marketplace → aitbc-internal
- aitbc-agent → aitbc-internal
- aitbc-agent-coordinator → aitbc-internal

**Add Public Services:**
- aitbc-api-gateway → aitbc-public
- aitbc-edge → aitbc-public
- aitbc-whisper → aitbc-public

**Add Blockchain Services:**
- aitbc-blockchain-node → aitbc-blockchain
- aitbc-blockchain-rpc → aitbc-blockchain
- aitbc-blockchain-p2p → aitbc-blockchain

## Next Steps

**Option 1: Implement the recommended strategy**
- Consolidate internal services to aitbc-internal
- Migrate public services to aitbc-public
- Configure blockchain services to aitbc-blockchain
- Keep specialized users for specific needs

**Option 2: Keep current configuration**
- Maintain individual users for isolated services
- Only add new services using the new strategy
- Gradually migrate existing services

**Option 3: Hybrid approach**
- Keep currently working isolated services as-is
- Apply new strategy only to new services and migrations
- Gradually consolidate similar services

---

**Last Updated**: June 7, 2026
**Strategy Version**: 1.0
