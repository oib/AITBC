# AITBC Incident Runbooks

**Last Updated:** 2026-05-28

This document contains specific runbooks for common incident scenarios, based on our chaos testing validation and integration test suite.

## Integration Test Status (Updated 2026-01-26)

### Current Test Coverage
- ✅ 6 integration tests passing
- ✅ Security tests using real ZK proof features
- ✅ Marketplace tests connecting to live service
- ⏸️ 1 test skipped (wallet payment flow)

### Test Environment
- Tests run against both real and mock clients
- CI/CD pipeline runs full test suite
- Local development: `python -m pytest tests/integration/ -v`

## Runbook: Coordinator API Outage

### Based on Chaos Test: `chaos_test_coordinator.py`

### Symptoms
- 503/504 errors on all endpoints
- Health check failures
- Job submission failures
- Marketplace unresponsive

### MTTR Target: 2 minutes

### Immediate Actions (0-2 minutes)
```bash
# 1. Check service status
systemctl status aitbc-coordinator-api

# 2. Check recent logs
journalctl -u aitbc-coordinator-api -n 50 --no-pager

# 3. Check if service is crashlooping
systemctl status aitbc-coordinator-api | grep -i "failed\|crash"

# 4. Quick restart if needed
systemctl restart aitbc-coordinator-api
```

### Investigation (2-10 minutes)
1. **Review Logs**
   ```bash
   journalctl -u aitbc-coordinator-api -f
   ```

2. **Check Resource Usage**
   ```bash
   top -p $(pgrep -f coordinator-api)
   ```

3. **Verify Database Connectivity**
   ```bash
   psql -U aitbc -d aitbc_coordinator -c "SELECT 1;"
   ```

4. **Check Redis Connection**
   ```bash
   redis-cli -h localhost ping
   ```

### Recovery Actions
1. **Scale Up if Resource Starved**
   ```bash
   # For systemd, check resource limits in service file
   systemctl edit aitbc-coordinator-api
   ```

2. **Force Restart if Stuck**
   ```bash
   systemctl stop aitbc-coordinator-api
   systemctl start aitbc-coordinator-api
   ```

3. **Rollback Deployment**
   ```bash
   cd /opt/aitbc
   git checkout <previous-commit>
   systemctl restart aitbc-coordinator-api
   ```

### Verification
```bash
# Test health endpoint
curl -f http://localhost:8203/v1/health

# Test API with sample request
curl -X GET http://localhost:8203/v1/jobs -H "X-API-Key: test-key"
```

## Runbook: Network Partition

### Based on Chaos Test: `chaos_test_network.py`

### Symptoms
- Blockchain nodes not communicating
- Consensus stalled
- High finality latency
- Transaction processing delays

### MTTR Target: 5 minutes

### Immediate Actions (0-5 minutes)
```bash
# 1. Check peer connectivity
curl -s http://localhost:8202/rpc/peers | jq

# 2. Check consensus status
curl -s http://localhost:8202/rpc/consensus | jq

# 3. Check network connectivity
ping -c 3 <peer-node-ip>
```

### Investigation (5-15 minutes)
1. **Identify Partitioned Nodes**
   ```bash
   # Check each node's peer count
   for node in aitbc1 aitbc2 aitbc3; do
     echo "Node: $node"
     ssh $node "curl -s http://localhost:8202/rpc/peers | jq '. | length'"
   done
   ```

2. **Check Firewall Rules**
   ```bash
   iptables -L -n
   ufw status
   ```

3. **Verify DNS Resolution**
   ```bash
   nslookup blockchain-node
   ```

### Recovery Actions
1. **Remove Problematic Network Rules**
   ```bash
   # Flush iptables on affected nodes
   iptables -F
   iptables -X
   ```

2. **Restart Network Components**
   ```bash
   systemctl restart aitbc-blockchain-p2p
   ```

3. **Force Re-peering**
   ```bash
   # Restart blockchain nodes to force re-peering
   systemctl restart aitbc-blockchain-node
   ```

### Verification
```bash
# Wait for consensus to resume
watch -n 5 'curl -s http://localhost:8202/rpc/consensus | jq .height'

# Verify peer connectivity
curl -s http://localhost:8202/rpc/peers | jq '. | length'
```

## Runbook: Database Failure

### Based on Chaos Test: `chaos_test_database.py`

### Symptoms
- Database connection errors
- Service degradation
- Failed transactions
- High error rates

### MTTR Target: 3 minutes

### Immediate Actions (0-3 minutes)
```bash
# 1. Check PostgreSQL status
systemctl status postgresql

# 2. Check connection count
-u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# 3. Check replica lag (if using replication)
-u postgres psql -c "SELECT pg_last_xact_replay_timestamp();"
```

### Investigation (3-10 minutes)
1. **Review Database Logs**
   ```bash
   tail -100 /var/log/postgresql/postgresql-*.log
   ```

2. **Check Resource Usage**
   ```bash
   df -h /var/lib/postgresql/data
   top -p $(pgrep postgres)
   ```

3. **Identify Long-running Queries**
   ```bash
   -u postgres psql -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 minutes';"
   ```

### Recovery Actions
1. **Kill Idle Connections**
   ```bash
   -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '1 hour';"
   ```

2. **Restart PostgreSQL**
   ```bash
   systemctl restart postgresql
   ```

3. **Failover to Replica**
   ```bash
   # Promote replica if primary fails
   -u postgres pg_ctl promote -D /var/lib/postgresql/data
   ```

### Verification
```bash
# Test database connectivity
psql -U aitbc -d aitbc_coordinator -c "SELECT 1;"

# Check application health
curl -f http://localhost:8203/v1/health
```

## Runbook: Redis Failure

### Symptoms
- Caching failures
- Session loss
- Increased database load
- Slow response times

### MTTR Target: 2 minutes

### Immediate Actions (0-2 minutes)
```bash
# 1. Check Redis status
systemctl status redis

# 2. Check memory usage
redis-cli info memory | grep used_memory_human

# 3. Check connection count
redis-cli info clients | grep connected_clients
```

### Investigation (2-5 minutes)
1. **Review Redis Logs**
   ```bash
   tail -100 /var/log/redis/redis-server.log
   ```

2. **Check for Eviction**
   ```bash
   redis-cli info stats | grep evicted_keys
   ```

3. **Identify Large Keys**
   ```bash
   redis-cli --bigkeys
   ```

### Recovery Actions
1. **Clear Expired Keys**
   ```bash
   redis-cli --scan --pattern "*:*" | xargs redis-cli del
   ```

2. **Restart Redis**
   ```bash
   systemctl restart redis
   ```

3. **Scale Redis Cluster**
   ```bash
   # For systemd, check Redis configuration
   systemctl edit redis
   ```

### Verification
```bash
# Test Redis connectivity
redis-cli ping

# Check application performance
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8203/v1/health
```

## Runbook: High CPU/Memory Usage

### Symptoms
- Slow response times
- Service crashes
- OOM errors
- System degradation

### MTTR Target: 5 minutes

### Immediate Actions (0-5 minutes)
```bash
# 1. Check resource usage
top
htop

# 2. Identify resource-hungry processes
ps aux --sort=-%cpu | head -10
ps aux --sort=-%mem | head -10

# 3. Check for OOM kills
dmesg | grep -i "killed process"
```

### Investigation (5-15 minutes)
1. **Analyze Resource Usage**
   ```bash
   # Detailed process metrics
   top -p $(pgrep -f coordinator-api)
   ```

2. **Check Resource Limits**
   ```bash
   # Check systemd service limits
   systemctl show aitbc-coordinator-api | grep -i "limit"
   ```

3. **Review Application Metrics**
   ```bash
   # Check Prometheus metrics
   curl http://localhost:8203/metrics | grep -E "(cpu|memory)"
   ```

### Recovery Actions
1. **Restart Affected Services**
   ```bash
   systemctl restart aitbc-coordinator-api
   systemctl restart aitbc-blockchain-node
   ```

2. **Increase Resource Limits**
   ```bash
   # Edit service resource limits
   systemctl edit aitbc-coordinator-api
   ```

3. **Optimize Application**
   ```bash
   # Check for memory leaks
   # Review application logs for patterns
   ```

### Verification
```bash
# Monitor resource usage
watch -n 5 'top -b -n 1 | head -20'

# Test service performance
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8203/v1/health
```

## Runbook: Storage Issues

### Symptoms
- Disk space warnings
- Write failures
- Database errors
- Service crashes

### MTTR Target: 10 minutes

### Immediate Actions (0-10 minutes)
```bash
# 1. Check disk usage
df -h

# 2. Identify large files
find /var/log -name "*.log" -size +100M
find /var/lib/postgresql -type f -size +1G

# 3. Clean up logs
journalctl --vacuum-time=7d
```

### Investigation (10-20 minutes)
1. **Analyze Storage Usage**
   ```bash
   du -sh /var/log/*
   du -sh /var/lib/postgresql/*
   ```

2. **Check Database Size**
   ```bash
   -u postgres psql -c "SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;"
   ```

3. **Review Retention Policies**
   ```bash
   # Check log rotation configuration
   logrotate -d /etc/logrotate.conf
   ```

### Recovery Actions
1. **Expand Storage**
   ```bash
   # Add disk space or mount additional storage
   # Update fstab if needed
   ```

2. **Force Cleanup**
   ```bash
   # Clean old logs
   find /var/log -name "*.log" -mtime +7 -delete

   # Clean old backups
   find /var/backups -mtime +30 -delete
   ```

3. **Restart Services**
   ```bash
   systemctl restart postgresql
   ```

### Verification
```bash
# Check disk space
df -h

# Verify database operations
-u postgres psql -c "SELECT 1;"
```

## Emergency Contact Procedures

### Escalation Matrix
1. **Level 1**: On-call engineer (5 minutes)
2. **Level 2**: On-call secondary (15 minutes)
3. **Level 3**: Engineering manager (30 minutes)
4. **Level 4**: CTO (1 hour, critical only)

### War Room Activation
```bash
# Create communication channel
# Invite stakeholders
# Start meeting
```

### Customer Communication
1. **Status Page Update** (5 minutes)
2. **Email Notification** (15 minutes)
3. **Twitter Update** (30 minutes, critical only)

## Post-Incident Checklist

### Immediate (0-1 hour)
- [ ] Service fully restored
- [ ] Monitoring normal
- [ ] Status page updated
- [ ] Stakeholders notified

### Short-term (1-24 hours)
- [ ] Incident document created
- [ ] Root cause identified
- [ ] Runbooks updated
- [ ] Post-mortem scheduled

### Long-term (1-7 days)
- [ ] Post-mortem completed
- [ ] Action items assigned
- [ ] Monitoring improved
- [ ] Process updated

## Runbook Maintenance

### Review Schedule
- **Monthly**: Review and update runbooks
- **Quarterly**: Full review and testing
- **Annually**: Major revision

### Update Process
1. Test runbook procedures
2. Document lessons learned
3. Update procedures
4. Train team members
5. Update documentation

---

*Version: 1.0*
*Last Updated: 2024-12-22*
*Owner: SRE Team*
