# Troubleshooting

Common issues and solutions for blockchain nodes using the enhanced AITBC CLI.

## Enhanced CLI Diagnostics

The enhanced AITBC CLI provides comprehensive diagnostic tools:

```bash
# Full system diagnostics
aitbc blockchain diagnose --full

# Network diagnostics
aitbc blockchain diagnose --network

# Sync diagnostics
aitbc blockchain diagnose --sync

# Performance diagnostics
aitbc blockchain diagnose --performance

# Startup diagnostics
aitbc blockchain diagnose --startup
```

## Common Issues

### Node Won't Start

```bash
# Enhanced CLI diagnostics
aitbc blockchain diagnose --startup

# Check configuration
aitbc blockchain config validate

# View detailed logs
aitbc blockchain logs --level error --follow

# Check port usage
aitbc blockchain diagnose --network

# Common causes:
# - Port already in use
# - Corrupted database
# - Invalid configuration
```

**Solutions:**
```bash
# Enhanced CLI port check
aitbc blockchain diagnose --network --check-ports

# Kill existing process (if needed)
sudo lsof -i :8080
sudo kill $(sudo lsof -t -i :8080)

# Reset database with enhanced CLI
aitbc blockchain reset --hard

# Validate and fix configuration
aitbc blockchain config validate
aitbc blockchain config fix

# Legacy approach
tail -f ~/.aitbc/logs/chain.log
rm -rf ~/.aitbc/data/chain.db
aitbc-chain init
```

### Sync Stuck

```bash
# Enhanced CLI sync diagnostics
aitbc blockchain diagnose --sync

# Check sync status with details
aitbc blockchain sync --verbose

# Force resync
aitbc blockchain sync --force

# Check peer connectivity
aitbc blockchain peers --status connected

# Network health check
aitbc blockchain diagnose --network

# Monitor sync progress
aitbc blockchain sync --watch
```

**Solutions:**
```bash
# Enhanced CLI peer management
aitbc blockchain peers add --peer <MULTIADDR> --validate

# Add more bootstrap peers
aitbc blockchain peers add --bootstrap /dns4/new-peer.example.com/tcp/7070/p2p/...

# Clear peer database
aitbc blockchain peers clear

# Reset and resync
aitbc blockchain reset --sync
aitbc blockchain sync --force

# Check network connectivity
aitbc blockchain test-connectivity
```

### High CPU/Memory Usage

```bash
# Enhanced CLI performance diagnostics
aitbc blockchain diagnose --performance

# Monitor resource usage
aitbc blockchain metrics --resource --follow

# Check for bottlenecks
aitbc blockchain metrics --detailed

# Historical performance data
aitbc blockchain metrics --history 24h
```

**Solutions:**
```bash
# Optimize configuration
aitbc blockchain config set max_peers 50
aitbc blockchain config set cache_size 1GB

# Enable performance mode
aitbc blockchain optimize --performance

# Monitor improvements
aitbc blockchain metrics --resource --follow
```

### Peer Connection Issues

```bash
# Enhanced CLI peer diagnostics
aitbc blockchain diagnose --network

# Check peer status
aitbc blockchain peers --detailed

# Test connectivity
aitbc blockchain test-connectivity

# Network diagnostics
aitbc blockchain diagnose --network --full
```

**Solutions:**
```bash
# Add reliable peers
aitbc blockchain peers add --bootstrap <MULTIADDR>

# Update peer configuration
aitbc blockchain config set bootstrap_nodes <NODES>

# Reset peer database
aitbc blockchain peers reset

# Check firewall settings
aitbc blockchain diagnose --network --firewall
```

### Validator Issues

```bash
# Enhanced CLI validator diagnostics
aitbc blockchain validators --diagnose

# Check validator status
aitbc blockchain validators --status active

# Validator rewards tracking
aitbc blockchain validators --rewards

# Performance metrics
aitbc blockchain validators --metrics
```

**Solutions:**
```bash
# Re-register as validator
aitbc blockchain validators register --stake 1000

# Check stake requirements
aitbc blockchain validators --requirements

# Monitor validator performance
aitbc blockchain validators --monitor
```

## Advanced Troubleshooting

### Database Corruption

```bash
# Enhanced CLI database diagnostics
aitbc blockchain diagnose --database

# Database integrity check
aitbc blockchain database check

# Repair database
aitbc blockchain database repair

# Rebuild database
aitbc blockchain database rebuild
```

### Configuration Issues

```bash
# Enhanced CLI configuration diagnostics
aitbc blockchain config diagnose

# Validate configuration
aitbc blockchain config validate

# Reset to defaults
aitbc blockchain config reset

# Generate new configuration
aitbc blockchain config generate
```

### Network Issues

```bash
# Enhanced CLI network diagnostics
aitbc blockchain diagnose --network --full

# Test all network endpoints
aitbc blockchain test-connectivity --all

# Check DNS resolution
aitbc blockchain diagnose --network --dns

# Firewall diagnostics
aitbc blockchain diagnose --network --firewall
```

## Monitoring and Alerting

### Real-time Monitoring

```bash
# Enhanced CLI monitoring
aitbc monitor dashboard --component blockchain

# Set up alerts
aitbc monitor alerts create --type blockchain_sync --threshold 90%

# Resource monitoring
aitbc blockchain metrics --resource --follow

# Export metrics
aitbc blockchain metrics --export prometheus
```

### Log Analysis

```bash
# Enhanced CLI log analysis
aitbc blockchain logs --analyze --level error

# Export logs for analysis
aitbc blockchain logs --export /tmp/blockchain-logs.json --format json

# Filter by time range
aitbc blockchain logs --since "1 hour ago" --level error

# Real-time log monitoring
aitbc blockchain logs --follow --level warn
```

## Recovery Procedures

### Complete Node Recovery

```bash
# Enhanced CLI recovery sequence
aitbc blockchain backup --emergency

# Stop node safely
aitbc blockchain node stop --force

# Reset everything
aitbc blockchain reset --hard

# Restore from backup
aitbc blockchain restore --input /backup/emergency-backup.tar.gz --verify

# Start node
aitbc blockchain node start

# Monitor recovery
aitbc blockchain sync --watch
```

### Emergency Procedures

```bash
# Emergency stop
aitbc blockchain node stop --emergency

# Emergency backup
aitbc blockchain backup --emergency --compress

# Emergency reset
aitbc blockchain reset --emergency

# Emergency recovery
aitbc blockchain recover --from-backup /backup/emergency.tar.gz
```

## Best Practices

### Prevention

1. **Regular monitoring** with enhanced CLI tools
2. **Automated backups** using enhanced backup options
3. **Configuration validation** before changes
4. **Performance monitoring** for early detection
5. **Network diagnostics** for connectivity issues

### Maintenance

1. **Weekly diagnostics** with `aitbc blockchain diagnose --full`
2. **Monthly backups** with verification
3. **Quarterly performance reviews**
4. **Configuration audits**
5. **Security scans**

### Troubleshooting Workflow

1. **Run diagnostics**: `aitbc blockchain diagnose --full`
2. **Check logs**: `aitbc blockchain logs --level error --follow`
3. **Verify configuration**: `aitbc blockchain config validate`
4. **Test connectivity**: `aitbc blockchain test-connectivity`
5. **Apply fixes**: Use enhanced CLI commands
6. **Monitor recovery**: `aitbc blockchain status --watch`

## Integration with Support

### Export Diagnostic Data

```bash
# Export full diagnostic report
aitbc blockchain diagnose --full --export /tmp/diagnostic-report.json

# Export logs for support
aitbc blockchain logs --export /tmp/support-logs.tar.gz --compress

# Export configuration
aitbc blockchain config export --output /tmp/config-backup.yaml
```

### Support Commands

```bash
# Generate support bundle
aitbc blockchain support-bundle --output /tmp/support-bundle.tar.gz

# System information
aitbc blockchain system-info --export /tmp/system-info.json

# Performance report
aitbc blockchain metrics --report --output /tmp/performance-report.json
```

## Legacy Command Equivalents

For users transitioning from legacy commands:

```bash
# Old → New
tail -f ~/.aitbc/logs/chain.log → aitbc blockchain logs --follow
aitbc-chain validate-config → aitbc blockchain config validate
aitbc-chain reset --hard → aitbc blockchain reset --hard
aitbc-chain p2p connections → aitbc blockchain peers --status connected
```

## Next

- [Operations](./3_operations.md) — Day-to-day operations
- [Configuration](./2_configuration.md) — Node configuration
- [Enhanced CLI](../23_cli/README.md) — Complete CLI reference
- [Monitoring](./7_monitoring.md) — Monitoring and alerting
