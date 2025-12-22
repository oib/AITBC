# AITBC Incident Runbooks

This document contains specific runbooks for common incident scenarios, based on our chaos testing validation.

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
# 1. Check pod status
kubectl get pods -n default -l app.kubernetes.io/name=coordinator

# 2. Check recent events
kubectl get events -n default --sort-by=.metadata.creationTimestamp | tail -20

# 3. Check if pods are crashlooping
kubectl describe pod -n default -l app.kubernetes.io/name=coordinator

# 4. Quick restart if needed
kubectl rollout restart deployment/coordinator -n default
```

### Investigation (2-10 minutes)
1. **Review Logs**
   ```bash
   kubectl logs -n default deployment/coordinator --tail=100
   ```

2. **Check Resource Limits**
   ```bash
   kubectl top pods -n default -l app.kubernetes.io/name=coordinator
   ```

3. **Verify Database Connectivity**
   ```bash
   kubectl exec -n default deployment/coordinator -- nc -z postgresql 5432
   ```

4. **Check Redis Connection**
   ```bash
   kubectl exec -n default deployment/coordinator -- redis-cli -h redis ping
   ```

### Recovery Actions
1. **Scale Up if Resource Starved**
   ```bash
   kubectl scale deployment/coordinator --replicas=5 -n default
   ```

2. **Manual Pod Deletion if Stuck**
   ```bash
   kubectl delete pods -n default -l app.kubernetes.io/name=coordinator --force --grace-period=0
   ```

3. **Rollback Deployment**
   ```bash
   kubectl rollout undo deployment/coordinator -n default
   ```

### Verification
```bash
# Test health endpoint
curl -f http://127.0.0.2:8011/v1/health

# Test API with sample request
curl -X GET http://127.0.0.2:8011/v1/jobs -H "X-API-Key: test-key"
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
kubectl exec -n default deployment/blockchain-node -- curl -s http://localhost:8080/v1/peers | jq

# 2. Check consensus status
kubectl exec -n default deployment/blockchain-node -- curl -s http://localhost:8080/v1/consensus | jq

# 3. Check network policies
kubectl get networkpolicies -n default
```

### Investigation (5-15 minutes)
1. **Identify Partitioned Nodes**
   ```bash
   # Check each node's peer count
   for pod in $(kubectl get pods -n default -l app.kubernetes.io/name=blockchain-node -o jsonpath='{.items[*].metadata.name}'); do
     echo "Pod: $pod"
     kubectl exec -n default $pod -- curl -s http://localhost:8080/v1/peers | jq '. | length'
   done
   ```

2. **Check Network Policies**
   ```bash
   kubectl describe networkpolicy default-deny-all-ingress -n default
   kubectl describe networkpolicy blockchain-node-netpol -n default
   ```

3. **Verify DNS Resolution**
   ```bash
   kubectl exec -n default deployment/blockchain-node -- nslookup blockchain-node
   ```

### Recovery Actions
1. **Remove Problematic Network Rules**
   ```bash
   # Flush iptables on affected nodes
   for pod in $(kubectl get pods -n default -l app.kubernetes.io/name=blockchain-node -o jsonpath='{.items[*].metadata.name}'); do
     kubectl exec -n default $pod -- iptables -F
   done
   ```

2. **Restart Network Components**
   ```bash
   kubectl rollout restart deployment/blockchain-node -n default
   ```

3. **Force Re-peering**
   ```bash
   # Delete and recreate pods to force re-peering
   kubectl delete pods -n default -l app.kubernetes.io/name=blockchain-node
   ```

### Verification
```bash
# Wait for consensus to resume
watch -n 5 'kubectl exec -n default deployment/blockchain-node -- curl -s http://localhost:8080/v1/consensus | jq .height'

# Verify peer connectivity
kubectl exec -n default deployment/blockchain-node -- curl -s http://localhost:8080/v1/peers | jq '. | length'
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
kubectl exec -n default deployment/postgresql -- pg_isready

# 2. Check connection count
kubectl exec -n default deployment/postgresql -- psql -U aitbc -c "SELECT count(*) FROM pg_stat_activity;"

# 3. Check replica lag
kubectl exec -n default deployment/postgresql-replica -- psql -U aitbc -c "SELECT pg_last_xact_replay_timestamp();"
```

### Investigation (3-10 minutes)
1. **Review Database Logs**
   ```bash
   kubectl logs -n default deployment/postgresql --tail=100
   ```

2. **Check Resource Usage**
   ```bash
   kubectl top pods -n default -l app.kubernetes.io/name=postgresql
   df -h /var/lib/postgresql/data
   ```

3. **Identify Long-running Queries**
   ```bash
   kubectl exec -n default deployment/postgresql -- psql -U aitbc -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 minutes';"
   ```

### Recovery Actions
1. **Kill Idle Connections**
   ```bash
   kubectl exec -n default deployment/postgresql -- psql -U aitbc -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '1 hour';"
   ```

2. **Restart PostgreSQL**
   ```bash
   kubectl rollout restart deployment/postgresql -n default
   ```

3. **Failover to Replica**
   ```bash
   # Promote replica if primary fails
   kubectl exec -n default deployment/postgresql-replica -- pg_ctl promote -D /var/lib/postgresql/data
   ```

### Verification
```bash
# Test database connectivity
kubectl exec -n default deployment/coordinator -- python -c "import psycopg2; conn = psycopg2.connect('postgresql://aitbc:password@postgresql:5432/aitbc'); print('Connected')"

# Check application health
curl -f http://127.0.0.2:8011/v1/health
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
kubectl exec -n default deployment/redis -- redis-cli ping

# 2. Check memory usage
kubectl exec -n default deployment/redis -- redis-cli info memory | grep used_memory_human

# 3. Check connection count
kubectl exec -n default deployment/redis -- redis-cli info clients | grep connected_clients
```

### Investigation (2-5 minutes)
1. **Review Redis Logs**
   ```bash
   kubectl logs -n default deployment/redis --tail=100
   ```

2. **Check for Eviction**
   ```bash
   kubectl exec -n default deployment/redis -- redis-cli info stats | grep evicted_keys
   ```

3. **Identify Large Keys**
   ```bash
   kubectl exec -n default deployment/redis -- redis-cli --bigkeys
   ```

### Recovery Actions
1. **Clear Expired Keys**
   ```bash
   kubectl exec -n default deployment/redis -- redis-cli --scan --pattern "*:*" | xargs redis-cli del
   ```

2. **Restart Redis**
   ```bash
   kubectl rollout restart deployment/redis -n default
   ```

3. **Scale Redis Cluster**
   ```bash
   kubectl scale deployment/redis --replicas=3 -n default
   ```

### Verification
```bash
# Test Redis connectivity
kubectl exec -n default deployment/coordinator -- redis-cli -h redis ping

# Check application performance
curl -w "@curl-format.txt" -o /dev/null -s http://127.0.0.2:8011/v1/health
```

## Runbook: High CPU/Memory Usage

### Symptoms
- Slow response times
- Pod evictions
- OOM errors
- System degradation

### MTTR Target: 5 minutes

### Immediate Actions (0-5 minutes)
```bash
# 1. Check resource usage
kubectl top pods -n default
kubectl top nodes

# 2. Identify resource-hungry pods
kubectl exec -n default deployment/coordinator -- top

# 3. Check for OOM kills
dmesg | grep -i "killed process"
```

### Investigation (5-15 minutes)
1. **Analyze Resource Usage**
   ```bash
   # Detailed pod metrics
   kubectl exec -n default deployment/coordinator -- ps aux --sort=-%cpu | head -10
   kubectl exec -n default deployment/coordinator -- ps aux --sort=-%mem | head -10
   ```

2. **Check Resource Limits**
   ```bash
   kubectl describe pod -n default -l app.kubernetes.io/name=coordinator | grep -A 10 Limits
   ```

3. **Review Application Metrics**
   ```bash
   # Check Prometheus metrics
   curl http://127.0.0.2:8011/metrics | grep -E "(cpu|memory)"
   ```

### Recovery Actions
1. **Scale Services**
   ```bash
   kubectl scale deployment/coordinator --replicas=5 -n default
   kubectl scale deployment/blockchain-node --replicas=3 -n default
   ```

2. **Increase Resource Limits**
   ```bash
   kubectl patch deployment coordinator -p '{"spec":{"template":{"spec":{"containers":[{"name":"coordinator","resources":{"limits":{"cpu":"2000m","memory":"4Gi"}}}]}}}}'
   ```

3. **Restart Affected Services**
   ```bash
   kubectl rollout restart deployment/coordinator -n default
   ```

### Verification
```bash
# Monitor resource usage
watch -n 5 'kubectl top pods -n default'

# Test service performance
curl -w "@curl-format.txt" -o /dev/null -s http://127.0.0.2:8011/v1/health
```

## Runbook: Storage Issues

### Symptoms
- Disk space warnings
- Write failures
- Database errors
- Pod crashes

### MTTR Target: 10 minutes

### Immediate Actions (0-10 minutes)
```bash
# 1. Check disk usage
df -h
kubectl exec -n default deployment/postgresql -- df -h

# 2. Identify large files
find /var/log -name "*.log" -size +100M
kubectl exec -n default deployment/postgresql -- find /var/lib/postgresql -type f -size +1G

# 3. Clean up logs
kubectl logs -n default deployment/coordinator --tail=1000 > /tmp/coordinator.log && truncate -s 0 /var/log/containers/coordinator*.log
```

### Investigation (10-20 minutes)
1. **Analyze Storage Usage**
   ```bash
   du -sh /var/log/*
   du -sh /var/lib/docker/*
   ```

2. **Check PVC Usage**
   ```bash
   kubectl get pvc -n default
   kubectl describe pvc postgresql-data -n default
   ```

3. **Review Retention Policies**
   ```bash
   kubectl get cronjobs -n default
   kubectl describe cronjob log-cleanup -n default
   ```

### Recovery Actions
1. **Expand Storage**
   ```bash
   kubectl patch pvc postgresql-data -p '{"spec":{"resources":{"requests":{"storage":"100Gi"}}}}'
   ```

2. **Force Cleanup**
   ```bash
   # Clean old logs
   find /var/log -name "*.log" -mtime +7 -delete
   
   # Clean Docker images
   docker system prune -a
   ```

3. **Restart Services**
   ```bash
   kubectl rollout restart deployment/postgresql -n default
   ```

### Verification
```bash
# Check disk space
df -h

# Verify database operations
kubectl exec -n default deployment/postgresql -- psql -U aitbc -c "SELECT 1;"
```

## Emergency Contact Procedures

### Escalation Matrix
1. **Level 1**: On-call engineer (5 minutes)
2. **Level 2**: On-call secondary (15 minutes)
3. **Level 3**: Engineering manager (30 minutes)
4. **Level 4**: CTO (1 hour, critical only)

### War Room Activation
```bash
# Create Slack channel
/slack create-channel #incident-$(date +%Y%m%d-%H%M%S)

# Invite stakeholders
/slack invite @sre-team @engineering-manager @cto

# Start Zoom meeting
/zoom start "AITBC Incident War Room"
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
