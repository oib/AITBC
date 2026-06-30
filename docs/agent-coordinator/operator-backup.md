# Agent Coordinator - Backup and Recovery

**Last Updated**: 2026-06-30
**Version**: 1.0

## Redis Backup

### Manual Backup

```bash
redis-cli SAVE
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d).rdb
```

### Automated Backup

```bash
#!/bin/bash
# backup_redis.sh
redis-cli BGSAVE
sleep 5
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d-%H%M%S).rdb
# Keep last 7 days
find /backup -name "redis-*.rdb" -mtime +7 -delete
```

### Restore from Backup

```bash
systemctl stop redis
cp /backup/redis-20260507.rdb /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb
systemctl start redis
```

## Service Configuration Backup

### Backup Service File

```bash
cp /etc/systemd/system/aitbc-agent-coordinator.service /backup/
```

### Backup Environment

```bash
cp /etc/aitbc/.env /backup/
```

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Maintenance](./operator-maintenance.md) - Regular maintenance tasks
- [Scaling](./operator-scaling.md) - Horizontal scaling and Redis clustering
