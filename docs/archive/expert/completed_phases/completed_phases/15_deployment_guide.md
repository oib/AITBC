# Agent Economics System Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the OpenClaw Agent Economics Enhancement system, including all components: Reputation System, Performance-Based Reward Engine, P2P Trading Protocol, Marketplace Analytics Platform, and Certification & Partnership Programs.

## System Architecture

### Components Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Economics System                    │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Reputation   │  │   Rewards   │  │    P2P Trading     │  │
│  │   System    │  │   Engine    │  │    Protocol        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Analytics  │  │ Certification│  │   Integration &     │  │
│  │  Platform   │  │ & Partnerships│  │   Testing Layer    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema

The system uses SQLModel with PostgreSQL as the primary database:

- **Reputation Tables**: `agent_reputations`, `community_feedback`, `economic_profiles`
- **Reward Tables**: `reward_profiles`, `reward_calculations`, `reward_distributions`
- **Trading Tables**: `trade_requests`, `trade_matches`, `trade_negotiations`, `trade_agreements`
- **Analytics Tables**: `market_metrics`, `market_insights`, `analytics_reports`
- **Certification Tables**: `agent_certifications`, `partnership_programs`, `achievement_badges`

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Python**: 3.13.5+
- **Database**: PostgreSQL 14+
- **Memory**: Minimum 8GB RAM (16GB+ recommended)
- **Storage**: Minimum 50GB SSD (100GB+ recommended)
- **Network**: Stable internet connection for blockchain integration

### Software Dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Database setup
sudo apt-get install postgresql postgresql-contrib

# Additional system packages
sudo apt-get install build-essential libpq-dev
```

### Environment Configuration

Create `.env` file with the following variables:

```env
# Database Configuration
DATABASE_URL=postgresql://username:password@localhost:5432/aitbc_economics
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Redis Configuration (for caching)
REDIS_URL=redis://localhost:6379/0
REDIS_POOL_SIZE=10

# Blockchain Configuration
BLOCKCHAIN_RPC_URL=http://localhost:8545
BLOCKCHAIN_CONTRACT_ADDRESS=0x1234567890123456789012345678901234567890
BLOCKCHAIN_PRIVATE_KEY=your_private_key_here

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
API_TIMEOUT=30

# Analytics Configuration
ANALYTICS_BATCH_SIZE=1000
ANALYTICS_RETENTION_DAYS=90
ANALYTICS_REFRESH_INTERVAL=300

# Security Configuration
SECRET_KEY=your_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# Monitoring Configuration
LOG_LEVEL=INFO
LOG_FORMAT=json
METRICS_PORT=9090
```

## Installation Steps

### 1. Database Setup

```bash
# Create database
sudo -u postgres createdb aitbc_economics

# Create user
sudo -u postgres createuser --interactive aitbc_user

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_economics TO aitbc_user;"
```

### 2. Schema Migration

```bash
# Run database migrations
python -m alembic upgrade head

# Verify schema
python -m alembic current
```

### 3. Service Configuration

Create systemd service files for each component:

```ini
# /etc/systemd/system/aitbc-reputation.service
[Unit]
Description=AITBC Reputation System
After=network.target postgresql.service

[Service]
Type=exec
User=aitbc
Group=aitbc
WorkingDirectory=/opt/aitbc/apps/coordinator-api
Environment=PYTHONPATH=/opt/aitbc
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn app.routers.reputation:router --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/aitbc-rewards.service
[Unit]
Description=AITBC Reward Engine
After=network.target postgresql.service

[Service]
Type=exec
User=aitbc
Group=aitbc
WorkingDirectory=/opt/aitbc/apps/coordinator-api
Environment=PYTHONPATH=/opt/aitbc
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn app.routers.rewards:router --host 0.0.0.0 --port 8002
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4. Load Balancer Configuration

```nginx
# /etc/nginx/sites-available/aitbc-economics
upstream economics_backend {
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
    server 127.0.0.1:8003;
    server 127.0.0.1:8004;
    server 127.0.0.1:8005;
}

server {
    listen 80;
    server_name economics.aitbc.bubuit.net;
    
    location / {
        proxy_pass http://economics_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://economics_backend/health;
        access_log off;
    }
}
```

### 5. Service Startup

```bash
# Enable and start services
systemctl enable aitbc-reputation
systemctl enable aitbc-rewards
systemctl enable aitbc-trading
systemctl enable aitbc-analytics
systemctl enable aitbc-certification

# Start services
systemctl start aitbc-reputation
systemctl start aitbc-rewards
systemctl start aitbc-trading
systemctl start aitbc-analytics
systemctl start aitbc-certification

# Check status
systemctl status aitbc-*
```

## Configuration Details

### Reputation System Configuration

```python
# config/reputation.py
REPUTATION_CONFIG = {
    "trust_score_weights": {
        "performance": 0.35,
        "reliability": 0.25,
        "community": 0.20,
        "economic": 0.15,
        "temporal": 0.05
    },
    "reputation_levels": {
        "beginner": {"min_score": 0, "max_score": 399},
        "novice": {"min_score": 400, "max_score": 599},
        "intermediate": {"min_score": 600, "max_score": 799},
        "advanced": {"min_score": 800, "max_score": 949},
        "master": {"min_score": 950, "max_score": 1000}
    },
    "update_frequency": 3600,  # 1 hour
    "batch_size": 100
}
```

### Reward Engine Configuration

```python
# config/rewards.py
REWARD_CONFIG = {
    "tiers": {
        "bronze": {"min_points": 0, "multiplier": 1.0},
        "silver": {"min_points": 1000, "multiplier": 1.2},
        "gold": {"min_points": 5000, "multiplier": 1.5},
        "platinum": {"min_points": 15000, "multiplier": 2.0},
        "diamond": {"min_points": 50000, "multiplier": 3.0}
    },
    "bonus_types": {
        "performance": {"weight": 0.4, "max_multiplier": 2.0},
        "loyalty": {"weight": 0.25, "max_multiplier": 1.5},
        "referral": {"weight": 0.2, "max_multiplier": 1.3},
        "milestone": {"weight": 0.15, "max_multiplier": 1.8}
    },
    "distribution_frequency": 86400,  # 24 hours
    "batch_processing_limit": 1000
}
```

### Trading Protocol Configuration

```python
# config/trading.py
TRADING_CONFIG = {
    "matching_weights": {
        "price": 0.25,
        "specifications": 0.20,
        "timing": 0.15,
        "reputation": 0.15,
        "geography": 0.10,
        "availability": 0.10,
        "service_level": 0.05
    },
    "settlement_types": {
        "immediate": {"fee_rate": 0.01, "processing_time": 300},
        "escrow": {"fee_rate": 0.02, "processing_time": 1800},
        "milestone": {"fee_rate": 0.025, "processing_time": 3600},
        "subscription": {"fee_rate": 0.015, "processing_time": 600}
    },
    "negotiation_strategies": {
        "aggressive": {"concession_rate": 0.02, "tolerance": 0.05},
        "balanced": {"concession_rate": 0.05, "tolerance": 0.10},
        "cooperative": {"concession_rate": 0.08, "tolerance": 0.15}
    }
}
```

## Monitoring and Logging

### Health Check Endpoints

```python
# Health check implementation
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {
            "reputation": await check_reputation_health(),
            "rewards": await check_rewards_health(),
            "trading": await check_trading_health(),
            "analytics": await check_analytics_health(),
            "certification": await check_certification_health()
        }
    }
```

### Metrics Collection

```python
# Prometheus metrics setup
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter('aitbc_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('aitbc_request_duration_seconds', 'Request duration')

# Business metrics
ACTIVE_AGENTS = Gauge('aitbc_active_agents', 'Number of active agents')
TRANSACTION_VOLUME = Gauge('aitbc_transaction_volume', 'Total transaction volume')
REPUTATION_SCORES = Histogram('aitbc_reputation_scores', 'Reputation score distribution')
```

### Log Configuration

```python
# logging.yaml
version: 1
disable_existing_loggers: false

formatters:
  json:
    format: '%(asctime)s %(name)s %(levelname)s %(message)s'
    class: pythonjsonlogger.jsonlogger.JsonFormatter

handlers:
  console:
    class: logging.StreamHandler
    formatter: json
    stream: ext://sys.stdout

  file:
    class: logging.handlers.RotatingFileHandler
    formatter: json
    filename: /var/log/aitbc/economics.log
    maxBytes: 10485760  # 10MB
    backupCount: 5

loggers:
  aitbc:
    level: INFO
    handlers: [console, file]
    propagate: false

root:
  level: INFO
  handlers: [console, file]
```

## Testing and Validation

### Pre-deployment Testing

```bash
# Run unit tests
pytest tests/unit/ -v --cov=app

# Run integration tests
pytest tests/integration/ -v --cov=app

# Run performance tests
pytest tests/performance/ -v --benchmark-only

# Run security tests
pytest tests/security/ -v
```

### Load Testing

```bash
# Install k6 for load testing
curl https://github.com/grafana/k6/releases/download/v0.47.0/k6-v0.47.0-linux-amd64.tar.gz -L | tar xvz

# Run load test
k6 run tests/load/api_load_test.js
```

### Data Validation

```python
# Data validation script
def validate_system_data():
    """Validate system data integrity"""
    
    validation_results = {
        "reputation_data": validate_reputation_data(),
        "reward_data": validate_reward_data(),
        "trading_data": validate_trading_data(),
        "analytics_data": validate_analytics_data(),
        "certification_data": validate_certification_data()
    }
    
    return all(validation_results.values())
```

## Security Considerations

### API Security

```python
# Security middleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*.aitbc.bubuit.net"])

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@app.get("/api/v1/reputation/{agent_id}")
@limiter.limit("100/minute")
async def get_reputation(agent_id: str):
    pass
```

### Database Security

```sql
-- Database security setup
CREATE ROLE aitbc_app WITH LOGIN PASSWORD 'secure_password';
CREATE ROLE aitbc_readonly WITH LOGIN PASSWORD 'readonly_password';

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aitbc_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aitbc_readonly;

-- Row level security
ALTER TABLE agent_reputations ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_reputation_policy ON agent_reputations
    FOR ALL TO aitbc_app
    USING (agent_id = current_setting('app.current_agent_id'));
```

### Blockchain Security

```python
# Blockchain security configuration
BLOCKCHAIN_CONFIG = {
    "contract_address": os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS"),
    "private_key": os.getenv("BLOCKCHAIN_PRIVATE_KEY"),
    "gas_limit": 300000,
    "gas_price": 20,  # gwei
    "confirmations_required": 2,
    "timeout_seconds": 300
}
```

## Backup and Recovery

### Database Backup

```bash
#!/bin/bash
# backup_database.sh

BACKUP_DIR="/var/backups/aitbc"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/economics_$DATE.sql"

# Create backup
pg_dump -h localhost -U aitbc_user -d aitbc_economics > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

# Remove old backups (keep last 7 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE.gz"
```

### Recovery Procedures

```bash
#!/bin/bash
# restore_database.sh

BACKUP_FILE=$1
RESTORE_DB="aitbc_economics_restore"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

# Create restore database
createdb $RESTORE_DB

# Restore from backup
gunzip -c $BACKUP_FILE | psql -h localhost -U aitbc_user -d $RESTORE_DB

echo "Database restored to $RESTORE_DB"
```

## Performance Optimization

### Database Optimization

```sql
-- Database performance tuning
-- PostgreSQL configuration recommendations

-- Memory settings
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

-- Connection settings
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

-- Logging settings
log_min_duration_statement = 1000
log_checkpoints = on
log_connections = on
log_disconnections = on
```

### Application Optimization

```python
# Performance optimization settings
PERFORMANCE_CONFIG = {
    "database_pool_size": 20,
    "database_max_overflow": 30,
    "cache_ttl": 3600,
    "batch_size": 1000,
    "async_tasks": True,
    "connection_timeout": 30,
    "query_timeout": 60
}
```

### Caching Strategy

```python
# Redis caching configuration
CACHE_CONFIG = {
    "reputation_cache_ttl": 3600,  # 1 hour
    "reward_cache_ttl": 1800,      # 30 minutes
    "trading_cache_ttl": 300,      # 5 minutes
    "analytics_cache_ttl": 600,    # 10 minutes
    "certification_cache_ttl": 7200 # 2 hours
}
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Check PostgreSQL status
   systemctl status postgresql
   
   # Check connection
   psql -h localhost -U aitbc_user -d aitbc_economics
   ```

2. **High Memory Usage**
   ```bash
   # Check memory usage
   free -h
   
   # Check process memory
   ps aux --sort=-%mem | head -10
   ```

3. **Slow API Responses**
   ```bash
   # Check API response times
   curl -w "@curl-format.txt" -o /dev/null -s "http://localhost:8000/health"
   ```

### Debug Mode

```python
# Enable debug mode
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

## Maintenance

### Regular Maintenance Tasks

```bash
#!/bin/bash
# maintenance.sh

# Database maintenance
psql -h localhost -U aitbc_user -d aitbc_economics -c "VACUUM ANALYZE;"

# Log rotation
logrotate -f /etc/logrotate.d/aitbc

# Cache cleanup
redis-cli FLUSHDB

# Health check
curl -f http://localhost:8000/health || echo "Health check failed"
```

### Scheduled Tasks

```cron
# /etc/cron.d/aitbc-maintenance
# Daily maintenance at 2 AM
0 2 * * * aitbc /opt/aitbc/scripts/maintenance.sh

# Weekly backup on Sunday at 3 AM
0 3 * * 0 aitbc /opt/aitbc/scripts/backup_database.sh

# Monthly performance report
0 4 1 * * aitbc /opt/aitbc/scripts/generate_performance_report.sh
```

## Rollback Procedures

### Application Rollback

```bash
# Rollback to previous version
systemctl stop aitbc-*
git checkout previous_version_tag
pip install -r requirements.txt
systemctl start aitbc-*
```

### Database Rollback

```bash
# Rollback database to previous backup
./restore_database.sh /var/backups/aitbc/economics_20260226_030000.sql.gz
```

## Support and Contact

### Support Channels

- **Technical Support**: support@aitbc.bubuit.net
- **Documentation**: https://docs.aitbc.bubuit.net
- **Status Page**: https://status.aitbc.bubuit.net
- **Community Forum**: https://community.aitbc.bubuit.net

### Emergency Contacts

- **Critical Issues**: emergency@aitbc.bubuit.net
- **Security Issues**: security@aitbc.bubuit.net
- **24/7 Hotline**: +1-555-123-4567

---

**Version**: 1.0.0  
**Last Updated**: February 26, 2026  
**Next Review**: March 26, 2026
