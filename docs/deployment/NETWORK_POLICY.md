# Network Policy Documentation

**Last Updated:** 2026-06-19
**Version:** v0.5.1

## Overview

This document defines network binding requirements for AITBC services, specifying which services must bind to localhost (127.0.0.1) for security and which services can bind to all interfaces (0.0.0.0) for external access.

## Network Binding Requirements

### Services Binding to 127.0.0.1 (Localhost-Only)

These services are internal and must only bind to localhost for security:

| Service | Port | Purpose | Security Rationale |
|---------|------|---------|-------------------|
| coordinator-api | 8203 | Main REST API | Internal platform API, should be behind gateway |
| blockchain-rpc | 8202 | Blockchain RPC | Internal blockchain access, should be behind gateway |
| hermes | 8103 | AI orchestration | Internal AI decision making, should be behind gateway |
| ai-engine multimodal | 8020 | Multimodal AI processing | Internal AI processing, should be behind gateway |
| ai-engine modality-optimization | 8021 | Modality optimization | Internal AI optimization, should be behind gateway |
| ai-engine learning | 8012 | Adaptive learning | Internal AI learning, should be behind gateway |

### Services Binding to 0.0.0.0 (Exposed)

These services are designed for external access and bind to all interfaces:

| Service | Port | Purpose | Security Considerations |
|---------|------|---------|-------------------------|
| api-gateway | 8201 | External API gateway | Designed for external access, needs rate limiting |
| ai-engine ai | 8005 | AI inference endpoint | Designed for external AI inference access |

### Services with No Explicit Bind (Default Behavior)

These services use their application defaults and should be audited:

| Service | Port | Default Bind | Required Action | Status |
|---------|------|--------------|-----------------|--------|
| marketplace | 8104 | Unknown | Audit and enforce 127.0.0.1 | ✅ Hardened (v0.5.1) |
| exchange | 8106 | localhost (HTTPServer) | Audit and enforce 127.0.0.1 | ✅ Hardened (v0.5.1) |
| gpu | 8101 | 0.0.0.0 (app default) | Audit and enforce 127.0.0.1 | ✅ Hardened (v0.5.1) |
| edge | 8111 | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |
| governance | 8105 | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |
| trading | 8107 | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |
| wallet | 8108 | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |
| blockchain-node | 8202 | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |
| blockchain-p2p | Unknown | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |
| blockchain-sync | Unknown | Unknown | Audit and enforce 127.0.0.1 | ⏸️ Pending |

## Security Hardening: IPDeny=any

For all services binding to 127.0.0.1, add `IPDeny=any` to provide defense-in-depth:

```ini
[Service]
Type=simple
# ... other configuration ...
IPDeny=any
```

This directive prevents any network access from the service, even if the application is compromised or misconfigured.

## Implementation Steps

### 1. Add IPDeny=any to Localhost-Only Services ⏸️ DEFERRED (systemd compatibility)

**Status**: Deferred due to systemd compatibility issues
- IPDeny=any requires systemd version 242+ (not available in current environment)
- Attempted to add IPDeny=any caused service failures
- Services affected: coordinator-api, blockchain-rpc, hermes, multimodal, modality-optimization, learning
- Resolution: Upgrade systemd or use alternative network isolation methods

**Alternative approaches**:
- Use firewall rules (iptables/nftables) for network isolation
- Use network namespaces for service isolation
- Implement application-level network restrictions

### 2. Audit and Enforce Localhost Binding ✅ COMPLETED (v0.5.1)

For services with no explicit bind, added explicit localhost binding or environment variables:

**Completed:**
- ✅ `apps/marketplace/aitbc-marketplace.service` - Added MARKETPLACE_BIND_HOST=127.0.0.1 + MARKETPLACE_BIND_PORT=8104
- ✅ `apps/exchange/aitbc-exchange.service` - Already binds localhost via HTTPServer
- ✅ `apps/gpu/aitbc-gpu.service` - Added GPU_BIND_HOST=127.0.0.1

**Pending (deferred to v0.5.2):**
- ⏸️ `apps/edge/aitbc-edge.service`
- ⏸️ `apps/governance/aitbc-governance.service`
- ⏸️ `apps/trading/aitbc-trading.service`
- ⏸️ `apps/wallet/aitbc-wallet.service`
- ⏸️ `apps/blockchain-node/aitbc-blockchain-node.service`
- ⏸️ `apps/blockchain-node/aitbc-blockchain-p2p.service`
- ⏸️ `apps/blockchain-node/aitbc-blockchain-sync.service`

### 3. Audit Exposed Services ⏸️ PENDING

For services binding to 0.0.0.0, ensure proper security:
- ⏸️ `apps/api-gateway/aitbc-api-gateway.service` - Verify rate limiting and authentication
- ⏸️ `apps/ai-engine/aitbc-ai.service` - Verify authentication and authorization

## Verification

### Check Service Bindings

```bash
# Check which services are listening on which ports
sudo netstat -tlnp | grep LISTEN

# Check systemd service configuration
grep -r "host=" apps/*/*.service
grep -r "127.0.0.1\|0.0.0.0" apps/*/*.service
```

### Check IPDeny=any Enforcement

```bash
# Verify IPDeny=any is present in service files
grep -r "IPDeny=any" apps/*/*.service

# Verify service cannot make network connections
# (This requires the service to be running)
sudo -u aitbc-internal python -c "import socket; socket.socket().connect(('8.8.8.8', 53))"
```

### Test Service Accessibility

```bash
# Test localhost-only services (should fail from external)
curl http://localhost:8203/health  # Should work
curl http://192.168.1.1:8203/health  # Should fail

# Test exposed services (should work from external)
curl http://localhost:8201/health  # Should work
curl http://192.168.1.1:8201/health  # Should work
```

## Firewall Rules

In addition to systemd hardening, ensure firewall rules enforce the network policy:

```bash
# Allow only api-gateway external access on port 8201
sudo ufw allow 8201/tcp

# Allow ai-engine external access on port 8005
sudo ufw allow 8005/tcp

# Block all other AITBC ports from external
sudo ufw deny 8203/tcp  # coordinator-api
sudo ufw deny 8202/tcp  # blockchain-rpc
sudo ufw deny 8103/tcp  # hermes
# ... block other internal ports
```

## Monitoring

### Monitor for Policy Violations

Set up monitoring to detect:
- Services binding to 0.0.0.0 without explicit authorization
- Services making unexpected network connections
- External access attempts to localhost-only services

### Alerting

Configure alerts for:
- Service configuration changes (IPDeny=any removed)
- Network binding changes (127.0.0.1 → 0.0.0.0)
- Firewall rule changes

## Compliance

This network policy supports:
- **Principle of Least Privilege**: Services only have the network access they need
- **Defense in Depth**: Multiple layers of security (systemd + firewall)
- **Audit Trail**: All network access is logged and monitored
- **Zero Trust**: No service is trusted by default

## References

- [Systemd Security Hardening](../deployment/STAGING.md#systemd-hardening)
- [Service Users](../deployment/SERVICE_USERS.md)
- [Secret Management](../operations/SECRETS.md)
