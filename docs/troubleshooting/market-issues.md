# Market Service Issues

This guide covers market service problems including offer matching, trading engine issues, and cache problems.

## Offers Not Matching

**Symptoms:**

- GPU offers not matched with jobs
- Jobs remain unassigned
- Market not updating

**Diagnosis:**

```bash
# Check market status
curl http://localhost:8102/health

# Check offers
curl http://localhost:8102/v1/offers

# Check matching logs
journalctl -u aitbc-market -n 50
```

**Solutions:**

1. Check offer constraints

```bash
# Verify offer constraints
curl http://localhost:8102/v1/offers | jq '.[].constraints'
```

1. Restart matching engine

```bash
systemctl restart aitbc-market
```

1. Clear offer cache

```bash
# Clear Redis cache
redis-cli FLUSHALL

# Restart service
systemctl restart aitbc-market
```

## See Also

- [Coordinator Issues](coordinator-issues.md) - Job queueing and assignment issues
- [Database Issues](database-issues.md) - Database-related market issues
- [Service Management](service-management.md) - General service troubleshooting
