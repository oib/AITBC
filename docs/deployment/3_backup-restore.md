# AITBC Backup and Restore Procedures

**Last Updated:** 2026-05-28

This document outlines the backup and restore procedures for all AITBC system components including PostgreSQL, Redis, and blockchain ledger storage.

## Overview

The AITBC platform implements a comprehensive backup strategy with:
- **Automated daily backups** via Kubernetes CronJobs
- **Manual backup capabilities** for on-demand operations
- **Incremental and full backup options** for ledger data
- **Cloud storage integration** for off-site backups
- **Retention policies** to manage storage efficiently

## Components

### 1. PostgreSQL Database
- **Location**: Coordinator API persistent storage
- **Data**: Jobs, marketplace offers/bids, user sessions, configuration
- **Backup Format**: Custom PostgreSQL dump with compression
- **Retention**: 30 days (configurable)

### 2. Redis Cache
- **Location**: In-memory cache with persistence
- **Data**: Session cache, temporary data, rate limiting
- **Backup Format**: RDB snapshot + AOF (if enabled)
- **Retention**: 30 days (configurable)

### 3. Ledger Storage
- **Location**: Blockchain node persistent storage
- **Data**: Blocks, transactions, receipts, wallet states
- **Backup Format**: Compressed tar archives
- **Retention**: 30 days (configurable)

## Automated Backups

### Systemd Timer

The automated backup system runs daily at 2:00 AM UTC using systemd timers:

```bash
# Enable backup timer
systemctl enable aitbc-backup.timer
systemctl start aitbc-backup.timer

# Check timer status
systemctl status aitbc-backup.timer

# View backup logs
journalctl -u aitbc-backup.service -f
```

### Backup Schedule

| Time (UTC) | Component      | Type       | Retention |
|------------|----------------|------------|-----------|
| 02:00      | PostgreSQL     | Full       | 30 days   |
| 02:01      | Redis          | Full       | 30 days   |
| 02:02      | Ledger         | Full       | 30 days   |

## Manual Backups

### PostgreSQL

```bash
# Create a manual backup
./scripts/deployment/backup_postgresql.sh default my-backup-$(date +%Y%m%d)

# View available backups
ls -la /tmp/postgresql-backups/
```

### Redis

```bash
# Create a manual backup
./scripts/deployment/backup_redis.sh default my-redis-backup-$(date +%Y%m%d)

# Force background save before backup
systemctl redis-cli BGSAVE
```

### Ledger Storage

```bash
# Create a full backup
./scripts/deployment/backup_ledger.sh default my-ledger-backup-$(date +%Y%m%d)

# Create incremental backup
./scripts/deployment/backup_ledger.sh default incremental-backup-$(date +%Y%m%d) true
```

## Restore Procedures

### PostgreSQL Restore

```bash
# List available backups
ls -la /tmp/postgresql-backups/

# Restore database
./scripts/deployment/restore_postgresql.sh default /tmp/postgresql-backups/my-backup.sql.gz

# Verify restore
curl -s http://localhost:8011/v1/health
```

### Redis Restore

```bash
# Stop Redis service
systemctl stop redis

# Clear existing data
rm -f /var/lib/redis/dump.rdb /var/lib/redis/appendonly.aof

# Copy backup file
cp /tmp/redis-backup.rdb /var/lib/redis/dump.rdb

# Start Redis service
systemctl start redis

# Verify restore
redis-cli DBSIZE
```

### Ledger Restore

```bash
# Stop blockchain nodes
systemctl stop aitbc-blockchain-node

# Extract backup
tar -xzf /tmp/ledger-backup-20231222_020000.tar.gz -C /tmp/

# Copy ledger data
cp -r /tmp/chain/ /var/lib/aitbc/data/
cp -r /tmp/wallets/ /var/lib/aitbc/data/
cp -r /tmp/receipts/ /var/lib/aitbc/data/

# Start blockchain nodes
systemctl start aitbc-blockchain-node

# Verify restore
curl -s http://localhost:8006/rpc/head
```

## Disaster Recovery

### Recovery Time Objective (RTO)

| Component      | RTO Target | Notes                           |
|----------------|------------|---------------------------------|
| PostgreSQL     | 1 hour     | Database restore from backup     |
| Redis          | 15 minutes | Cache rebuild from backup       |
| Ledger         | 2 hours    | Full chain synchronization       |

### Recovery Point Objective (RPO)

| Component      | RPO Target | Notes                           |
|----------------|------------|---------------------------------|
| PostgreSQL     | 24 hours   | Daily backups                    |
| Redis          | 24 hours   | Daily backups                    |
| Ledger         | 24 hours   | Daily full + incremental backups|

### Disaster Recovery Steps

1. **Assess Impact**
   ```bash
   # Check component status
   systemctl status aitbc-*
   ```

2. **Restore Critical Services**
   ```bash
   # Restore PostgreSQL first (critical for operations)
   ./scripts/deployment/restore_postgresql.sh default [latest-backup]
   
   # Restore Redis cache
   ./restore_redis.sh default [latest-backup]
   
   # Restore ledger data
   ./restore_ledger.sh default [latest-backup]
   ```

3. **Verify System Health**
   ```bash
   # Check all services
   systemctl status aitbc-*
   
   # Verify API endpoints
   curl -s http://coordinator-api:8011/v1/health
   curl -s http://blockchain-node:8080/v1/health
   ```

## Monitoring and Alerting

### Backup Monitoring

Prometheus metrics track backup success/failure:

```yaml
# AlertManager rules for backups
- alert: BackupFailed
  expr: backup_success == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Backup failed for {{ $labels.component }}"
    description: "Backup for {{ $labels.component }} has failed for 5 minutes"
```

### Log Monitoring

```bash
# View backup logs
journalctl -u aitbc-backup.service -f

# Monitor backup timer
systemctl status aitbc-backup.timer
```

## Best Practices

### Backup Security

1. **Encryption**: Backups uploaded to S3 use server-side encryption
2. **Access Control**: IAM policies restrict backup access
3. **Retention**: Automatic cleanup of old backups
4. **Validation**: Regular restore testing

### Performance Considerations

1. **Off-Peak Backups**: Scheduled during low traffic (2 AM UTC)
2. **Parallel Processing**: Components backed up sequentially
3. **Compression**: All backups compressed to save storage
4. **Incremental Backups**: Ledger supports incremental to reduce size

### Testing

1. **Monthly Restore Tests**: Validate backup integrity
2. **Disaster Recovery Drills**: Quarterly full scenario testing
3. **Documentation Updates**: Keep procedures current

## Troubleshooting

### Common Issues

#### Backup Fails with "Permission Denied"
```bash
# Check service account permissions
systemctl status aitbc-backup.service
journalctl -u aitbc-backup.service -n 50
```

#### Restore Fails with "Database in Use"
```bash
# Scale down application before restore
systemctl stop coordinator-api
# Perform restore
# Scale up after restore
systemctl start coordinator-api
```

#### Ledger Restore Incomplete
```bash
# Verify backup integrity
tar -tzf ledger-backup.tar.gz
# Check metadata.json for block height
cat metadata.json | jq '.latest_block_height'
```

### Getting Help

1. Check logs: `journalctl -u aitbc-backup.service`
2. Verify storage: `df -h` on backup nodes
3. Check network: Test S3 connectivity
4. Review events: `journalctl -xe`

## Configuration

### Environment Variables

| Variable               | Default          | Description                     |
|------------------------|------------------|---------------------------------|
| BACKUP_RETENTION_DAYS  | 30               | Days to keep backups            |
| BACKUP_SCHEDULE        | 0 2 * * *        | Cron schedule for backups       |
| S3_BUCKET_PREFIX       | aitbc-backups    | S3 bucket name prefix           |
| COMPRESSION_LEVEL      | 6                | gzip compression level          |

### Customizing Backup Schedule

Edit the systemd timer configuration:

```bash
# Edit the timer unit
systemctl edit aitbc-backup.timer

# Change the schedule (e.g., to 3 AM UTC)
# OnCalendar=*-*-* 03:00:00

# Reload systemd
systemctl daemon-reload
systemctl restart aitbc-backup.timer
```

### Adjusting Retention

Modify retention in each backup script:

```bash
# In backup_*.sh scripts
RETENTION_DAYS=60  # Keep for 60 days instead of 30
```
