# Deployment Troubleshooting

This guide covers common deployment issues and their solutions.

## Service Won't Start

**Symptoms:**
- Services fail to start
- Systemd shows "failed" status

**Solutions:**
```bash
# Check service logs
journalctl -u aitbc-blockchain -n 50

# Check configuration
systemctl status aitbc-blockchain

# Restart service
systemctl restart aitbc-blockchain
```

## Database Connection Issues

**Symptoms:**
- Services cannot connect to database
- Connection refused errors

**Solutions:**
```bash
# Check PostgreSQL status
systemctl status postgresql

# Test connection
psql -h localhost -U aitbc -d aitbc

# Check firewall
ufw status | grep 5432
```

## Port Conflicts

**Symptoms:**
- Services fail to bind to ports
- Address already in use errors

**Solutions:**
```bash
# Check port usage
netstat -tulpn | grep 8006

# Kill process using port
kill -9 $(lsof -t -i:8006)
```

## Permission Issues

**Symptoms:**
- File permission errors
- Access denied errors

**Solutions:**
```bash
# Fix ownership
chown -R aitbc:aitbc /opt/aitbc

# Fix permissions
chmod 600 /etc/aitbc/*.env
```

## See Also

- [Troubleshooting/Service Management](../troubleshooting/service-management.md) - Detailed service troubleshooting
- [Troubleshooting/Database Issues](../troubleshooting/database-issues.md) - Database-specific issues
- [Health Checks](health-checks.md) - Service health monitoring
