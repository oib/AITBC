# Database Issues

This guide covers database problems including connection issues, slow queries, and database corruption.

## Connection Refused

**Symptoms:**
- Database connection errors
- Service unable to connect to PostgreSQL
- "Connection refused" messages

**Diagnosis:**
```bash
# Check PostgreSQL status
systemctl status postgresql

# Test connection
psql -h localhost -U aitbc -d aitbc

# Check PostgreSQL logs
tail -f /var/log/postgresql/postgresql-*.log
```

**Solutions:**
1. Restart PostgreSQL
```bash
systemctl restart postgresql
```

2. Check connection limits
```bash
# Check max connections
psql -d aitbc -c "SHOW max_connections;"

# Check active connections
psql -d aitbc -c "SELECT count(*) FROM pg_stat_activity;"
```

3. Check firewall
```bash
# Check if port 5432 is open
ufw status | grep 5432

# Allow PostgreSQL
ufw allow 5432/tcp
```

## Slow Queries

**Symptoms:**
- API responses slow
- Database CPU high
- Query timeouts

**Diagnosis:**
```bash
# Enable query logging
psql -d aitbc -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
systemctl reload postgresql

# Check slow queries
psql -d aitbc -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

**Solutions:**
1. Add indexes
```sql
-- Add index on frequently queried columns
CREATE INDEX idx_job_state ON job(state);
CREATE INDEX idx_job_created_at ON job(created_at);
```

2. Optimize queries
```sql
-- Use EXPLAIN ANALYZE
EXPLAIN ANALYZE SELECT * FROM job WHERE state = 'QUEUED';
```

3. Increase work_mem
```sql
-- Increase work_mem for complex queries
ALTER SYSTEM SET work_mem = '256MB';
systemctl reload postgresql
```

## Database Corruption

**Symptoms:**
- Data inconsistencies
- Queries return wrong results
- Database won't start

**Diagnosis:**
```bash
# Check database integrity
psql -d aitbc -c "VACUUM FULL ANALYZE;"

# Check for corruption
psql -d aitbc -c "SELECT * FROM pg_stat_database;"
```

**Solutions:**
1. Restore from backup
```bash
# Stop PostgreSQL
systemctl stop postgresql

# Restore from backup
psql -d aitbc < backup-20260511.sql

# Start PostgreSQL
systemctl start postgresql
```

2. Use WAL recovery
```bash
# Configure recovery
echo "restore_command = 'cp /var/lib/postgresql/wal/%f %p'" >> /etc/postgresql/*/main/recovery.conf

# Restart PostgreSQL
systemctl restart postgresql
```

## See Also

- [Coordinator Issues](coordinator-issues.md) - API database connectivity issues
- [Performance Issues](performance-issues.md) - Performance optimization
- [Service Management](service-management.md) - General service troubleshooting
