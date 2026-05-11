# Comprehensive Troubleshooting Guide

This guide provides troubleshooting steps for common issues encountered when deploying and operating the AITBC platform.

## Table of Contents

- [General Troubleshooting](#general-troubleshooting)
- [Blockchain Node Issues](#blockchain-node-issues)
- [Coordinator API Issues](#coordinator-api-issues)
- [Wallet Daemon Issues](#wallet-daemon-issues)
- [Marketplace Service Issues](#marketplace-service-issues)
- [Database Issues](#database-issues)
- [Network Issues](#network-issues)
- [GPU Issues](#gpu-issues)
- [Performance Issues](#performance-issues)
- [Security Issues](#security-issues)

## General Troubleshooting

### Service Won't Start

**Symptoms:**
- Service fails to start
- Systemd service shows "failed" status
- No logs available

**Diagnosis:**
```bash
# Check service status
sudo systemctl status aitbc-coordinator-api

# Check recent logs
sudo journalctl -u aitbc-coordinator-api -n 50

# Check for errors in logs
sudo journalctl -u aitbc-coordinator-api -f | grep -i error
```

**Solutions:**
1. Check configuration files
```bash
# Validate configuration
python -m apps.coordinator_api.main --validate-config
```

2. Check port conflicts
```bash
# Check if port is in use
sudo netstat -tulpn | grep 8011

# Kill process using the port
sudo kill -9 $(sudo lsof -t -i:8011)
```

3. Check permissions
```bash
# Check file permissions
ls -la /opt/aitbc

# Fix permissions
sudo chown -R aitbc:aitbc /opt/aitbc
```

4. Check dependencies
```bash
# Verify Python dependencies
source venv/bin/activate
pip list

# Install missing dependencies
pip install -r requirements.txt
```

### High CPU Usage

**Symptoms:**
- Service consuming excessive CPU
- System sluggish
- High load averages

**Diagnosis:**
```bash
# Check CPU usage
top -p $(pgrep -f coordinator-api)

# Check process details
ps aux | grep coordinator-api

# Check system load
uptime
```

**Solutions:**
1. Profile the application
```bash
# Profile with cProfile
python -m cProfile -o profile.stats apps/coordinator_api/main.py

# Analyze profile
python -m pstats profile.stats
```

2. Check for infinite loops
```bash
# Monitor process strace
sudo strace -p $(pgrep -f coordinator-api)
```

3. Optimize database queries
```bash
# Enable query logging
export SQLALCHEMY_ECHO=true

# Analyze slow queries
psql -d aitbc -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

### Memory Leaks

**Symptoms:**
- Memory usage increases over time
- Service crashes with OOM killer
- Swap usage high

**Diagnosis:**
```bash
# Check memory usage
free -h

# Check process memory
ps aux | grep coordinator-api

# Monitor memory over time
watch -n 1 'free -h'
```

**Solutions:**
1. Check for memory leaks
```bash
# Use memory profiler
pip install memory-profiler
python -m memory_profiler apps/coordinator_api/main.py
```

2. Check connection pooling
```python
# Reduce pool size
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10
)
```

3. Restart service periodically
```bash
# Add to crontab
0 2 * * * systemctl restart aitbc-coordinator-api
```

## Blockchain Node Issues

### Node Won't Sync

**Symptoms:**
- Block height not increasing
- Sync status shows "syncing" indefinitely
- Peers not connecting

**Diagnosis:**
```bash
# Check sync status
curl http://localhost:8080/v1/network

# Check peer connections
curl http://localhost:8080/v1/network/peers

# Check blockchain logs
sudo journalctl -u aitbc-blockchain -n 50
```

**Solutions:**
1. Add bootstrap peers
```bash
# Edit configuration
echo "BOOTSTRAP_PEERS=peer1.example.com:8080,peer2.example.com:8080" >> /etc/aitbc/blockchain.env

# Restart service
sudo systemctl restart aitbc-blockchain
```

2. Check network connectivity
```bash
# Test peer connectivity
telnet peer.example.com 8080

# Check firewall
sudo ufw status
```

3. Reset blockchain state
```bash
# Stop service
sudo systemctl stop aitbc-blockchain

# Backup data
mv /var/lib/aitbc/blockchain /var/lib/aitbc/blockchain.backup

# Start service
sudo systemctl start aitbc-blockchain
```

### Fork Detected

**Symptoms:**
- Multiple blockchain branches
- Consensus failures
- Invalid blocks

**Diagnosis:**
```bash
# Check blockchain height
curl http://localhost:8080/v1/blocks/head

# Check for forks
curl http://localhost:8080/v1/blocks/forks
```

**Solutions:**
1. Choose correct fork
```bash
# Revert to correct height
curl -X POST http://localhost:8080/v1/admin/revert \
  -H "Content-Type: application/json" \
  -d '{"height": 12345}'
```

2. Restart with clean state
```bash
# Stop service
sudo systemctl stop aitbc-blockchain

# Clear blockchain data
rm -rf /var/lib/aitbc/blockchain

# Start service
sudo systemctl start aitbc-blockchain
```

## Coordinator API Issues

### 500 Internal Server Error

**Symptoms:**
- API returns 500 errors
- Jobs fail to submit
- Status checks fail

**Diagnosis:**
```bash
# Check API logs
sudo journalctl -u aitbc-coordinator-api -n 100 | grep -i error

# Check database connection
psql -d aitbc -c "SELECT 1;"

# Check health endpoint
curl http://localhost:8011/health
```

**Solutions:**
1. Check database connectivity
```bash
# Test database connection
psql -h localhost -U aitbc -d aitbc

# Restart PostgreSQL
sudo systemctl restart postgresql
```

2. Check Redis connection
```bash
# Test Redis
redis-cli ping

# Restart Redis
sudo systemctl restart redis
```

3. Check datetime handling
```bash
# Check for datetime comparison errors
# Ensure all datetimes are timezone-aware or offset-naive consistently
```

### Job Stuck in Queued State

**Symptoms:**
- Jobs remain in QUEUED state
- No miners assigned
- Job expiration

**Diagnosis:**
```bash
# Check job status
curl -H "X-Api-Key: $API_KEY" \
  http://localhost:8011/v1/jobs/{job_id}

# Check miner availability
curl http://localhost:8011/v1/miners

# Check logs
sudo journalctl -u aitbc-coordinator-api -n 50
```

**Solutions:**
1. Check miner registration
```bash
# Verify miners are registered
curl http://localhost:8011/v1/miners

# Register miner if needed
curl -X POST http://localhost:8011/v1/miners/register \
  -H "Content-Type: application/json" \
  -d '{"miner_id": "miner-123", "gpu_type": "nvidia-rtx-3090"}'
```

2. Check job constraints
```bash
# Verify job constraints can be satisfied
curl -H "X-Api-Key: $API_KEY" \
  http://localhost:8011/v1/jobs/{job_id} | jq '.constraints'
```

3. Increase job TTL
```bash
# Resubmit with longer TTL
curl -X POST http://localhost:8011/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"payload": {...}, "ttl_seconds": 3600}'
```

## Wallet Daemon Issues

### Wallet Not Responding

**Symptoms:**
- Wallet daemon unresponsive
- Transactions not signing
- Balance not updating

**Diagnosis:**
```bash
# Check wallet daemon status
sudo systemctl status aitbc-wallet

# Check wallet logs
sudo journalctl -u aitbc-wallet -n 50

# Test wallet endpoint
curl http://localhost:8071/health
```

**Solutions:**
1. Check wallet file integrity
```bash
# Verify wallet file exists
ls -la /var/lib/aitbc/wallet/

# Check wallet file permissions
chmod 600 /var/lib/aitbc/wallet/wallet.dat
```

2. Restart wallet daemon
```bash
sudo systemctl restart aitbc-wallet
```

3. Check key derivation
```bash
# Verify key derivation path
python -c "from aitbc_crypto import Wallet; w = Wallet(); print(w.address)"
```

### Transaction Signing Failed

**Symptoms:**
- Transactions fail to sign
- Invalid signature errors
- Key not found errors

**Diagnosis:**
```bash
# Check wallet keys
curl http://localhost:8071/v1/keys

# Check transaction logs
sudo journalctl -u aitbc-wallet -n 50 | grep -i transaction
```

**Solutions:**
1. Verify private key
```bash
# Check private key exists
ls -la /var/lib/aitbc/wallet/private_key

# Regenerate keys if needed
curl -X POST http://localhost:8071/v1/keys/regenerate
```

2. Check key permissions
```bash
# Secure private key
chmod 600 /var/lib/aitbc/wallet/private_key
chown aitbc:aitbc /var/lib/aitbc/wallet/private_key
```

## Marketplace Service Issues

### Offers Not Matching

**Symptoms:**
- GPU offers not matched with jobs
- Jobs remain unassigned
- Marketplace not updating

**Diagnosis:**
```bash
# Check marketplace status
curl http://localhost:8102/health

# Check offers
curl http://localhost:8102/v1/offers

# Check matching logs
sudo journalctl -u aitbc-marketplace -n 50
```

**Solutions:**
1. Check offer constraints
```bash
# Verify offer constraints
curl http://localhost:8102/v1/offers | jq '.[].constraints'
```

2. Restart matching engine
```bash
sudo systemctl restart aitbc-marketplace
```

3. Clear offer cache
```bash
# Clear Redis cache
redis-cli FLUSHALL

# Restart service
sudo systemctl restart aitbc-marketplace
```

## Database Issues

### Connection Refused

**Symptoms:**
- Database connection errors
- Service unable to connect to PostgreSQL
- "Connection refused" messages

**Diagnosis:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test connection
psql -h localhost -U aitbc -d aitbc

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

**Solutions:**
1. Restart PostgreSQL
```bash
sudo systemctl restart postgresql
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
sudo ufw status | grep 5432

# Allow PostgreSQL
sudo ufw allow 5432/tcp
```

### Slow Queries

**Symptoms:**
- API responses slow
- Database CPU high
- Query timeouts

**Diagnosis:**
```bash
# Enable query logging
psql -d aitbc -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
sudo systemctl reload postgresql

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
sudo systemctl reload postgresql
```

### Database Corruption

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
sudo systemctl stop postgresql

# Restore from backup
psql -d aitbc < backup-20260511.sql

# Start PostgreSQL
sudo systemctl start postgresql
```

2. Use WAL recovery
```bash
# Configure recovery
echo "restore_command = 'cp /var/lib/postgresql/wal/%f %p'" >> /etc/postgresql/*/main/recovery.conf

# Restart PostgreSQL
sudo systemctl restart postgresql
```

## Network Issues

### Connection Timeouts

**Symptoms:**
- Services unable to connect to each other
- Intermittent connection failures
- High latency

**Diagnosis:**
```bash
# Test connectivity
ping -c 10 localhost

# Check DNS
nslookup localhost

# Check ports
telnet localhost 8011
```

**Solutions:**
1. Check network configuration
```bash
# Check IP configuration
ip addr show

# Check routing
ip route show

# Check DNS
cat /etc/resolv.conf
```

2. Check firewall rules
```bash
# Check UFW status
sudo ufw status

# Check iptables
sudo iptables -L -n
```

3. Check MTU
```bash
# Check MTU
ip link show

# Adjust MTU if needed
sudo ip link set eth0 mtu 1500
```

### DNS Issues

**Symptoms:**
- Domain names not resolving
- Services unable to connect by hostname
- Slow DNS resolution

**Diagnosis:**
```bash
# Test DNS resolution
nslookup google.com

# Check DNS servers
cat /etc/resolv.conf

# Test local DNS
dig localhost
```

**Solutions:**
1. Change DNS servers
```bash
# Use Google DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf
```

2. Clear DNS cache
```bash
# Clear systemd cache
sudo systemd-resolve --flush-caches

# Restart DNS service
sudo systemctl restart systemd-resolved
```

## GPU Issues

### GPU Not Detected

**Symptoms:**
- GPU not recognized
- CUDA errors
- Mining fails

**Diagnosis:**
```bash
# Check GPU
nvidia-smi

# Check CUDA
nvcc --version

# Check driver
dmesg | grep -i nvidia
```

**Solutions:**
1. Reinstall NVIDIA driver
```bash
# Remove old driver
sudo apt remove nvidia-* --purge

# Install new driver
sudo apt install nvidia-driver-535

# Reboot
sudo reboot
```

2. Check CUDA installation
```bash
# Verify CUDA installation
nvcc --version

# Reinstall CUDA if needed
sudo apt install nvidia-cuda-toolkit
```

3. Check GPU permissions
```bash
# Add user to video group
sudo usermod -aG video $USER

# Reboot
sudo reboot
```

### GPU Memory Errors

**Symptoms:**
- Out of memory errors
- CUDA out of memory
- Jobs failing

**Diagnosis:**
```bash
# Check GPU memory
nvidia-smi

# Monitor memory usage
watch -n 1 nvidia-smi
```

**Solutions:**
1. Reduce batch size
```python
# Reduce batch size in job configuration
batch_size = 8  # Reduce from 16
```

2. Clear GPU cache
```python
import torch
torch.cuda.empty_cache()
```

3. Restart mining service
```bash
sudo systemctl restart aitbc-miner
```

## Performance Issues

### Slow API Response Times

**Symptoms:**
- API requests take long to complete
- Timeouts
- Poor user experience

**Diagnosis:**
```bash
# Measure response time
time curl http://localhost:8011/v1/jobs

# Check database query times
psql -d aitbc -c "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Solutions:**
1. Enable caching
```python
# Add Redis caching
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_job(job_id: str):
    return job_service.get_job(job_id)
```

2. Optimize database queries
```sql
-- Add indexes
CREATE INDEX CONCURRENTLY idx_job_state ON job(state);
```

3. Use connection pooling
```python
# Increase pool size
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40
)
```

### High Latency

**Symptoms:**
- Network latency high
- Slow data transfer
- Poor performance

**Diagnosis:**
```bash
# Measure latency
ping -c 10 localhost

# Check network throughput
iperf3 -s
iperf3 -c localhost
```

**Solutions:**
1. Optimize network
```bash
# Check network configuration
ethtool eth0

# Adjust network settings
sudo ethtool -G eth0 rx 4096 tx 4096
```

2. Use local caching
```python
# Cache frequently accessed data
from cachetools import TTLCache

cache = TTLCache(maxsize=1000, ttl=300)
```

## Security Issues

### Unauthorized Access

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

### Data Breach

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

## Getting Help

### Log Collection

When reporting issues, collect the following information:

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
