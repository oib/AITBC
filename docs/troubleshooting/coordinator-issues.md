# Coordinator API Issues

This guide covers Coordinator API problems including 500 errors, job queueing issues, and database connectivity.

## 500 Internal Server Error

**Symptoms:**
- API returns 500 errors
- Jobs fail to submit
- Status checks fail

**Diagnosis:**
```bash
# Check API logs
journalctl -u aitbc-coordinator-api -n 100 | grep -i error

# Check database connection
psql -d aitbc -c "SELECT 1;"

# Check health endpoint
curl http://localhost:8203/health
```

**Solutions:**
1. Check database connectivity
```bash
# Test database connection
psql -h localhost -U aitbc -d aitbc

# Restart PostgreSQL
systemctl restart postgresql
```

2. Check Redis connection
```bash
# Test Redis
redis-cli ping

# Restart Redis
systemctl restart redis
```

3. Check datetime handling
```bash
# Check for datetime comparison errors
# Ensure all datetimes are timezone-aware or offset-naive consistently
```

## Job Stuck in Queued State

**Symptoms:**
- Jobs remain in QUEUED state
- No miners assigned
- Job expiration

**Diagnosis:**
```bash
# Check job status
curl -H "X-Api-Key: $API_KEY" \
  http://localhost:8203/v1/jobs/{job_id}

# Check miner availability
curl http://localhost:8203/v1/miners

# Check logs
journalctl -u aitbc-coordinator-api -n 50
```

**Solutions:**
1. Check miner registration
```bash
# Verify miners are registered
curl http://localhost:8203/v1/miners

# Register miner if needed
curl -X POST http://localhost:8203/v1/miners/register \
  -H "Content-Type: application/json" \
  -d '{"miner_id": "miner-123", "gpu_type": "nvidia-rtx-3090"}'
```

2. Check job constraints
```bash
# Verify job constraints can be satisfied
curl -H "X-Api-Key: $API_KEY" \
  http://localhost:8203/v1/jobs/{job_id} | jq '.constraints'
```

3. Increase job TTL
```bash
# Resubmit with longer TTL
curl -X POST http://localhost:8203/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"payload": {...}, "ttl_seconds": 3600}'
```

## See Also

- [Database Issues](database-issues.md) - Database connection and performance issues
- [Service Management](service-management.md) - General service troubleshooting
- [Marketplace Issues](marketplace-issues.md) - Marketplace matching problems
