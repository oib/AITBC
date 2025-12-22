# AITBC Backup and Restore Procedures

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

### Kubernetes CronJob

The automated backup system runs daily at 2:00 AM UTC:

```bash
# Deploy the backup CronJob
kubectl apply -f infra/k8s/backup-cronjob.yaml

# Check CronJob status
kubectl get cronjob aitbc-backup

# View backup jobs
kubectl get jobs -l app=aitbc-backup

# View backup logs
kubectl logs job/aitbc-backup-<timestamp>
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
./infra/scripts/backup_postgresql.sh default my-backup-$(date +%Y%m%d)

# View available backups
ls -la /tmp/postgresql-backups/

# Upload to S3 manually
aws s3 cp /tmp/postgresql-backups/my-backup.sql.gz s3://aitbc-backups-default/postgresql/
```

### Redis

```bash
# Create a manual backup
./infra/scripts/backup_redis.sh default my-redis-backup-$(date +%Y%m%d)

# Force background save before backup
kubectl exec -n default deployment/redis -- redis-cli BGSAVE
```

### Ledger Storage

```bash
# Create a full backup
./infra/scripts/backup_ledger.sh default my-ledger-backup-$(date +%Y%m%d)

# Create incremental backup
./infra/scripts/backup_ledger.sh default incremental-backup-$(date +%Y%m%d) true
```

## Restore Procedures

### PostgreSQL Restore

```bash
# List available backups
aws s3 ls s3://aitbc-backups-default/postgresql/

# Download backup from S3
aws s3 cp s3://aitbc-backups-default/postgresql/postgresql-backup-20231222_020000.sql.gz /tmp/

# Restore database
./infra/scripts/restore_postgresql.sh default /tmp/postgresql-backup-20231222_020000.sql.gz

# Verify restore
kubectl exec -n default deployment/coordinator-api -- curl -s http://localhost:8011/v1/health
```

### Redis Restore

```bash
# Stop Redis service
kubectl scale deployment redis --replicas=0 -n default

# Clear existing data
kubectl exec -n default deployment/redis -- rm -f /data/dump.rdb /data/appendonly.aof

# Copy backup file
kubectl cp /tmp/redis-backup.rdb default/redis-0:/data/dump.rdb

# Start Redis service
kubectl scale deployment redis --replicas=1 -n default

# Verify restore
kubectl exec -n default deployment/redis -- redis-cli DBSIZE
```

### Ledger Restore

```bash
# Stop blockchain nodes
kubectl scale deployment blockchain-node --replicas=0 -n default

# Extract backup
tar -xzf /tmp/ledger-backup-20231222_020000.tar.gz -C /tmp/

# Copy ledger data
kubectl cp /tmp/chain/ default/blockchain-node-0:/app/data/chain/
kubectl cp /tmp/wallets/ default/blockchain-node-0:/app/data/wallets/
kubectl cp /tmp/receipts/ default/blockchain-node-0:/app/data/receipts/

# Start blockchain nodes
kubectl scale deployment blockchain-node --replicas=3 -n default

# Verify restore
kubectl exec -n default deployment/blockchain-node -- curl -s http://localhost:8080/v1/blocks/head
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
   kubectl get pods -n default
   kubectl get events --sort-by=.metadata.creationTimestamp
   ```

2. **Restore Critical Services**
   ```bash
   # Restore PostgreSQL first (critical for operations)
   ./infra/scripts/restore_postgresql.sh default [latest-backup]
   
   # Restore Redis cache
   ./restore_redis.sh default [latest-backup]
   
   # Restore ledger data
   ./restore_ledger.sh default [latest-backup]
   ```

3. **Verify System Health**
   ```bash
   # Check all services
   kubectl get pods -n default
   
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
kubectl logs -l app=aitbc-backup -n default --tail=100

# Monitor backup CronJob
kubectl get cronjob aitbc-backup -w
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
kubectl describe serviceaccount backup-service-account
kubectl describe role backup-role
```

#### Restore Fails with "Database in Use"
```bash
# Scale down application before restore
kubectl scale deployment coordinator-api --replicas=0
# Perform restore
# Scale up after restore
kubectl scale deployment coordinator-api --replicas=3
```

#### Ledger Restore Incomplete
```bash
# Verify backup integrity
tar -tzf ledger-backup.tar.gz
# Check metadata.json for block height
cat metadata.json | jq '.latest_block_height'
```

### Getting Help

1. Check logs: `kubectl logs -l app=aitbc-backup`
2. Verify storage: `df -h` on backup nodes
3. Check network: Test S3 connectivity
4. Review events: `kubectl get events --sort-by=.metadata.creationTimestamp`

## Configuration

### Environment Variables

| Variable               | Default          | Description                     |
|------------------------|------------------|---------------------------------|
| BACKUP_RETENTION_DAYS  | 30               | Days to keep backups            |
| BACKUP_SCHEDULE        | 0 2 * * *        | Cron schedule for backups       |
| S3_BUCKET_PREFIX       | aitbc-backups    | S3 bucket name prefix           |
| COMPRESSION_LEVEL      | 6                | gzip compression level          |

### Customizing Backup Schedule

Edit the CronJob schedule in `infra/k8s/backup-cronjob.yaml`:

```yaml
spec:
  schedule: "0 3 * * *"  # Change to 3 AM UTC
```

### Adjusting Retention

Modify retention in each backup script:

```bash
# In backup_*.sh scripts
RETENTION_DAYS=60  # Keep for 60 days instead of 30
```
