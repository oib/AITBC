# Marketplace Service Issues

This guide covers marketplace service problems including offer matching, trading engine issues, and cache problems.

## Offers Not Matching

**Symptoms:**
- GPU offers not matched with jobs
- Jobs remain unassigned
- Marketplace not updating

**Diagnosis:**
```bash
# Check marketplace status
curl http://localhost:8102/health

# Check offers
curl http://localhost:8102/v1/offers

# Check matching logs
journalctl -u aitbc-marketplace -n 50
```

**Solutions:**
1. Check offer constraints
```bash
# Verify offer constraints
curl http://localhost:8102/v1/offers | jq '.[].constraints'
```

2. Restart matching engine
```bash
systemctl restart aitbc-marketplace
```

3. Clear offer cache
```bash
# Clear Redis cache
redis-cli FLUSHALL

# Restart service
systemctl restart aitbc-marketplace
```

## See Also

- [Coordinator Issues](coordinator-issues.md) - Job queueing and assignment issues
- [Database Issues](database-issues.md) - Database-related marketplace issues
- [Service Management](service-management.md) - General service troubleshooting
