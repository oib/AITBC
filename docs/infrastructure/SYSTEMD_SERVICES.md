# SystemD Services Management Guide

**Last Updated**: 2026-03-29  
**Version**: 3.4 (Debian Root Usage)  
**Environment**: Debian Linux with root user (no sudo required)

## Overview

This guide covers SystemD service management for AITBC following the infrastructure optimization that fixed 34+ services.

## 🚀 Service Status After Optimization

### ✅ Fixed Services (34+ services updated)
- **Python Interpreter**: Changed from non-existent venvs to `/usr/bin/python3`
- **Working Directories**: Updated to correct paths
- **Environment Files**: Created missing `.env` files
- **PYTHONPATH**: Fixed module import paths

### 📁 Service Categories

#### Core Services
- `aitbc-coordinator-api.service` - Central API (Port 8000)
- `aitbc-blockchain-node.service` - Blockchain node (Port 8005)
- `aitbc-exchange-api.service` - Exchange API (Port 8001)
- `aitbc-wallet.service` - Wallet service (Port 8003)
- `aitbc-adaptive-learning.service` - Adaptive Learning (Port 8010)

#### Agent Services
- `aitbc-agent-registry.service` - Agent discovery
- `aitbc-agent-coordinator.service` - Task coordination
- `aitbc-ai-service.service` - AI services

#### Blockchain Services
- `aitbc-blockchain-node.service` - Blockchain Node with P2P (Port 8005)
- `aitbc-blockchain-rpc.service` - RPC API (Port 8006)

#### Supporting Services
- `aitbc-explorer.service` - Blockchain explorer
- `aitbc-gpu-miner.service` - GPU mining
- `aitbc-marketplace.service` - Marketplace
- `aitbc-multimodal.service` - Multimodal processing

## 🧭 Current Port Mapping

### Active Services (as of 2026-03-29)
```bash
⚠️ Port 8000 - Coordinator API (aitbc-coordinator-api.service) - **LEGACY - DISABLED**
✅ Port 8001 - Exchange API (aitbc-exchange-api.service)  
✅ Port 8003 - Wallet Service (aitbc-wallet.service)
✅ Port 8006 - Blockchain RPC (aitbc-blockchain-rpc.service)
✅ Port 8010 - Adaptive Learning (aitbc-adaptive-learning.service)
✅ Port 8005 - Blockchain Node with P2P (aitbc-blockchain-node.service)
```

### Service Dependencies
```bash
Coordinator API → Wallet Service → Exchange API
Blockchain RPC ← Blockchain Node (with P2P)
Adaptive Learning → Coordinator API
```

## 🛠️ Service Management Commands

### Basic Operations
```bash
# List all AITBC services
systemctl list-units --all | grep aitbc

# Check service status
systemctl status aitbc-coordinator-api.service

# Start a service
systemctl start aitbc-coordinator-api.service

# Stop a service
systemctl stop aitbc-coordinator-api.service

# Restart a service
systemctl restart aitbc-coordinator-api.service

# Enable auto-start
systemctl enable aitbc-coordinator-api.service

# Disable auto-start
systemctl disable aitbc-coordinator-api.service
```

### Bulk Operations
```bash
# Start all core services
systemctl start aitbc-coordinator-api aitbc-blockchain-node aitbc-exchange-api aitbc-wallet

# Restart all agent services
systemctl restart aitbc-agent-* aitbc-ai-service

# Check all services status
systemctl status aitbc-*
```

## 📊 Service Monitoring

### Health Checks
```bash
# Real-time monitoring
watch -n 5 'systemctl status aitbc-* --no-pager'

# Service failures
journalctl -u aitbc-coordinator-api.service --since "1 hour ago" -p err

# All service logs
journalctl -f | grep aitbc
```

### Performance Monitoring
```bash
# Resource usage
systemctl status aitbc-* | grep -E "(CPU|Memory)"

# Service start times
systemctl show aitbc-coordinator-api.service --property=ActiveEnterTimestamp

# Dependency failures
systemctl list-dependencies aitbc-coordinator-api.service
```

## 🔍 Troubleshooting

### Common Issues

#### Service Not Starting
```bash
# Check recent logs
journalctl -u aitbc-service-name.service -n 20

# Check for missing files
systemctl cat aitbc-service-name.service | grep ExecStart

# Verify working directory
ls -la /path/to/working/directory
```

#### Python Module Errors
```bash
# Check PYTHONPATH
systemctl cat aitbc-service-name.service | grep PYTHONPATH

# Verify module exists
python3 -c "import module.name"

# Install missing dependencies
pip3 install missing-package
```

#### Permission Issues
```bash
# Check file permissions
ls -la /var/lib/aitbc/keystore/

# Fix keystore permissions
chmod 700 /var/lib/aitbc/keystore/
chown root:root /var/lib/aitbc/keystore/
```

### Service-Specific Fixes

#### Coordinator API
```bash
# Check environment files
ls -la /home/oib/aitbc/apps/coordinator-api/.env

# Verify Python path
python3 -c "import sys; print(sys.path)"

# Test manual startup
cd /home/oib/aitbc/apps/coordinator-api
PYTHONPATH=/home/oib/aitbc/apps/coordinator-api/src python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Blockchain Node
```bash
# Check data directory
ls -la /var/lib/aitbc/data/

# Verify configuration
cat /opt/aitbc/apps/blockchain-node/.env.production

# Test blockchain module
cd /opt/aitbc/apps/blockchain-node
python3 -m aitbc_chain.main --help
```

## 🔄 Service Dependencies

### Startup Order
```
1. aitbc-agent-registry.service
2. aitbc-agent-coordinator.service
3. aitbc-coordinator-api.service
4. aitbc-blockchain-node.service
5. aitbc-blockchain-rpc.service
6. aitbc-exchange-api.service
7. aitbc-wallet.service
```

### Dependency Chain
```
network.target
├── aitbc-agent-registry.service
├── aitbc-agent-coordinator.service (requires: registry)
├── aitbc-coordinator-api.service
├── aitbc-blockchain-node.service
├── aitbc-blockchain-rpc.service (requires: node)
├── aitbc-exchange-api.service (requires: coordinator-api)
└── aitbc-wallet.service (requires: coordinator-api)
```

## 🛠️ Service Configuration

### Standard Service Template
```ini
[Unit]
Description=AITBC Service Name
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/service
Environment=PYTHONPATH=/path/to/src
ExecStart=/usr/bin/python3 -m module.name
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Environment Variables
```bash
# Common environment variables
PYTHONPATH=/path/to/src
KEYSTORE_PATH=/var/lib/aitbc/keystore
DB_PATH=/var/lib/aitbc/data
LOG_PATH=/var/lib/aitbc/logs
```

## 📋 Maintenance Procedures

### Regular Tasks
```bash
# Weekly service health check
for service in $(systemctl list-units --all | grep aitbc | awk '{print $1}'); do
    echo "=== $service ==="
    systemctl is-active "$service"
done

# Monthly log cleanup
journalctl --vacuum-time=30d

# Service configuration backup
cp -r /etc/systemd/system/aitbc-*.service /backup/systemd/```

### Service Updates
```bash
# After code changes
systemctl daemon-reload
systemctl restart aitbc-affected-service

# After dependency updates
systemctl restart aitbc-*

# Verify all services
systemctl status aitbc-* --no-pager
```

## 🚨 Emergency Procedures

### Service Recovery
```bash
# Emergency restart all services
systemctl restart aitbc-*

# Reset failed services
systemctl reset-failed aitbc-*

# Force service start
systemctl start aitbc-service-name.service --ignore-dependencies
```

### Disaster Recovery
```bash
# Restore from backup
cp /backup/systemd/aitbc-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aitbc-*
systemctl start aitbc-*
```

---

**Related Documentation**:
- [Runtime Directories Guide](../RUNTIME_DIRECTORIES.md)
- [Security Hardening Guide](SECURITY_HARDENING.md)
- [Infrastructure Overview](README.md)
