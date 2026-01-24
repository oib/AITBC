# Production Rollback Procedures

## Emergency Rollback Guide

Use these procedures when a deployment causes critical issues in production.

### Immediate Actions (First 5 minutes)

1. **Assess the Impact**
   - Check monitoring dashboards
   - Review error logs
   - Identify affected services
   - Determine if rollback is necessary

2. **Communicate**
   - Notify team in #production-alerts
   - Post status on status page if needed
   - Document start time of incident

### Automated Rollback (if available)

```bash
# Quick rollback to previous version
./scripts/rollback-to-previous.sh

# Rollback to specific version
./scripts/rollback-to-version.sh v1.2.3
```

### Manual Rollback Steps

#### 1. Stop Current Services
```bash
# Stop all AITBC services
sudo systemctl stop aitbc-coordinator
sudo systemctl stop aitbc-node
sudo systemctl stop aitbc-miner
sudo systemctl stop aitbc-dashboard
sudo docker-compose down
```

#### 2. Restore Previous Code
```bash
# Get previous deployment tag
git tag --sort=-version:refname | head -n 5

# Checkout previous stable version
git checkout v1.2.3

# Rebuild if necessary
docker-compose build --no-cache
```

#### 3. Restore Database (if needed)
```bash
# List available backups
aws s3 ls s3://aitbc-backups/database/

# Restore latest backup
pg_restore -h localhost -U postgres -d aitbc_prod latest_backup.dump
```

#### 4. Restore Configuration
```bash
# Restore from backup
cp /etc/aitbc/backup/config.yaml /etc/aitbc/config.yaml
cp /etc/aitbc/backup/.env /etc/aitbc/.env
```

#### 5. Restart Services
```bash
# Start services in correct order
sudo systemctl start aitbc-coordinator
sleep 10
sudo systemctl start aitbc-node
sleep 10
sudo systemctl start aitbc-miner
sleep 10
sudo systemctl start aitbc-dashboard
```

#### 6. Verify Rollback
```bash
# Check service status
./scripts/health-check.sh

# Run smoke tests
./scripts/smoke-test.sh

# Verify blockchain sync
curl -X POST http://localhost:8545 -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"eth_syncing","params":[],"id":1}'
```

### Database-Specific Rollbacks

#### Partial Data Rollback
```bash
# Create backup before changes
pg_dump -h localhost -U postgres aitbc_prod > pre-rollback-backup.sql

# Rollback specific tables
psql -h localhost -U postgres -d aitbc_prod < rollback-tables.sql
```

#### Migration Rollback
```bash
# Check migration status
./scripts/migration-status.sh

# Rollback last migration
./scripts/rollback-migration.sh
```

### Service-Specific Rollbacks

#### Coordinator Service
```bash
# Restore coordinator state
sudo systemctl stop aitbc-coordinator
cp /var/lib/aitbc/coordinator/backup/state.db /var/lib/aitbc/coordinator/
sudo systemctl start aitbc-coordinator
```

#### Blockchain Node
```bash
# Reset to last stable block
sudo systemctl stop aitbc-node
aitbc-node --reset-to-block 123456
sudo systemctl start aitbc-node
```

#### Mining Operations
```bash
# Stop mining immediately
curl -X POST http://localhost:8080/api/mining/stop

# Reset mining state
redis-cli FLUSHDB
```

### Verification Checklist

- [ ] All services running
- [ ] Database connectivity
- [ ] API endpoints responding
- [ ] Blockchain syncing
- [ ] Mining operations (if applicable)
- [ ] Dashboard accessible
- [ ] SSL certificates valid
- [ ] Monitoring alerts cleared

### Post-Rollback Actions

1. **Root Cause Analysis**
   - Document what went wrong
   - Identify failure point
   - Create prevention plan

2. **Team Communication**
   - Update incident ticket
   - Share lessons learned
   - Update runbooks

3. **Preventive Measures**
   - Add additional tests
   - Improve monitoring
   - Update deployment checklist

### Contact Information

- **On-call Engineer**: [Phone/Slack]
- **Engineering Lead**: [Phone/Slack]
- **DevOps Team**: #devops-alerts
- **Management**: #management-alerts

### Escalation

1. **Level 1**: On-call engineer (first 15 minutes)
2. **Level 2**: Engineering lead (after 15 minutes)
3. **Level 3**: CTO (after 30 minutes)

### Notes

- Always create a backup before rollback
- Document every step during rollback
- Test in staging before production if possible
- Keep stakeholders informed throughout process
