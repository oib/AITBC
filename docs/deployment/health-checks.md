# Deployment Health Checks

This guide covers health checks and monitoring for AITBC deployment.

## Service Health Endpoints

```bash
# Check blockchain node health
curl http://localhost:8006/health

# Check coordinator API health
curl http://localhost:8203/health

# Check marketplace service health
curl http://localhost:8102/health

# Check wallet service health
curl http://localhost:8071/health
```

## Systemd Service Status

```bash
# Check all AITBC services
systemctl status aitbc-*

# Check specific service
systemctl status aitbc-blockchain

# Enable service auto-start
systemctl enable aitbc-blockchain
```

## Database Health

```bash
# Check PostgreSQL status
systemctl status postgresql

# Test database connection
psql -h localhost -U aitbc -d aitbc -c "SELECT 1;"

# Check Redis status
systemctl status redis-server

# Test Redis connection
redis-cli ping
```

## Monitoring Commands

```bash
# Check system resources
htop

# Check disk usage
df -h

# Check memory usage
free -h

# Check network connections
netstat -tulpn
```

## See Also

- [Troubleshooting/Service Management](../troubleshooting/service-management.md) - Service troubleshooting
- [Configuration](configuration.md) - Environment configuration
- [Deployment Troubleshooting](deployment-troubleshooting.md) - Common deployment issues
