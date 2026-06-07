# Configuration

## Overview

The Governance Service can be configured via environment variables, configuration files, and command-line options. This document covers all configuration options.

## Environment Variables

### Database Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| DB_TYPE | Database type (sqlite/postgresql) | sqlite | No |
| DB_HOST | PostgreSQL host | localhost | No (PostgreSQL) |
| DB_PORT | PostgreSQL port | 5432 | No (PostgreSQL) |
| DB_NAME | Database name | aitbc_governance | No (PostgreSQL) |
| DB_USER | Database user | aitbc_governance | No (PostgreSQL) |
| DB_PASS | Database password | - | Yes (PostgreSQL) |

### Service Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| GOVERNANCE_PORT | Service port | 8105 | No |
| GOVERNANCE_HOST | Service host | 0.0.0.0 | No |
| LOG_LEVEL | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO | No |

### Blockchain Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| BLOCKCHAIN_RPC_URL | Blockchain RPC endpoint | http://localhost:8006 | No |
| CHAIN_ID | Chain identifier | ait-hub.aitbc.bubuit.net | No |

## Configuration Files

### alembic.ini

Location: `/opt/aitbc/apps/governance/alembic.ini`

**Database URL Configuration:**
```ini
# SQLite (default)
sqlalchemy.url = sqlite:////var/lib/aitbc/data/governance_service.db

# PostgreSQL (production)
# sqlalchemy.url = postgresql://aitbc_governance:password@localhost:5432/aitbc_governance
```

### ~/.aitbc/config.toml

Location: User's home directory

**CLI Configuration:**
```toml
[governance]
service_url = "http://localhost:8105"

[blockchain]
rpc_url = "http://localhost:8006"
chain_id = "ait-hub.aitbc.bubuit.net"
```

## Database Configuration

### SQLite (Default)

**Configuration:**
```bash
export DB_TYPE=sqlite
```

**Database Location:**
```
/var/lib/aitbc/data/governance_service.db
```

**Setup:**
```bash
mkdir -p /var/lib/aitbc/data
```

### PostgreSQL (Production)

**Configuration:**
```bash
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=aitbc_governance
export DB_USER=aitbc_governance
export DB_PASS=your_password
```

**Database Setup:**
```bash
sudo -u postgres psql
CREATE DATABASE aitbc_governance;
CREATE USER aitbc_governance WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;
\q
```

**Update alembic.ini:**
```ini
sqlalchemy.url = postgresql://aitbc_governance:your_password@localhost:5432/aitbc_governance
```

## Service Configuration

### Port Configuration

**Environment Variable:**
```bash
export GOVERNANCE_PORT=8105
```

**Or modify main.py:**
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8105)
```

### Host Configuration

**Environment Variable:**
```bash
export GOVERNANCE_HOST=0.0.0.0
```

### Logging Configuration

**Environment Variable:**
```bash
export LOG_LEVEL=INFO
```

**Or modify main.py:**
```python
configure_logging(level="DEBUG")
```

## Systemd Service Configuration

### Service File

Location: `/etc/systemd/system/aitbc-governance.service`

**Configuration:**
```ini
[Unit]
Description=AITBC Governance Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/apps/governance
Environment="PATH=/opt/aitbc/venv/bin"
Environment="DB_TYPE=postgresql"
Environment="DB_HOST=localhost"
Environment="DB_PORT=5432"
Environment="DB_NAME=aitbc_governance"
Environment="DB_USER=aitbc_governance"
Environment="DB_PASS=your_password"
ExecStart=/opt/aitbc/venv/bin/python -m governance_service.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Reload Configuration

```bash
sudo systemctl daemon-reload
sudo systemctl restart aitbc-governance
```

## Nginx Configuration

### Reverse Proxy

Location: `/etc/nginx/sites-available/governance`

**Configuration:**
```nginx
server {
    listen 80;
    server_name governance.aitbc.bubuit.net;

    location / {
        proxy_pass http://localhost:8105;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Enable Configuration

```bash
sudo ln -s /etc/nginx/sites-available/governance /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## CLI Configuration

### Service URL

**Environment Variable:**
```bash
export GOVERNANCE_SERVICE_URL=http://localhost:8105
```

**Or in config.toml:**
```toml
[governance]
service_url = "http://localhost:8105"
```

### Wallet Configuration

**Wallet Directory:**
```bash
export AITBC_WALLET_DIR=/opt/aitbc/wallets
```

**Default:** `~/.aitbc/wallets`

## Smart Contract Configuration

### Deployment Configuration

**RPC URL:**
```bash
export RPC_URL=https://mainnet.example.com
```

**Private Key:**
```bash
export PRIVATE_KEY=0x...
```

**Contract Addresses:**
```bash
export GOVERNANCE_TOKEN_ADDRESS=0x...
export VOTING_CONTRACT_ADDRESS=0x...
```

## Validation

### Test Configuration

```bash
# Test database connection
cd /opt/aitbc/apps/governance
python -c "from governance_service.storage import init_db; import asyncio; asyncio.run(init_db())"

# Test service health
curl http://localhost:8105/health

# Test CLI configuration
aitbc governance --help
```

## Troubleshooting Configuration

### Database Connection Failed

**Check:**
```bash
# SQLite: Check file permissions
ls -la /var/lib/aitbc/data/governance_service.db

# PostgreSQL: Check connection
psql -h localhost -U aitbc_governance -d aitbc_governance
```

### Service Won't Start

**Check:**
```bash
# Check systemd logs
sudo journalctl -u aitbc-governance -n 50

# Check environment variables
systemctl show aitbc-governance --property=Environment
```

### CLI Can't Connect

**Check:**
```bash
# Check service URL
echo $GOVERNANCE_SERVICE_URL

# Check service is running
curl http://localhost:8105/health
```

## Best Practices

1. **Use environment variables** for sensitive data (passwords, keys)
2. **Use configuration files** for non-sensitive settings
3. **Document all configuration changes**
4. **Test configuration changes in development first**
5. **Use version control for configuration files** (excluding secrets)
6. **Rotate secrets regularly**
7. **Use different configurations for development/staging/production**

## Security Considerations

- Never commit secrets to version control
- Use `.env` files for local development (add to .gitignore)
- Use secret management systems for production (e.g., HashiCorp Vault)
- Restrict file permissions on configuration files
- Use SSL/TLS for production deployments
- Enable firewall rules to restrict access

## References

- Service README: `/opt/aitbc/apps/governance/README.md`
- Alembic Configuration: `/opt/aitbc/apps/governance/alembic/alembic.ini`
- Systemd Service: `/etc/systemd/system/aitbc-governance.service`
