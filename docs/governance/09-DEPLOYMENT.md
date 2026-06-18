# Deployment

## Overview

This document covers deployment procedures for the Governance Service, including systemd service setup, database configuration, and production deployment.

## Prerequisites

- Python 3.13+
- PostgreSQL (for production) or SQLite (for development)
- Systemd service manager
- Nginx (optional, for reverse proxy)

## Development Deployment

### Local Development

1. **Clone repository:**
   ```bash
   cd /opt/aitbc
   ```

2. **Install dependencies:**
   ```bash
   poetry install --with governance
   ```

3. **Set up database:**
   ```bash
   mkdir -p /var/lib/aitbc/data
   ```

4. **Run migrations:**
   ```bash
   cd /opt/aitbc/apps/governance
   /opt/aitbc/venv/bin/alembic upgrade head
   ```

5. **Start service:**
   ```bash
   python -m governance_service.main
   ```

6. **Verify:**
   ```bash
   curl http://localhost:8105/health
   ```

## Production Deployment

### Systemd Service Setup

1. **Create service file:**
   ```bash
   sudo nano /etc/systemd/system/aitbc-governance.service
   ```

2. **Add service configuration:**
   ```ini
   [Unit]
   Description=AITBC Governance Service
   After=network.target postgresql.service

   [Service]
   Type=simple
   User=aitbc
   Group=aitbc
   WorkingDirectory=/opt/aitbc/apps/governance
   Environment="PATH=/opt/aitbc/venv/bin"
   Environment="DB_TYPE=postgresql"
   Environment="DB_HOST=localhost"
   Environment="DB_PORT=5432"
   Environment="DB_NAME=aitbc_governance"
   Environment="DB_USER=aitbc_governance"
   Environment="DB_PASS=your_secure_password"
   ExecStart=/opt/aitbc/venv/bin/python -m governance_service.main
   Restart=always
   RestartSec=10
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable aitbc-governance
   sudo systemctl start aitbc-governance
   ```

4. **Check status:**
   ```bash
   sudo systemctl status aitbc-governance
   ```

### PostgreSQL Setup

1. **Install PostgreSQL:**
   ```bash
   sudo apt update
   sudo apt install postgresql postgresql-contrib
   ```

2. **Create database and user:**
   ```bash
   sudo -u postgres psql
   ```

3. **Run SQL commands:**
   ```sql
   CREATE DATABASE aitbc_governance;
   CREATE USER aitbc_governance WITH PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;
   ALTER USER aitbc_governance CREATEDB;
   \q
   ```

4. **Configure PostgreSQL for remote access (optional):**
   ```bash
   sudo nano /etc/postgresql/*/main/postgresql.conf
   ```

   Add:
   ```ini
   listen_addresses = '*'
   ```

5. **Configure pg_hba.conf:**
   ```bash
   sudo nano /etc/postgresql/*/main/pg_hba.conf
   ```

   Add:
   ```
   host    aitbc_governance    aitbc_governance    0.0.0.0/0    md5
   ```

6. **Restart PostgreSQL:**
   ```bash
   sudo systemctl restart postgresql
   ```

### Database Migration

1. **Update alembic.ini:**
   ```bash
   cd /opt/aitbc/apps/governance
   nano alembic/alembic.ini
   ```

   Update:
   ```ini
   sqlalchemy.url = postgresql://aitbc_governance:your_secure_password@localhost:5432/aitbc_governance
   ```

2. **Run migrations:**
   ```bash
   /opt/aitbc/venv/bin/alembic upgrade head
   ```

3. **Verify migration:**
   ```bash
   /opt/aitbc/venv/bin/alembic current
   ```

### Nginx Reverse Proxy (Optional)

1. **Create Nginx configuration:**
   ```bash
   sudo nano /etc/nginx/sites-available/governance
   ```

2. **Add configuration:**
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

           # Timeouts
           proxy_connect_timeout 60s;
           proxy_send_timeout 60s;
           proxy_read_timeout 60s;
       }
   }
   ```

3. **Enable configuration:**
   ```bash
   sudo ln -s /etc/nginx/sites-available/governance /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

4. **Configure SSL (Let's Encrypt):**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d governance.aitbc.bubuit.net
   ```

## Smart Contract Deployment

### Prerequisites

- Foundry installed
- Testnet/Mainnet RPC endpoint
- Wallet with sufficient gas

### Deployment Steps

1. **Compile contracts:**
   ```bash
   cd /opt/aitbc/contracts/governance
   forge build
   ```

2. **Deploy AITBCGovernanceToken:**
   ```bash
   forge create src/AITBCGovernanceToken.sol:AITBCGovernanceToken \
     --rpc-url $RPC_URL \
     --private-key $PRIVATE_KEY \
     --verify
   ```

3. **Note the contract address**

4. **Deploy AITBCVoting:**
   ```bash
   forge create src/AITBCVoting.sol:AITBCVoting \
     --rpc-url $RPC_URL \
     --private-key $PRIVATE_KEY \
     --constructor-args <TOKEN_ADDRESS> \
     --verify
   ```

5. **Verify deployment:**
   ```bash
   cast call <TOKEN_ADDRESS> "totalSupply()" --rpc-url $RPC_URL
   cast call <VOTING_ADDRESS> "governanceToken()" --rpc-url $RPC_URL
   ```

6. **Update configuration:**
   ```bash
   export GOVERNANCE_TOKEN_ADDRESS=<TOKEN_ADDRESS>
   export VOTING_CONTRACT_ADDRESS=<VOTING_ADDRESS>
   ```

## Deployment Method

**AITBC deploys exclusively via systemd** and does not support Docker or containerization. All services are managed as systemd units for production deployments.

### Systemd Service Management

The governance service is managed via systemd:

```bash
# Start service
sudo systemctl start aitbc-governance

# Stop service
sudo systemctl stop aitbc-governance

# Restart service
sudo systemctl restart aitbc-governance

# Enable service at boot
sudo systemctl enable aitbc-governance

# View service status
sudo systemctl status aitbc-governance

# View service logs
sudo journalctl -u aitbc-governance -f
```

### Service Configuration

Service configuration is managed through:
- Systemd unit files in `/etc/systemd/system/`
- Environment files in `/etc/aitbc/`
- Configuration via environment variables

See the main deployment guide for complete systemd setup instructions.

## Monitoring

### Service Health Checks

```bash
# Health check
curl http://localhost:8105/health

# Readiness check
curl http://localhost:8105/ready

# Liveness check
curl http://localhost:8105/live
```

### Systemd Monitoring

```bash
# View service logs
sudo journalctl -u aitbc-governance -f

# View service status
sudo systemctl status aitbc-governance

# Restart service
sudo systemctl restart aitbc-governance
```

### Database Monitoring

```bash
# Check PostgreSQL connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Check database size
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('aitbc_governance'));"
```

## Backup and Recovery

### Database Backup

```bash
# PostgreSQL backup
sudo -u postgres pg_dump aitbc_governance > governance_backup_$(date +%Y%m%d).sql

# SQLite backup
cp /var/lib/aitbc/data/governance_service.db governance_backup_$(date +%Y%m%d).db
```

### Database Recovery

```bash
# PostgreSQL restore
sudo -u postgres psql aitbc_governance < governance_backup_20260607.sql

# SQLite restore
cp governance_backup_20260607.db /var/lib/aitbc/data/governance_service.db
```

### Automated Backups

Create cron job:
```bash
sudo crontab -e
```

Add:
```
0 2 * * * sudo -u postgres pg_dump aitbc_governance > /backups/governance_$(date +\%Y\%m\%d).sql
```

## Scaling

### Horizontal Scaling

1. **Deploy multiple instances:**
   - Use load balancer (Nginx, HAProxy)
   - Configure session management
   - Use shared database (PostgreSQL)

2. **Load balancer configuration:**
   ```nginx
   upstream governance {
       server localhost:8105;
       server localhost:8106;
       server localhost:8107;
   }

   server {
       location / {
           proxy_pass http://governance;
       }
   }
   ```

### Vertical Scaling

1. **Increase resources:**
   - More CPU cores
   - More RAM
   - Faster storage (SSD)

2. **Optimize database:**
   - Connection pooling
   - Query optimization
   - Index tuning

## Rollback Procedures

### Service Rollback

```bash
# Stop current version
sudo systemctl stop aitbc-governance

# Restore previous version
cd /opt/aitbc/apps/governance
git checkout <previous_version>

# Restart service
sudo systemctl start aitbc-governance
```

### Database Rollback

```bash
# Rollback migration
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic downgrade -1
```

## Production Checklist

- [ ] PostgreSQL installed and configured
- [ ] Database created and user configured
- [ ] Alembic migrations applied
- [ ] Systemd service configured and enabled
- [ ] Nginx reverse proxy configured (if using)
- [ ] SSL/TLS certificates configured (if using HTTPS)
- [ ] Firewall rules configured
- [ ] Monitoring and logging configured
- [ ] Backup procedures configured
- [ ] Smart contracts deployed (if using on-chain features)
- [ ] Environment variables configured
- [ ] Health checks verified
- [ ] Load testing performed

## References

- Service README: `/opt/aitbc/apps/governance/README.md`
- Configuration: [Configuration](08-CONFIGURATION.md)
- Troubleshooting: [Troubleshooting](11-TROUBLESHOOTING.md)
