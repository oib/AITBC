---
description: Daily operations, monitoring, and troubleshooting for multi-node blockchain deployment
title: Multi-Node Blockchain Setup - Operations Module
version: 1.0
---

# Multi-Node Blockchain Setup - Operations Module

This module covers daily operations, monitoring, service management, and troubleshooting for the multi-node AITBC blockchain network.

## Prerequisites

- Complete [Core Setup Module](multi-node-blockchain-setup-core.md)
- Both nodes operational and synchronized
- Basic wallets created and funded

## Daily Operations

### Service Management

```bash
# Check service status on both nodes
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service'

# Restart services if needed
sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service
ssh aitbc1 'sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service'

# Check service logs
sudo journalctl -u aitbc-blockchain-node.service -f
sudo journalctl -u aitbc-blockchain-rpc.service -f
```

### Blockchain Monitoring

```bash
# Check blockchain height and sync status
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height')
echo "Genesis: $GENESIS_HEIGHT, Follower: $FOLLOWER_HEIGHT, Diff: $((FOLLOWER_HEIGHT - GENESIS_HEIGHT))"

# Check network status
curl -s http://localhost:8006/rpc/info | jq .
ssh aitbc1 'curl -s http://localhost:8006/rpc/info | jq .'

# Monitor block production
watch -n 10 'curl -s http://localhost:8006/rpc/head | jq "{height: .height, timestamp: .timestamp}"'
```

### Wallet Operations

```bash
# Check wallet balances
cd /opt/aitbc && source venv/bin/activate
./aitbc-cli wallet balance genesis-ops
./aitbc-cli wallet balance user-wallet

# Send transactions
./aitbc-cli wallet send genesis-ops user-wallet 100 123

# Check transaction history
./aitbc-cli wallet transactions genesis-ops --limit 10

# Cross-node transaction
FOLLOWER_ADDR=$(ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli wallet list | grep "follower-ops:" | cut -d" " -f2')
./aitbc-cli wallet send genesis-ops $FOLLOWER_ADDR 50 123
```

## Health Monitoring

### Automated Health Check

```bash
# Comprehensive health monitoring script
python3 /tmp/aitbc1_heartbeat.py

# Manual health checks
curl -s http://localhost:8006/health | jq .
ssh aitbc1 'curl -s http://localhost:8006/health | jq .'

# Check system resources
free -h
df -h /var/lib/aitbc
ssh aitbc1 'free -h && df -h /var/lib/aitbc'
```

### Performance Monitoring

```bash
# Check RPC performance
time curl -s http://localhost:8006/rpc/head > /dev/null
time ssh aitbc1 'curl -s http://localhost:8006/rpc/head > /dev/null'

# Monitor database size
du -sh /var/lib/aitbc/data/ait-mainnet/
ssh aitbc1 'du -sh /var/lib/aitbc/data/ait-mainnet/'

# Check network latency
ping -c 5 aitbc1
ssh aitbc1 'ping -c 5 localhost'
```

## Troubleshooting Common Issues

### Service Issues

| Problem | Symptoms | Diagnosis | Fix |
|---|---|---|---|
| RPC not responding | Connection refused on port 8006 | `curl -s http://localhost:8006/health` fails | Restart RPC service: `sudo systemctl restart aitbc-blockchain-rpc.service` |
| Block production stopped | Height not increasing | Check proposer status | Restart node service: `sudo systemctl restart aitbc-blockchain-node.service` |
| High memory usage | System slow, OOM errors | `free -h` shows low memory | Restart services, check for memory leaks |
| Disk space full | Services failing | `df -h` shows 100% on data partition | Clean old logs, prune database if needed |

### Blockchain Issues

| Problem | Symptoms | Diagnosis | Fix |
|---|---|---|---|
| Nodes out of sync | Height difference > 10 | Compare heights on both nodes | Check network connectivity, restart services |
| Transactions stuck | Transaction not mining | Check mempool status | Verify proposer is active, check transaction validity |
| Wallet balance wrong | Balance shows 0 or incorrect | Check wallet on correct node | Query balance on node where wallet was created |
| Genesis missing | No blockchain data | Check data directory | Verify genesis block creation, re-run core setup |

### Network Issues

| Problem | Symptoms | Diagnosis | Fix |
|---|---|---|---|
| SSH connection fails | Can't reach follower node | `ssh aitbc1` times out | Check network, SSH keys, firewall |
| Gossip not working | No block propagation | Check Redis connectivity | Verify Redis configuration, restart Redis |
| RPC connectivity | Can't reach RPC endpoints | `curl` fails | Check service status, port availability |

## Performance Optimization

### Database Optimization

```bash
# Check database fragmentation
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "PRAGMA table_info(blocks);"

# Vacuum database (maintenance window)
sudo systemctl stop aitbc-blockchain-node.service aitbc-blockchain-rpc.service
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM;"
sudo systemctl start aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Check database size growth
du -sh /var/lib/aitbc/data/ait-mainnet/chain.db
```

### Log Management

```bash
# Check log sizes
du -sh /var/log/aitbc/*

# Rotate logs if needed
sudo logrotate -f /etc/logrotate.d/aitbc

# Clean old logs (older than 7 days)
find /var/log/aitbc -name "*.log" -mtime +7 -delete
```

### Resource Monitoring

```bash
# Monitor CPU usage
top -p $(pgrep aitbc-blockchain)

# Monitor memory usage
ps aux | grep aitbc-blockchain

# Monitor disk I/O
iotop -p $(pgrep aitbc-blockchain)

# Monitor network traffic
iftop -i eth0
```

## Backup and Recovery

### Database Backup

```bash
# Create backup
BACKUP_DIR="/var/backups/aitbc/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db $BACKUP_DIR/
sudo cp /var/lib/aitbc/data/ait-mainnet/mempool.db $BACKUP_DIR/

# Backup keystore
sudo cp -r /var/lib/aitbc/keystore $BACKUP_DIR/

# Backup configuration
sudo cp /etc/aitbc/.env $BACKUP_DIR/
```

### Recovery Procedures

```bash
# Restore from backup
BACKUP_DIR="/var/backups/aitbc/20240330"
sudo systemctl stop aitbc-blockchain-node.service aitbc-blockchain-rpc.service
sudo cp $BACKUP_DIR/chain.db /var/lib/aitbc/data/ait-mainnet/
sudo cp $BACKUP_DIR/mempool.db /var/lib/aitbc/data/ait-mainnet/
sudo systemctl start aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Verify recovery
curl -s http://localhost:8006/rpc/head | jq .height
```

## Security Operations

### Security Monitoring

```bash
# Check for unauthorized access
sudo grep "Failed password" /var/log/auth.log | tail -10

# Monitor blockchain for suspicious activity
./aitbc-cli wallet transactions genesis-ops --limit 20 | grep -E "(large|unusual)"

# Check file permissions
ls -la /var/lib/aitbc/
ls -la /etc/aitbc/
```

### Security Hardening

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Check for open ports
netstat -tlnp | grep -E "(8006|7070)"

# Verify firewall status
sudo ufw status
```

## Automation Scripts

### Daily Health Check Script

```bash
#!/bin/bash
# daily_health_check.sh

echo "=== Daily Health Check $(date) ==="

# Check services
echo "Services:"
systemctl is-active aitbc-blockchain-node.service aitbc-blockchain-rpc.service
ssh aitbc1 'systemctl is-active aitbc-blockchain-node.service aitbc-blockchain-rpc.service'

# Check sync
echo "Sync Status:"
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height')
echo "Genesis: $GENESIS_HEIGHT, Follower: $FOLLOWER_HEIGHT"

# Check disk space
echo "Disk Usage:"
df -h /var/lib/aitbc
ssh aitbc1 'df -h /var/lib/aitbc'

# Check memory
echo "Memory Usage:"
free -h
ssh aitbc1 'free -h'
```

### Automated Recovery Script

```bash
#!/bin/bash
# auto_recovery.sh

# Check if services are running
if ! systemctl is-active --quiet aitbc-blockchain-node.service; then
    echo "Restarting blockchain node service..."
    sudo systemctl restart aitbc-blockchain-node.service
fi

if ! systemctl is-active --quiet aitbc-blockchain-rpc.service; then
    echo "Restarting RPC service..."
    sudo systemctl restart aitbc-blockchain-rpc.service
fi

# Check sync status
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height')

if [ $((FOLLOWER_HEIGHT - GENESIS_HEIGHT)) -gt 10 ]; then
    echo "Nodes out of sync, restarting follower services..."
    ssh aitbc1 'sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service'
fi
```

## Monitoring Dashboard

### Key Metrics to Monitor

- **Block Height**: Should be equal on both nodes
- **Transaction Rate**: Normal vs abnormal patterns
- **Memory Usage**: Should be stable over time
- **Disk Usage**: Monitor growth rate
- **Network Latency**: Between nodes
- **Error Rates**: In logs and transactions

### Alert Thresholds

```bash
# Create monitoring alerts
if [ $((FOLLOWER_HEIGHT - GENESIS_HEIGHT)) -gt 20 ]; then
    echo "ALERT: Nodes significantly out of sync"
fi

DISK_USAGE=$(df /var/lib/aitbc | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "ALERT: Disk usage above 80%"
fi

MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [ $MEMORY_USAGE -gt 90 ]; then
    echo "ALERT: Memory usage above 90%"
fi
```

## Dependencies

This operations module depends on:
- **[Core Setup Module](multi-node-blockchain-setup-core.md)** - Basic node setup required

## Next Steps

After mastering operations, proceed to:
- **[Advanced Features Module](multi-node-blockchain-advanced.md)** - Smart contracts and security testing
- **[Production Module](multi-node-blockchain-production.md)** - Production deployment and scaling
