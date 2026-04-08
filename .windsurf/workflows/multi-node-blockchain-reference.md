---
description: Configuration overview, verification commands, system overview, success metrics, and best practices
title: Multi-Node Blockchain Setup - Reference Module
version: 1.0
---

# Multi-Node Blockchain Setup - Reference Module

This module provides comprehensive reference information including configuration overview, verification commands, system overview, success metrics, and best practices for the multi-node AITBC blockchain network.

## Configuration Overview

### Environment Configuration

```bash
# Main configuration file
/etc/aitbc/.env

# Production configuration
/etc/aitbc/.env.production

# Key configuration parameters
CHAIN_ID=ait-mainnet
PROPOSER_ID=ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871
ENABLE_BLOCK_PRODUCTION=true
BLOCK_TIME_SECONDS=10
MAX_TXS_PER_BLOCK=1000
MAX_BLOCK_SIZE_BYTES=2097152
MEMPOOL_MAX_SIZE=10000
MEMPOOL_MIN_FEE=10
GOSSIP_BACKEND=redis
GOSSIP_BROADCAST_URL=redis://10.1.223.40:6379
RPC_TLS_ENABLED=false
AUDIT_LOG_ENABLED=true
```

### Service Configuration

```bash
# Systemd services
/etc/systemd/system/aitbc-blockchain-node.service
/etc/systemd/system/aitbc-blockchain-rpc.service

# Production services
/etc/systemd/system/aitbc-blockchain-node-production.service
/etc/systemd/system/aitbc-blockchain-rpc-production.service

# Service dependencies
aitbc-blockchain-rpc.service -> aitbc-blockchain-node.service
```

### Database Configuration

```bash
# Database location
/var/lib/aitbc/data/ait-mainnet/chain.db
/var/lib/aitbc/data/ait-mainnet/mempool.db

# Database optimization settings
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;
```

### Network Configuration

```bash
# RPC service
Port: 8006
Protocol: HTTP/HTTPS
TLS: Optional (production)

# P2P service
Port: 7070
Protocol: TCP
Encryption: Optional

# Gossip network
Backend: Redis
Host: 10.1.223.40:6379
Encryption: Optional
```

## Verification Commands

### Basic Health Checks

```bash
# Check service status
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service'

# Check blockchain health
curl -s http://localhost:8006/health | jq .
ssh aitbc1 'curl -s http://localhost:8006/health | jq .'

# Check blockchain height
curl -s http://localhost:8006/rpc/head | jq .height
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

# Verify sync status
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height)
echo "Height difference: $((FOLLOWER_HEIGHT - GENESIS_HEIGHT))"
```

### Wallet Verification

```bash
# List all wallets
cd /opt/aitbc && source venv/bin/activate
./aitbc-cli wallet list

# Check specific wallet balance
./aitbc-cli wallet balance genesis-ops
./aitbc-cli wallet balance follower-ops

# Verify wallet addresses
./aitbc-cli wallet list | grep -E "(genesis-ops|follower-ops)"

# Test wallet operations
./aitbc-cli wallet send genesis-ops follower-ops 10 123
```

### Network Verification

```bash
# Test connectivity
ping -c 3 aitbc1
ssh aitbc1 'ping -c 3 localhost'

# Test RPC endpoints
curl -s http://localhost:8006/rpc/head > /dev/null && echo "Local RPC OK"
ssh aitbc1 'curl -s http://localhost:8007/rpc/head > /dev/null && echo "Remote RPC OK"'

# Test P2P connectivity
telnet aitbc1 7070

# Check network latency
ping -c 5 aitbc1 | tail -1
```

### AI Operations Verification

```bash
# Check AI services
./aitbc-cli market list

# Test AI job submission
./aitbc-cli ai submit --wallet genesis-ops --type inference --prompt "test" --payment 10

# Verify resource allocation
./aitbc-cli resource status

# Check AI job status
./aitbc-cli ai status --job-id "latest"
```

### Smart Contract Verification

```bash
# Check contract deployment
./aitbc-cli contract list

# Test messaging system
curl -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test", "agent_address": "address", "title": "Test", "description": "Test"}'

# Verify contract state
./aitbc-cli contract state --name "AgentMessagingContract"
```

## System Overview

### Architecture Components

```
┌─────────────────┐    ┌─────────────────┐
│   Genesis Node   │    │  Follower Node   │
│   (aitbc)        │    │   (aitbc1)       │
├─────────────────┤    ├─────────────────┤
│ Blockchain Node  │    │ Blockchain Node  │
│ RPC Service      │    │ RPC Service      │
│ Keystore         │    │ Keystore         │
│ Database         │    │ Database         │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────────────────────┘
               P2P Network
         │                       │
         └───────────────────────┘
               Gossip Network
                     │
               ┌─────────┐
               │  Redis  │
               └─────────┘
```

### Data Flow

```
CLI Command → RPC Service → Blockchain Node → Database
                ↓
            Smart Contract → Blockchain State
                ↓
            Gossip Network → Other Nodes
```

### Service Dependencies

```
aitbc-blockchain-rpc.service
    ↓ depends on
aitbc-blockchain-node.service
    ↓ depends on
Redis Service (for gossip)
```

## Success Metrics

### Blockchain Metrics

| Metric | Target | Acceptable Range | Critical |
|---|---|---|---|
| Block Height Sync | Equal | ±1 block | >5 blocks |
| Block Production Rate | 1 block/10s | 5-15s/block | >30s/block |
| Transaction Confirmation | <10s | <30s | >60s |
| Network Latency | <10ms | <50ms | >100ms |

### System Metrics

| Metric | Target | Acceptable Range | Critical |
|---|---|---|---|
| CPU Usage | <50% | 50-80% | >90% |
| Memory Usage | <70% | 70-85% | >95% |
| Disk Usage | <80% | 80-90% | >95% |
| Network I/O | <70% | 70-85% | >95% |

### Service Metrics

| Metric | Target | Acceptable Range | Critical |
|---|---|---|---|
| Service Uptime | 99.9% | 99-99.5% | <95% |
| RPC Response Time | <100ms | 100-500ms | >1s |
| Error Rate | <1% | 1-5% | >10% |
| Failed Transactions | <0.5% | 0.5-2% | >5% |

### AI Operations Metrics

| Metric | Target | Acceptable Range | Critical |
|---|---|---|---|
| Job Success Rate | >95% | 90-95% | <90% |
| Job Completion Time | <5min | 5-15min | >30min |
| GPU Utilization | >70% | 50-70% | <50% |
| Marketplace Volume | Growing | Stable | Declining |

## Quick Reference Commands

### Daily Operations

```bash
# Quick health check
./aitbc-cli blockchain info && ./aitbc-cli network status

# Service status
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Cross-node sync check
curl -s http://localhost:8006/rpc/head | jq .height && ssh aitbc1 'curl -s http://localhost:8007/rpc/head | jq .height'

# Wallet balance check
./aitbc-cli wallet balance genesis-ops
```

### Troubleshooting

```bash
# Check logs
sudo journalctl -u aitbc-blockchain-node.service -f
sudo journalctl -u aitbc-blockchain-rpc.service -f

# Restart services
sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Check database integrity
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "PRAGMA integrity_check;"

# Verify network connectivity
ping -c 3 aitbc1 && ssh aitbc1 'ping -c 3 localhost'
```

### Performance Monitoring

```bash
# System resources
top -p $(pgrep aitbc-blockchain)
free -h
df -h /var/lib/aitbc

# Blockchain performance
./aitbc-cli analytics --period "1h"

# Network performance
iftop -i eth0
```

## Best Practices

### Security Best Practices

```bash
# Regular security updates
sudo apt update && sudo apt upgrade -y

# Monitor access logs
sudo grep "Failed password" /var/log/auth.log | tail -10

# Use strong passwords for wallets
echo "Use passwords with: minimum 12 characters, mixed case, numbers, symbols"

# Regular backups
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db /var/backups/aitbc/chain-$(date +%Y%m%d).db
```

### Performance Best Practices

```bash
# Regular database maintenance
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM; ANALYZE;"

# Monitor resource usage
watch -n 30 'free -h && df -h /var/lib/aitbc'

# Optimize system parameters
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Operational Best Practices

```bash
# Use session IDs for agent workflows
SESSION_ID="task-$(date +%s)"
openclaw agent --agent main --session-id $SESSION_ID --message "Task description"

# Always verify transactions
./aitbc-cli wallet transactions wallet-name --limit 5

# Monitor cross-node synchronization
watch -n 10 'curl -s http://localhost:8006/rpc/head | jq .height && ssh aitbc1 "curl -s http://localhost:8007/rpc/head | jq .height"'
```

### Development Best Practices

```bash
# Test in development environment first
./aitbc-cli wallet send test-wallet test-wallet 1 test

# Use meaningful wallet names
./aitbc-cli wallet create "genesis-operations" "strong_password"

# Document all configuration changes
git add /etc/aitbc/.env
git commit -m "Update configuration: description of changes"
```

## Troubleshooting Guide

### Common Issues and Solutions

#### Service Issues

**Problem**: Services won't start
```bash
# Check configuration
sudo journalctl -u aitbc-blockchain-node.service -n 50

# Check permissions
ls -la /var/lib/aitbc/
sudo chown -R aitbc:aitbc /var/lib/aitbc

# Check dependencies
systemctl status redis
```

#### Network Issues

**Problem**: Nodes can't communicate
```bash
# Check network connectivity
ping -c 3 aitbc1
ssh aitbc1 'ping -c 3 localhost'

# Check firewall
sudo ufw status
sudo ufw allow 8006/tcp
sudo ufw allow 7070/tcp

# Check port availability
netstat -tlnp | grep -E "(8006|7070)"
```

#### Blockchain Issues

**Problem**: Nodes out of sync
```bash
# Check heights
curl -s http://localhost:8006/rpc/head | jq .height
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

# Check gossip status
redis-cli ping
redis-cli info replication

# Restart services if needed
sudo systemctl restart aitbc-blockchain-node.service
```

#### Wallet Issues

**Problem**: Wallet balance incorrect
```bash
# Check correct node
./aitbc-cli wallet balance wallet-name
ssh aitbc1 './aitbc-cli wallet balance wallet-name'

# Verify wallet address
./aitbc-cli wallet list | grep "wallet-name"

# Check transaction history
./aitbc-cli wallet transactions wallet-name --limit 10
```

#### AI Operations Issues

**Problem**: AI jobs not processing
```bash
# Check AI services
./aitbc-cli market list

# Check resource allocation
./aitbc-cli resource status

# Check AI job status
./aitbc-cli ai status --job-id "job_id"

# Verify wallet balance
./aitbc-cli wallet balance wallet-name
```

### Emergency Procedures

#### Service Recovery

```bash
# Emergency service restart
sudo systemctl stop aitbc-blockchain-node.service aitbc-blockchain-rpc.service
sudo systemctl start aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Database recovery
sudo systemctl stop aitbc-blockchain-node.service
sudo cp /var/backups/aitbc/chain-backup.db /var/lib/aitbc/data/ait-mainnet/chain.db
sudo systemctl start aitbc-blockchain-node.service
```

#### Network Recovery

```bash
# Reset network configuration
sudo systemctl restart networking
sudo ip addr flush
sudo systemctl restart aitbc-blockchain-node.service

# Re-establish P2P connections
sudo systemctl restart aitbc-blockchain-node.service
sleep 10
sudo systemctl restart aitbc-blockchain-rpc.service
```

## Dependencies

This reference module provides information for all other modules:
- **[Core Setup Module](multi-node-blockchain-setup-core.md)** - Basic setup verification
- **[Operations Module](multi-node-blockchain-operations.md)** - Daily operations reference
- **[Advanced Features Module](multi-node-blockchain-advanced.md)** - Advanced operations reference
- **[Production Module](multi-node-blockchain-production.md)** - Production deployment reference
- **[Marketplace Module](multi-node-blockchain-marketplace.md)** - Marketplace operations reference

## Documentation Maintenance

### Updating This Reference

1. Update configuration examples when new parameters are added
2. Add new verification commands for new features
3. Update success metrics based on production experience
4. Add new troubleshooting solutions for discovered issues
5. Update best practices based on operational experience

### Version Control

```bash
# Track documentation changes
git add .windsurf/workflows/multi-node-blockchain-reference.md
git commit -m "Update reference documentation: description of changes"
git tag -a "v1.1" -m "Reference documentation v1.1"
```

This reference module serves as the central hub for all multi-node blockchain setup operations and should be kept up-to-date with the latest system capabilities and operational procedures.
