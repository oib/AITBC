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
journalctl -u aitbc-coordinator-api | grep -i authentication

# Check access logs
tail -f /var/log/nginx/access.log
```

**Solutions:**

1. Review API keys

```bash
# API keys are file-backed — there are no /v1/admin/api-keys routes.
# Inspect the storage file (path from API_KEY_STORAGE_PATH, typically
# /etc/aitbc/credentials/ or the service env):
sudo cat "$(grep -oP 'API_KEY_STORAGE_PATH=\K.*' \
  /etc/aitbc/aitbc-coordinator-api.env)"

# Rotate a key: edit the storage file / rotate via the provisioning
# script, then restart:
sudo systemctl restart aitbc-coordinator-api
```

1. Enable rate limiting

```python
# Add rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/v1/jobs")
@limiter.limit("100/minute")
async def submit_job():
    pass
```

1. Enable IP whitelisting

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
journalctl -u aitbc-* | grep -i error

# Check access logs
grep "401\|403" /var/log/nginx/access.log
```

**Solutions:**

1. Immediate containment

```bash
# Stop all services
systemctl stop aitbc-*

# Change all credentials
# Rotate API keys
# Change database passwords
```

1. Investigate breach

```bash
# Preserve evidence
journalctl -u aitbc-* > incident-logs.txt

# Analyze logs
grep -i "suspicious\|unauthorized" incident-logs.txt
```

1. Recovery

```bash
# Restore from backup
psql -d aitbc < backup.sql

# Restart services
systemctl start aitbc-*
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
journalctl -u aitbc-coordinator-api -n 500 > coordinator.log
journalctl -u aitbc-blockchain-node -n 500 > blockchain.log
journalctl -u aitbc-marketplace -n 500 > marketplace.log

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
- **API reference**: https://hub.example.net/api/docs (live openapi)
- **Community**: none — `community.aitbc.dev` does not exist; use GitHub issues

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Edit environment
echo "DEBUG=true" >> /etc/aitbc/aitbc-coordinator-api.env   # the unit's real EnvironmentFile

# Restart service
systemctl restart aitbc-coordinator-api

# View debug logs
journalctl -u aitbc-coordinator-api -f
```
