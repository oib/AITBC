# Staging Environment Guide

**Last Updated:** 2026-06-19
**Version:** v0.5.0

## Overview

The staging environment is a production-like environment used for testing changes before deploying to production. It mirrors production configuration while using separate resources to prevent any impact on production systems.

## Purpose

- Test new features and bug fixes in a production-like environment
- Validate configuration changes
- Perform integration testing across services
- Train operations teams on deployment procedures
- Load testing and performance validation

## Architecture

Staging follows the same architecture as production but with isolated resources:

```
staging.aitbc.example.com
├── Blockchain Node (port 8202)
│   ├── Separate blockchain network (staging chain ID)
│   └── Separate genesis block
├── Coordinator API (port 8000)
│   ├── Separate PostgreSQL database
│   └── Separate Redis instance
├── Agent Coordinator (port 8100)
│   ├── Separate configuration
│   └── Test agent instances
├── Governance Service (port 8105)
│   ├── Separate governance database
│   └── Test proposals
└── Monitoring Stack
    ├── Prometheus (port 9090)
    ├── Grafana (port 3000)
    └── Alertmanager (port 9093)
```

## Prerequisites

### System Requirements

Same as production:
- CPU: 4+ cores
- RAM: 16GB+
- Disk: 100GB+ SSD
- OS: Debian 12+ or Ubuntu 22.04+

### Software Requirements

- Python 3.13+
- PostgreSQL 15+
- Redis 7+
- systemd
- nginx (for reverse proxy)

## Deployment

### 1. Initial Setup

```bash
# Clone the repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Run the setup script with staging configuration
./scripts/deployment/setup.sh --environment staging
```

### 2. Environment Configuration

Create `/etc/aitbc/staging.env`:

```bash
# Environment
AITBC_ENVIRONMENT=staging
CHAIN_ID=ait-staging

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aitbc_staging
DB_USER=aitbc_staging
DB_PASS=<secure_password_from_vault>

# Redis Configuration
REDIS_URL=redis://localhost:6379/2

# Service Ports (can differ from production)
COORDINATOR_API_PORT=8000
AGENT_COORDINATOR_PORT=8100
GOVERNANCE_PORT=8105
BLOCKCHAIN_NODE_PORT=8202

# Logging
LOG_LEVEL=debug
LOG_FORMAT=json

# Feature Flags
ENABLE_EXPERIMENTAL_FEATURES=true
ENABLE_METRICS=true
```

### 3. Database Setup

```bash
# Create staging database
sudo -u postgres psql <<EOF
CREATE DATABASE aitbc_staging;
CREATE USER aitbc_staging WITH PASSWORD '<secure_password>';
GRANT ALL PRIVILEGES ON DATABASE aitbc_staging TO aitbc_staging;
EOF

# Run migrations
cd /opt/aitbc/apps/coordinator-api
source /opt/aitbc/venv/bin/activate
alembic upgrade head
```

### 4. Service Configuration

Update systemd service files to use staging environment:

```bash
# For each service, add:
EnvironmentFile=/etc/aitbc/staging.env
Environment=AITBC_ENVIRONMENT=staging
```

Example for coordinator-api:

```ini
[Service]
EnvironmentFile=/etc/aitbc/staging.env
Environment=LOG_LEVEL=debug
Environment=LOG_FORMAT=json
```

### 5. Start Services

```bash
# Enable and start all services
sudo systemctl enable aitbc-coordinator-api
sudo systemctl enable aitbc-agent-coordinator
sudo systemctl enable aitbc-governance
sudo systemctl enable aitbc-blockchain-p2p

sudo systemctl start aitbc-coordinator-api
sudo systemctl start aitbc-agent-coordinator
sudo systemctl start aitbc-governance
sudo systemctl start aitbc-blockchain-p2p
```

## Staging vs Production Differences

| Aspect | Staging | Production |
|--------|---------|------------|
| Chain ID | `ait-staging` | `ait-mainnet` |
| Database | `aitbc_staging` | `aitbc` |
| Redis DB | 2 | 0 |
| Log Level | `debug` | `info` |
| Metrics | Enabled | Enabled |
| Experimental Features | Enabled | Disabled |
| Resource Limits | Lower | Full |
| Backup Frequency | Daily | Hourly |
| Monitoring | Full | Full |

## Data Management

### Initial Data

Staging uses synthetic test data:

```bash
# Generate test blockchain data
python /opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py \
    --chain-id ait-staging \
    --create-wallet \
    --db-path /var/lib/aitbc/blockchain/staging.db

# Load test governance proposals
python /opt/aitbc/apps/governance/scripts/load_test_proposals.py \
    --environment staging
```

### Data Refresh

To refresh staging data:

```bash
# Stop services
sudo systemctl stop aitbc-*

# Backup current staging data
sudo -u postgres pg_dump aitbc_staging > /tmp/staging_backup_$(date +%Y%m%d).sql

# Drop and recreate database
sudo -u postgres psql <<EOF
DROP DATABASE aitbc_staging;
CREATE DATABASE aitbc_staging;
EOF

# Restore from production snapshot (sanitized)
sudo -u postgres psql aitbc_staging < /tmp/production_sanitized.sql

# Restart services
sudo systemctl start aitbc-*
```

### Data Sanitization

When copying from production to staging, sanitize sensitive data:

```bash
# Remove real user data
sudo -u postgres psql aitbc_staging <<EOF
DELETE FROM users WHERE email NOT LIKE '%@staging.example.com';
UPDATE users SET email = REPLACE(email, '@', '+staging@');
DELETE FROM api_keys WHERE key NOT LIKE 'staging_%';
EOF
```

## Testing Procedures

### Smoke Tests

Run after each deployment:

```bash
# Health check
./scripts/monitoring/health_check.sh --environment staging

# API connectivity
curl -f http://localhost:8000/health || exit 1
curl -f http://localhost:8100/health || exit 1
curl -f http://localhost:8105/health || exit 1
curl -f http://localhost:8202/health || exit 1
```

### Integration Tests

```bash
# Run integration test suite
cd /opt/aitbc
pytest tests/integration/ --environment=staging
```

### Load Testing

```bash
# Run load tests (k6 or locust)
k6 run tests/load/test_coordinator.js --env STAGING_URL=http://localhost:8000
```

## Monitoring

### Prometheus Metrics

Access staging metrics:

```bash
# Prometheus UI
http://staging.aitbc.example.com:9090

# Grafana dashboards
http://staging.aitbc.example.com:3000
```

### Log Aggregation

Staging logs are sent to a separate log index:

```bash
# View staging logs
journalctl -u aitbc-coordinator-api -f
```

### Alerts

Staging has separate alerting rules with higher thresholds to avoid noise:

- Response time alerts: 5s (vs 2s in production)
- Error rate alerts: 10% (vs 5% in production)
- Disk usage alerts: 90% (vs 80% in production)

## Deployment to Staging

### Automated Deployment

```bash
# Deploy to staging
./scripts/deployment/deploy.sh --environment staging

# This will:
# 1. Pull latest code
# 2. Run database migrations
# 3. Restart services
# 4. Run smoke tests
# 5. Report status
```

### Manual Deployment

```bash
# 1. Pull latest code
cd /opt/aitbc
git pull origin main

# 2. Update dependencies
source venv/bin/activate
pip install -e ".[dev]"

# 3. Run database migrations
cd apps/coordinator-api
alembic upgrade head

# 4. Restart services
sudo systemctl restart aitbc-*

# 5. Verify deployment
./scripts/monitoring/health_check.sh --environment staging
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
journalctl -u aitbc-coordinator-api -n 50

# Check environment variables
systemctl show aitbc-coordinator-api --property=Environment

# Verify database connectivity
psql -h localhost -U aitbc_staging -d aitbc_staging
```

### Database Migration Failures

```bash
# Check migration status
cd /opt/aitbc/apps/coordinator-api
alembic current

# Force specific version (use with caution)
alembic upgrade <revision>
```

### Network Issues

```bash
# Check service ports
ss -tlnp | grep -E '8000|8100|8105|8202'

# Test connectivity
curl -v http://localhost:8000/health
```

## Security Considerations

Staging should be secured similarly to production:

- Use HTTPS for all external access
- Restrict access to staging environment (VPN or allowlist)
- Use separate secrets from production
- Enable authentication for monitoring dashboards
- Regular security updates

## Cleanup

To reset staging environment:

```bash
# Stop all services
sudo systemctl stop aitbc-*

# Drop staging database
sudo -u postgres psql <<EOF
DROP DATABASE aitbc_staging;
EOF

# Remove blockchain data
sudo rm -rf /var/lib/aitbc/blockchain/staging.db

# Remove logs older than 30 days
sudo journalctl --vacuum-time=30d

# Restart services (they will reinitialize)
sudo systemctl start aitbc-*
```

## Best Practices

1. **Always test in staging before production**
2. **Keep staging configuration in sync with production**
3. **Use realistic test data**
4. **Monitor staging alerts**
5. **Document any staging-specific workarounds**
6. **Regularly refresh staging data**
7. **Automate staging deployments**
8. **Use staging for training new team members**

## See Also

- [Production Deployment Guide](single-server.md)
- [Configuration Reference](configuration.md)
- [Health Checks](health-checks.md)
- [Secret Management](../operations/SECRETS.md)
- [Service Ports Reference](../reference/SERVICE_PORTS.md)
