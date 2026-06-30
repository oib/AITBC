# Agent Coordinator - Scaling

**Last Updated**: 2026-06-30
**Version**: 1.0

## Horizontal Scaling

### Multiple Coordinator Instances

1. Deploy multiple coordinator instances behind load balancer
2. Use shared Redis instance
3. Configure consistent PYTHONPATH across instances

### Load Balancer Configuration

```nginx
upstream coordinator {
    server localhost:9001;
    server localhost:9002;
    server localhost:9003;
}

server {
    listen 80;
    location / {
        proxy_pass http://coordinator;
    }
}
```

## Redis Clustering

### For High Availability

- Use Redis Sentinel for failover
- Use Redis Cluster for sharding
- Configure coordinator to use Redis Sentinel

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Backup and Recovery](./operator-backup.md) - Redis backup and service configuration backup
- [Security](./operator-security.md) - Network security and authentication
