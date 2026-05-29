# Security Issues

This guide covers security problems including unauthorized access, data breaches, and authentication failures.

## Unauthorized Access

**Symptoms:**
- Unauthorized API calls
- Failed authentication attempts
- Suspicious activity

**Diagnosis:**
```bash
# Check authentication logs
sudo journalctl -u aitbc-coordinator-api | grep -i authentication

# Check access logs
sudo tail -f /var/log/nginx/access.log
```

**Solutions:**
1. Review API keys
```bash
# List all API keys
curl -H "X-Admin-Key: $ADMIN_KEY" \
  http://localhost:8011/v1/admin/api-keys

# Revoke suspicious keys
curl -X DELETE http://localhost:8011/v1/admin/api-keys/{key_id}
```

2. Enable rate limiting
```python
# Add rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/v1/jobs")
@limiter.limit("100/minute")
async def submit_job():
    pass
```

3. Enable IP whitelisting
```bash
# Configure nginx
allow 192.168.1.0/24;
deny all;
```

## Data Breach

**Symptoms:**
- Data accessed without authorization
- Logs show suspicious activity
- Credentials compromised

**Diagnosis:**
```bash
# Check for suspicious activity
sudo journalctl -u aitbc-* | grep -i error

# Check access logs
sudo grep "401\|403" /var/log/nginx/access.log
```

**Solutions:**
1. Immediate containment
```bash
# Stop all services
sudo systemctl stop aitbc-*

# Change all credentials
# Rotate API keys
# Change database passwords
```

2. Investigate breach
```bash
# Preserve evidence
sudo journalctl -u aitbc-* > incident-logs.txt

# Analyze logs
grep -i "suspicious\|unauthorized" incident-logs.txt
```

3. Recovery
```bash
# Restore from backup
psql -d aitbc < backup.sql

# Restart services
sudo systemctl start aitbc-*
```

## See Also

- [Wallet Issues](wallet-issues.md) - Key management and wallet security
- [Network Issues](network-issues.md) - Firewall and access control
- [Service Management](service-management.md) - General service troubleshooting

## Getting Help

### Log Collection

When reporting security issues, collect the following information:

```bash
# Service logs
sudo journalctl -u aitbc-coordinator-api -n 500 > coordinator.log
sudo journalctl -u aitbc-blockchain -n 500 > blockchain.log
sudo journalctl -u aitbc-marketplace -n 500 > marketplace.log

# System information
uname -a > system-info.txt
free -h >> system-info.txt
df -h >> system-info.txt

# Network information
ip addr show > network-info.txt
netstat -tulpn >> network-info.txt

# Database information
psql -d aitbc -c "\l" > database-info.txt
psql -d aitbc -c "SELECT version();" >> database-info.txt
```

### Support Channels

- **GitHub Issues**: https://github.com/oib/AITBC/issues
- **Documentation**: https://aitbc.bubuit.net/docs/
- **Community**: https://community.aitbc.dev/

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Edit environment
echo "DEBUG=true" >> /etc/aitbc/coordinator.env

# Restart service
sudo systemctl restart aitbc-coordinator-api

# View debug logs
sudo journalctl -u aitbc-coordinator-api -f
```
