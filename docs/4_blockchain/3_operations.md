# Node Operations

Day-to-day operations for blockchain nodes using the enhanced AITBC CLI.

## Enhanced CLI Blockchain Commands

The enhanced AITBC CLI provides comprehensive blockchain management capabilities:

```bash
# Blockchain status and synchronization
aitbc blockchain status
aitbc blockchain sync
aitbc blockchain info

# Network information
aitbc blockchain peers
aitbc blockchain blocks --limit 10
aitbc blockchain validators

# Transaction operations
aitbc blockchain transaction <TX_ID>
```

## Starting the Node

```bash
# Enhanced CLI node management
aitbc blockchain node start

# Start with custom configuration
aitbc blockchain node start --config /path/to/config.yaml

# Start as daemon
aitbc blockchain node start --daemon

# Legacy commands (still supported)
aitbc-chain start
aitbc-chain start --daemon
```

## Stopping the Node

```bash
# Enhanced CLI graceful shutdown
aitbc blockchain node stop

# Force stop
aitbc blockchain node stop --force

# Legacy commands
aitbc-chain stop
aitbc-chain stop --force
```

## Node Status

```bash
# Enhanced CLI status with more details
aitbc blockchain status

# Detailed node information
aitbc blockchain info

# Network status
aitbc blockchain peers

# Legacy command
aitbc-chain status
```

Shows:
- Block height
- Peers connected
- Mempool size
- Last block time
- Network health
- Validator status

## Checking Sync Status

```bash
# Enhanced CLI sync status
aitbc blockchain sync

# Detailed sync information
aitbc blockchain sync --verbose

# Progress monitoring
aitbc blockchain sync --watch

# Legacy command
aitbc-chain sync-status
```

Shows:
- Current height
- Target height
- Sync progress percentage
- Estimated time to sync
- Network difficulty
- Block production rate

## Managing Peers

### List Peers

```bash
# Enhanced CLI peer management
aitbc blockchain peers

# Detailed peer information
aitbc blockchain peers --detailed

# Filter by status
aitbc blockchain peers --status connected

# Legacy command
aitbc-chain peers list
```

### Add Peer

```bash
# Enhanced CLI peer addition
aitbc blockchain peers add /dns4/new-node.example.com/tcp/7070/p2p/...

# Add with validation
aitbc blockchain peers add --peer <MULTIADDR> --validate

# Legacy command
aitbc-chain peers add /dns4/new-node.example.com/tcp/7070/p2p/...
```

### Remove Peer

```bash
# Enhanced CLI peer removal
aitbc blockchain peers remove <PEER_ID>

# Remove with confirmation
aitbc blockchain peers remove <PEER_ID> --confirm

# Legacy command
aitbc-chain peers remove <PEER_ID>
```

## Validator Operations

```bash
# Enhanced CLI validator management
aitbc blockchain validators

# Validator status
aitbc blockchain validators --status active

# Validator rewards
aitbc blockchain validators --rewards

# Become a validator
aitbc blockchain validators register --stake 1000

# Legacy equivalent
aitbc-validator status
```

## Backup & Restore

### Backup Data

```bash
# Enhanced CLI backup with more options
aitbc blockchain backup --output /backup/chain-backup.tar.gz

# Compressed backup
aitbc blockchain backup --compress --output /backup/chain-backup.tar.gz

# Incremental backup
aitbc blockchain backup --incremental --output /backup/incremental.tar.gz

# Legacy command
aitbc-chain backup --output /backup/chain-backup.tar.gz
```

### Restore Data

```bash
# Enhanced CLI restore with validation
aitbc blockchain restore --input /backup/chain-backup.tar.gz

# Restore with verification
aitbc blockchain restore --input /backup/chain-backup.tar.gz --verify

# Legacy command
aitbc-chain restore --input /backup/chain-backup.tar.gz
```

## Log Management

```bash
# Enhanced CLI log management
aitbc blockchain logs --tail 100

# Filter by level and component
aitbc blockchain logs --level error --component consensus

# Real-time monitoring
aitbc blockchain logs --follow

# Export logs with formatting
aitbc blockchain logs --export /var/log/aitbc-chain.log --format json

# Legacy commands
aitbc-chain logs --tail 100
aitbc-chain logs --level error
```

## Advanced Operations

### Network Diagnostics

```bash
# Enhanced CLI network diagnostics
aitbc blockchain diagnose --network

# Full system diagnostics
aitbc blockchain diagnose --full

# Connectivity test
aitbc blockchain test-connectivity
```

### Performance Monitoring

```bash
# Enhanced CLI performance metrics
aitbc blockchain metrics

# Resource usage
aitbc blockchain metrics --resource

# Historical performance
aitbc blockchain metrics --history 24h
```

### Configuration Management

```bash
# Enhanced CLI configuration
aitbc blockchain config show

# Update configuration
aitbc blockchain config set key value

# Validate configuration
aitbc blockchain config validate

# Reset to defaults
aitbc blockchain config reset
```

## Troubleshooting with Enhanced CLI

### Node Won't Start

```bash
# Enhanced CLI diagnostics
aitbc blockchain diagnose --startup

# Check configuration
aitbc blockchain config validate

# View detailed logs
aitbc blockchain logs --level error --follow

# Reset database if needed
aitbc blockchain reset --hard
```

### Sync Issues

```bash
# Enhanced CLI sync diagnostics
aitbc blockchain diagnose --sync

# Force resync
aitbc blockchain sync --force

# Check peer connectivity
aitbc blockchain peers --status connected

# Network health check
aitbc blockchain diagnose --network
```

### Performance Issues

```bash
# Enhanced CLI performance analysis
aitbc blockchain metrics --detailed

# Resource monitoring
aitbc blockchain metrics --resource --follow

# Bottleneck analysis
aitbc blockchain diagnose --performance
```

## Integration with Monitoring

```bash
# Enhanced CLI monitoring integration
aitbc monitor dashboard --component blockchain

# Set up alerts
aitbc monitor alerts create --type blockchain_sync --threshold 90%

# Export metrics for Prometheus
aitbc blockchain metrics --export prometheus
```

## Best Practices

1. **Use enhanced CLI commands** for better functionality
2. **Monitor regularly** with `aitbc blockchain status`
3. **Backup frequently** using enhanced backup options
4. **Validate configuration** before starting node
5. **Use diagnostic tools** for troubleshooting
6. **Integrate with monitoring** for production deployments

## Migration from Legacy Commands

If you're migrating from legacy commands:

```bash
# Old → New
aitbc-chain start → aitbc blockchain node start
aitbc-chain status → aitbc blockchain status
aitbc-chain peers list → aitbc blockchain peers
aitbc-chain backup → aitbc blockchain backup
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Consensus](./4_consensus.md) — Consensus mechanism
- [Enhanced CLI](../23_cli/README.md) — Complete CLI reference
