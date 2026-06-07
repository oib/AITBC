# Troubleshooting

## Overview

This document covers common issues and solutions for the Governance Service, smart contracts, CLI commands, and database operations.

## Service Issues

### Service Won't Start

**Symptoms:**
- Systemd service fails to start
- Service starts but immediately stops
- Port already in use

**Solutions:**

1. **Check systemd logs:**
   ```bash
   sudo journalctl -u aitbc-governance -n 50
   ```

2. **Check if port is in use:**
   ```bash
   sudo lsof -i :8105
   ```

3. **Kill existing process:**
   ```bash
   sudo kill -9 <pid>
   ```

4. **Check dependencies:**
   ```bash
   source /opt/aitbc/venv/bin/activate
   pip list | grep governance
   ```

5. **Restart service:**
   ```bash
   sudo systemctl restart aitbc-governance
   ```

### Service Returns 500 Errors

**Symptoms:**
- API endpoints return 500 status
- Internal server error in logs

**Solutions:**

1. **Check application logs:**
   ```bash
   sudo journalctl -u aitbc-governance -f
   ```

2. **Check database connection:**
   ```bash
   # SQLite
   ls -la /var/lib/aitbc/data/governance_service.db
   
   # PostgreSQL
   sudo -u postgres psql -h localhost -U aitbc_governance -d aitbc_governance
   ```

3. **Verify migrations:**
   ```bash
   cd /opt/aitbc/apps/governance
   /opt/aitbc/venv/bin/alembic current
   ```

4. **Run migrations if needed:**
   ```bash
   /opt/aitbc/venv/bin/alembic upgrade head
   ```

### Health Check Fails

**Symptoms:**
- `/health` endpoint returns error
- `/ready` endpoint returns 503

**Solutions:**

1. **Check service status:**
   ```bash
   sudo systemctl status aitbc-governance
   ```

2. **Test database connectivity:**
   ```bash
   python -c "from governance_service.storage import init_db; import asyncio; asyncio.run(init_db())"
   ```

3. **Check environment variables:**
   ```bash
   systemctl show aitbc-governance --property=Environment
   ```

## Database Issues

### Migration Fails

**Symptoms:**
- `alembic upgrade head` fails
- "Table already exists" error
- "Module not found" error

**Solutions:**

1. **Table already exists:**
   ```bash
   # SQLite: Delete database
   rm /var/lib/aitbc/data/governance_service.db
   
   # PostgreSQL: Drop database
   sudo -u postgres psql -c "DROP DATABASE aitbc_governance;"
   sudo -u postgres psql -c "CREATE DATABASE aitbc_governance;"
   
   # Re-run migrations
   /opt/aitbc/venv/bin/alembic upgrade head
   ```

2. **Module not found:**
   ```bash
   # Check Python path in alembic/env.py
   cd /opt/aitbc/apps/governance
   cat alembic/env.py | grep sys.path
   ```

3. **Database connection error:**
   ```bash
   # Check alembic.ini
   cat alembic/alembic.ini | grep sqlalchemy.url
   
   # Test connection
   psql -h localhost -U aitbc_governance -d aitbc_governance
   ```

### Database Lock Errors

**Symptoms:**
- "Database is locked" error (SQLite)
- Connection timeout (PostgreSQL)

**Solutions:**

1. **SQLite lock:**
   ```bash
   # Check for open connections
   sudo lsof /var/lib/aitbc/data/governance_service.db
   
   # Kill processes
   sudo kill -9 <pid>
   ```

2. **PostgreSQL connection limit:**
   ```bash
   # Check max connections
   sudo -u postgres psql -c "SHOW max_connections;"
   
   # Increase if needed
   sudo nano /etc/postgresql/*/main/postgresql.conf
   # Add: max_connections = 100
   sudo systemctl restart postgresql
   ```

### Slow Queries

**Symptoms:**
- API responses are slow
- Database queries take long time

**Solutions:**

1. **Check indexes:**
   ```bash
   sudo -u postgres psql -d aitbc_governance -c "\d proposals"
   ```

2. **Analyze query performance:**
   ```bash
   sudo -u postgres psql -d aitbc_governance -c "EXPLAIN ANALYZE SELECT * FROM proposals WHERE status = 'active';"
   ```

3. **Add missing indexes:**
   ```bash
   /opt/aitbc/venv/bin/alembic revision -m "add_missing_indexes"
   # Edit migration to add indexes
   /opt/aitbc/venv/bin/alembic upgrade head
   ```

## Smart Contract Issues

### Compilation Fails

**Symptoms:**
- `forge build` fails
- Compiler errors

**Solutions:**

1. **Check Solidity version:**
   ```bash
   forge --version
   ```

2. **Install OpenZeppelin:**
   ```bash
   cd /opt/aitbc/contracts/governance
   forge install OpenZeppelin/openzeppelin-contracts
   ```

3. **Check import paths:**
   ```bash
   cat src/AITBCGovernanceToken.sol | grep import
   ```

### Tests Fail

**Symptoms:**
- `forge test` fails
- Specific test fails

**Solutions:**

1. **Run with verbosity:**
   ```bash
   forge test -vvv
   ```

2. **Run specific test:**
   ```bash
   forge test --match-test testStakeTokens
   ```

3. **Check gas limits:**
   ```bash
   forge test --gas-report
   ```

### Deployment Fails

**Symptoms:**
- Transaction reverted
- Out of gas
- Invalid address

**Solutions:**

1. **Check RPC URL:**
   ```bash
   echo $RPC_URL
   curl $RPC_URL
   ```

2. **Check private key:**
   ```bash
   echo $PRIVATE_KEY
   ```

3. **Check gas price:**
   ```bash
   cast gas-price --rpc-url $RPC_URL
   ```

4. **Test on testnet first:**
   ```bash
   export RPC_URL=https://testnet.example.com
   forge create ...
   ```

## CLI Issues

### Command Not Found

**Symptoms:**
- `aitbc governance` not found
- Command not recognized

**Solutions:**

1. **Check installation:**
   ```bash
   which aitbc
   ```

2. **Reinstall CLI:**
   ```bash
   cd /opt/aitbc
   poetry install
   ```

3. **Check PATH:**
   ```bash
   echo $PATH | grep aitbc
   ```

### Connection Errors

**Symptoms:**
- "Network error" in CLI
- Cannot connect to service

**Solutions:**

1. **Check service is running:**
   ```bash
   curl http://localhost:8105/health
   ```

2. **Check service URL:**
   ```bash
   echo $GOVERNANCE_SERVICE_URL
   ```

3. **Check firewall:**
   ```bash
   sudo ufw status
   sudo ufw allow 8105
   ```

### Wallet Errors

**Symptoms:**
- "Wallet not found"
- "Invalid wallet"

**Solutions:**

1. **List wallets:**
   ```bash
   aitbc wallet list
   ```

2. **Check wallet directory:**
   ```bash
   ls -la ~/.aitbc/wallets/
   ```

3. **Create wallet:**
   ```bash
   aitbc wallet create mywallet
   ```

## API Issues

### 404 Not Found

**Symptoms:**
- Endpoint returns 404
- Resource not found

**Solutions:**

1. **Check endpoint path:**
   ```bash
   curl http://localhost:8105/v1/governance/proposals
   ```

2. **Check API version:**
   ```bash
   curl http://localhost:8105/v1/governance/status
   ```

3. **Check service logs:**
   ```bash
   sudo journalctl -u aitbc-governance -n 50
   ```

### 400 Bad Request

**Symptoms:**
- Invalid request data
- Validation error

**Solutions:**

1. **Check request format:**
   ```bash
   curl -X POST http://localhost:8105/v1/governance/stake \
     -H "Content-Type: application/json" \
     -d '{"staker_address": "0x123...", "amount": 1000, "lock_period_days": 30}'
   ```

2. **Check validation rules:**
   - Lock period must be >= 30 days
   - Address must be valid hex
   - Amount must be positive

### 500 Internal Server Error

**Symptoms:**
- Server error
- Unhandled exception

**Solutions:**

1. **Check service logs:**
   ```bash
   sudo journalctl -u aitbc-governance -f
   ```

2. **Check database:**
   ```bash
   # SQLite
   sqlite3 /var/lib/aitbc/data/governance_service.db ".tables"
   
   # PostgreSQL
   sudo -u postgres psql -d aitbc_governance -c "\dt"
   ```

3. **Restart service:**
   ```bash
   sudo systemctl restart aitbc-governance
   ```

## Performance Issues

### High Memory Usage

**Symptoms:**
- Service uses excessive memory
- OOM killer kills process

**Solutions:**

1. **Check memory usage:**
   ```bash
   ps aux | grep governance_service
   ```

2. **Check connection pool:**
   ```python
   # In storage.py, reduce pool size
   engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
   ```

3. **Restart service:**
   ```bash
   sudo systemctl restart aitbc-governance
   ```

### High CPU Usage

**Symptoms:**
- Service uses excessive CPU
- Slow response times

**Solutions:**

1. **Check CPU usage:**
   ```bash
   top -p $(pgrep governance_service)
   ```

2. **Check for infinite loops:**
   ```bash
   sudo journalctl -u aitbc-governance -f
   ```

3. **Profile code:**
   ```bash
   python -m cProfile -s cumtime governance_service/main.py
   ```

## Getting Help

### Logs

**Service logs:**
```bash
sudo journalctl -u aitbc-governance -f
```

**Application logs:**
```bash
tail -f /var/log/aitbc/governance.log
```

### Debug Mode

**Enable debug logging:**
```bash
export LOG_LEVEL=DEBUG
sudo systemctl restart aitbc-governance
```

**Run service manually:**
```bash
cd /opt/aitbc/apps/governance
python -m governance_service.main
```

### Support

**Documentation:**
- Service README: `/opt/aitbc/apps/governance/README.md`
- Release Notes: `/opt/aitbc/docs/releases/RELEASE_v0.4.12.md`

**Issue Reporting:**
- Collect logs
- Describe the issue
- Include steps to reproduce
- Note system configuration

## Common Error Messages

### "Module not found: governance_service"

**Cause:** Python path not configured correctly

**Solution:**
```bash
export PYTHONPATH=/opt/aitbc/apps/governance/src:$PYTHONPATH
```

### "Table already exists"

**Cause:** Database already has tables from previous migration

**Solution:**
```bash
# SQLite
rm /var/lib/aitbc/data/governance_service.db

# PostgreSQL
sudo -u postgres psql -c "DROP DATABASE aitbc_governance;"
sudo -u postgres psql -c "CREATE DATABASE aitbc_governance;"
```

### "Insufficient voting power"

**Cause:** Not enough tokens or staked tokens

**Solution:**
```bash
# Check voting power
aitbc governance voting-power <address>

# Stake more tokens
aitbc governance stake --address <address> --amount 1000 --lock-days 30
```

### "Proposal not in succeeded state"

**Cause:** Proposal status is not 'succeeded'

**Solution:**
```bash
# Check proposal status
aitbc governance get-proposal <proposal_id>
```

## Prevention

### Regular Maintenance

1. **Check service health:**
   ```bash
   curl http://localhost:8105/health
   ```

2. **Check disk space:**
   ```bash
   df -h /var/lib/aitbc/data
   ```

3. **Check database size:**
   ```bash
   # SQLite
   ls -lh /var/lib/aitbc/data/governance_service.db
   
   # PostgreSQL
   sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('aitbc_governance'));"
   ```

4. **Review logs:**
   ```bash
   sudo journalctl -u aitbc-governance --since yesterday
   ```

### Monitoring

Set up monitoring for:
- Service uptime
- Response times
- Error rates
- Database performance
- Disk usage
- Memory usage

### Backups

Regular backups of:
- Database
- Configuration files
- Wallet files
- Smart contract addresses

## References

- Service README: `/opt/aitbc/apps/governance/README.md`
- Configuration: [Configuration](08-CONFIGURATION.md)
- Deployment: [Deployment](09-DEPLOYMENT.md)
- Security: [Security](10-SECURITY.md)
