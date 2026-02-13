# Troubleshooting
Common issues and solutions for blockchain nodes.

## Common Issues

### Node Won't Start

```bash
# Check logs
tail -f ~/.aitbc/logs/chain.log

# Common causes:
# - Port already in use
# - Corrupted database
# - Invalid configuration
```

**Solutions:**
```bash
# Kill existing process
sudo lsof -i :8080
sudo kill $(sudo lsof -t -i :8080)

# Reset database
rm -rf ~/.aitbc/data/chain.db
aitbc-chain init

# Validate config
aitbc-chain validate-config
```

### Sync Stuck

```bash
# Check sync status
aitbc-chain sync-status

# Force sync from scratch
aitbc-chain reset --hard

# Check peer connectivity
aitbc-chain p2p connections
```

**Solutions:**
```bash
# Add more peers
aitbc-chain p2p add-bootstrap /dns4/new-peer.example.com/tcp/7070/p2p/...

# Clear peer database
rm -rf ~/.aitbc/data/peers.db

# Restart with fresh sync
aitbc-chain start --sync-mode full
```

### P2P Connection Issues

```bash
# Check connectivity
aitbc-chain p2p check-connectivity

# Test port forwarding
curl http://localhost:8080/rpc/net_info
```

**Solutions:**
```bash
# Open firewall
sudo ufw allow 7070/tcp
sudo ufw allow 8080/tcp

# Check NAT configuration
aitbc-chain p2p nat-status

# Use relay mode
aitbc-chain start --p2p-relay-enabled
```

### High Memory Usage

```bash
# Check memory usage
htop | grep aitbc-chain

# Check database size
du -sh ~/.aitbc/data/
```

**Solutions:**
```bash
# Prune old data
aitbc-chain prune --keep-blocks 10000

# Reduce peer count
# Edit config: max_peers: 25

# Enable compression
aitbc-chain start --db-compression
```

### RPC Not Responding

```bash
# Check RPC status
curl http://localhost:8080/rpc/health

# Check if RPC is enabled
aitbc-chain status | grep RPC
```

**Solutions:**
```bash
# Restart with RPC enabled
aitbc-chain start --rpc-enabled

# Check CORS settings
# Edit config: rpc.cors_origins

# Increase rate limits
# Edit config: rpc.rate_limit: 2000
```

## Diagnostic Commands

```bash
# Full system check
aitbc-chain doctor

# Network diagnostics
aitbc-chain diagnose network

# Database diagnostics
aitbc-chain diagnose database

# Log analysis
aitbc-chain logs --analyze
```

## Getting Help

```bash
# Generate debug report
aitbc-chain debug-report > debug.txt

# Share on Discord or GitHub Issues
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
