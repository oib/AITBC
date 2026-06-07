# AITBC Memory Configuration

**Date**: June 7, 2026
**Status**: ✅ Implemented
**Purpose**: Memory limits tuning and monitoring for AITBC services

## Overview

This document describes the memory configuration for all AITBC services, including memory limits, monitoring setup, and operational procedures. The configuration ensures optimal resource utilization and prevents out-of-memory (OOM) situations.

## Memory Limits Configuration

### High-Memory Services (>150MB)

| Service | Memory Limit | Current Usage | Usage % | Notes |
|---------|--------------|---------------|---------|-------|
| **aitbc-whisper.service** | 1GB | 587MB | 57% | ML model loaded (Whisper base) |
| **aitbc-coordinator-api.service** | 512MB | 202MB | 39% | Coordinator API with database |
| **aitbc-edge.service** | 512MB | 166MB | 32% | Edge API service |
| **aitbc-ffmpeg.service** | 512MB | 144MB | 28% | Video processing service |
| **aitbc-blockchain-node.service** | 2GB | 109MB | 5% | Blockchain node (high limit for growth) |

### Standard Services (256MB Limit)

All other services have been configured with a 256MB memory limit:

| Service | Current Usage | Usage % | Notes |
|---------|---------------|---------|-------|
| aitbc-agent-coordinator.service | 77MB | 30% | Agent coordination |
| aitbc-agent-daemon.service | 73MB | 28% | Agent daemon |
| aitbc-agent-management.service | 33MB | 12% | Agent management |
| aitbc-ai.service | 40MB | 15% | AI service |
| aitbc-api-gateway.service | 64MB | 25% | API gateway |
| aitbc-blockchain-event-bridge.service | 58MB | 22% | Event bridge |
| aitbc-blockchain-p2p.service | 74MB | 29% | P2P networking |
| aitbc-blockchain-rpc.service | 96MB | 37% | Blockchain RPC |
| aitbc-exchange.service | 53MB | 20% | Exchange service |
| aitbc-governance.service | 75MB | 29% | Governance service |
| aitbc-gpu.service | 74MB | 29% | GPU service |
| aitbc-hermes.service | 56MB | 22% | Hermes messaging |
| aitbc-learning.service | 87MB | 34% | Learning service |
| aitbc-marketplace.service | 81MB | 31% | Marketplace service |
| aitbc-miner.service | 52MB | 20% | Mining service |
| aitbc-modality-optimization.service | 77MB | 30% | Modality optimization |
| aitbc-monitoring.service | 37MB | 14% | Monitoring service |
| aitbc-multimodal.service | 77MB | 30% | Multimodal service |
| aitbc-plugin.service | 37MB | 14% | Plugin service |
| aitbc-trading.service | 76MB | 29% | Trading service |
| aitbc-wallet.service | 67MB | 26% | Wallet service |

## Memory Monitoring

### Automated Monitoring

**Service**: `aitbc-memory-monitor.timer`
**Frequency**: Every 5 minutes
**Script**: `/opt/aitbc/scripts/monitoring/memory-monitor.sh`
**Log File**: `/var/log/aitbc/memory-monitor.log`

### Monitoring Features

1. **Service Memory Monitoring**
   - Checks memory usage for all AITBC services
   - Compares current usage against configured limits
   - Alerts when usage exceeds 80% of limit
   - Warnings when usage exceeds 60% of limit

2. **System Memory Monitoring**
   - Monitors overall system memory usage
   - Alerts when system memory exceeds 90%
   - Tracks available memory

3. **OOM Killer Detection**
   - Checks kernel logs for OOM killer events
   - Alerts if OOM events are detected
   - Provides recent OOM event details

### Alert Thresholds

- **Critical**: Service usage > 80% of limit
- **Warning**: Service usage > 60% of limit
- **System Critical**: System memory > 90%

### Manual Monitoring

Run the memory monitor manually:
```bash
/opt/aitbc/scripts/monitoring/memory-monitor.sh
```

Check service memory usage:
```bash
systemctl show <service-name> -p MemoryCurrent -p MemoryMax -p MemoryLimit
```

Check all services:
```bash
for service in $(systemctl list-units --type=service --state=running | grep aitbc | awk '{print $1}'); do
    echo "=== $service ==="
    systemctl show $service -p MemoryCurrent -p MemoryMax -p MemoryLimit 2>/dev/null | grep -E "MemoryCurrent|MemoryMax|MemoryLimit"
done
```

## Memory Configuration Details

### Systemd Memory Directives

- **MemoryMax**: Hard memory limit (service will be killed if exceeded)
- **MemoryLimit**: Soft memory limit (service may be throttled if exceeded)

### Example Configuration

```ini
[Service]
# Memory limits
MemoryMax=256M
MemoryLimit=256M
```

### Modified Service Files

The following service files have been updated with memory limits:

**High-Memory Services:**
- `/etc/systemd/system/aitbc-whisper.service` (1GB)
- `/etc/systemd/system/aitbc-coordinator-api.service` (512MB)
- `/etc/systemd/system/aitbc-edge.service` (512MB)
- `/etc/systemd/system/aitbc-ffmpeg.service` (512MB)
- `/etc/systemd/system/aitbc-blockchain-rpc.service` (256MB)
- `/etc/systemd/system/aitbc-agent-coordinator.service` (256MB)

**Standard Services (256MB):**
- All other AITBC services

## Memory Usage Summary

### Current Status

- **Total Service Memory**: ~2.1GB
- **System Memory**: 8.3GB/16GB (52%)
- **Available Memory**: 7.7GB
- **Services Running**: 26/26 (100%)
- **Memory Alerts**: 0

### Memory Distribution

- **High-Memory Services**: 1.1GB (5 services)
- **Standard Services**: 1.0GB (21 services)
- **Total Configured Limits**: ~6.5GB
- **Headroom**: ~9.5GB (available for growth)

## Operational Procedures

### Adjusting Memory Limits

If a service consistently hits its memory limit:

1. **Monitor the service**:
   ```bash
   systemctl status <service-name>
   journalctl -u <service-name> -f
   ```

2. **Check current usage**:
   ```bash
   systemctl show <service-name> -p MemoryCurrent -p MemoryMax
   ```

3. **Edit the service file**:
   ```bash
   sudo nano /etc/systemd/system/<service-name>.service
   ```

4. **Update memory limits**:
   ```ini
   [Service]
   MemoryMax=<new-limit>
   MemoryLimit=<new-limit>
   ```

5. **Reload and restart**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart <service-name>
   ```

### Troubleshooting Memory Issues

**Service keeps hitting memory limit:**
- Increase the memory limit
- Check for memory leaks in the service
- Review service logs for errors

**System memory usage high:**
- Check which services are using the most memory
- Consider reducing memory limits for less critical services
- Add more system memory if needed

**OOM killer events detected:**
- Review OOM killer logs
- Identify which services were killed
- Increase memory limits for affected services
- Check for memory leaks

### Memory Monitoring Alerts

**Critical Alert (>80% usage):**
- Immediate action required
- Check service logs
- Consider increasing memory limit
- Monitor for stability

**Warning Alert (>60% usage):**
- Monitor service closely
- Plan for memory limit increase
- Check for unusual patterns

## Performance Impact

### Benefits

1. **Prevents OOM Situations**: Memory limits prevent services from consuming all available memory
2. **Better Resource Allocation**: Ensures fair distribution of memory across services
3. **Improved Stability**: Prevents cascading failures from memory exhaustion
4. **Proactive Monitoring**: Automated alerts for memory issues

### Considerations

1. **Service Restarts**: Services hitting memory limits will be killed and restarted
2. **Performance Throttling**: Soft limits may cause performance degradation
3. **Monitoring Overhead**: Memory monitoring script runs every 5 minutes (minimal impact)

## Future Improvements

### Planned Enhancements

1. **Dynamic Memory Limits**: Automatically adjust limits based on usage patterns
2. **Memory Profiling**: Identify memory leaks and optimization opportunities
3. **Load-Based Scaling**: Increase limits during high load periods
4. **Integration with Monitoring**: Add Prometheus metrics for memory usage
5. **Alert Integration**: Configure email/SMS alerts for critical memory events

### Optimization Opportunities

1. **Database Optimization**: Reduce memory usage through query optimization
2. **Caching Strategy**: Implement Redis to reduce database memory usage
3. **Service Consolidation**: Combine similar services to reduce overhead
4. **Memory Pooling**: Share memory resources across services

## Related Documentation

- [SERVICE_PORTS.md](../reference/SERVICE_PORTS.md) - Service port configuration
- [SECURITY_VULNERABILITIES_2026-06-07.md](../SECURITY_VULNERABILITIES_2026-06-07.md) - Security remediation
- [RELEASE_v0.4.13.md](../releases/RELEASE_v0.4.13.md) - Release notes with optimization roadmap

## Maintenance

### Regular Tasks

- **Weekly**: Review memory monitor logs for patterns
- **Monthly**: Adjust memory limits based on usage trends
- **Quarterly**: Review and optimize memory configuration

### Contact

For questions or issues related to memory configuration:
- **Documentation**: `/opt/aitbc/docs/operations/`
- **Logs**: `/var/log/aitbc/memory-monitor.log`
- **Service Logs**: `journalctl -u aitbc-*.service`

---

**Last Updated**: June 7, 2026
**Configuration Version**: 1.0
