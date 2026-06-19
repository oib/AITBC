# Deployment Dependencies

**Last Updated:** 2026-06-19
**Version:** v0.5.0

## Overview

This document lists all system-level dependencies required for deploying AITBC in production. For Python package dependencies, see [Development Dependencies](../development/DEPENDENCIES.md).

## System Requirements

### Operating System

**Supported:**
- Debian 12 (Bookworm) or later
- Ubuntu 22.04 (Jammy) or later
- RHEL 9 or equivalent

**Minimum:**
- Linux kernel 5.15+
- systemd 247+

### Hardware Requirements

**Minimum (Single Server):**
- CPU: 4 cores (x86_64)
- RAM: 16 GB
- Disk: 100 GB SSD
- Network: 1 Gbps

**Recommended (Production):**
- CPU: 8+ cores
- RAM: 32 GB+
- Disk: 500 GB+ NVMe SSD
- Network: 10 Gbps

**Multi-Server Deployment:**
- Blockchain Node: 4 cores, 16 GB RAM, 200 GB SSD
- Coordinator API: 2 cores, 8 GB RAM, 50 GB SSD
- Agent Coordinator: 2 cores, 8 GB RAM, 50 GB SSD
- Governance Service: 2 cores, 8 GB RAM, 50 GB SSD
- Monitoring Stack: 2 cores, 8 GB RAM, 100 GB SSD

## Software Dependencies

### Core Dependencies

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| Python | 3.13+ | Runtime environment | `apt install python3.13 python3.13-venv` |
| PostgreSQL | 15+ | Primary database | `apt install postgresql-15` |
| Redis | 7+ | Caching and message broker | `apt install redis-server` |
| nginx | 1.24+ | Reverse proxy | `apt install nginx` |
| git | 2.40+ | Version control | `apt install git` |

### Optional Dependencies

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| Docker | 24+ | Containerization (optional) | `apt install docker.io` |
| Node.js | 20+ | Frontend build tools | `apt install nodejs npm` |
| certbot | Latest | SSL certificate management | `apt install certbot python3-certbot-nginx` |

### Development Tools (for deployment)

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| curl | Latest | HTTP client | `apt install curl` |
| wget | Latest | File download | `apt install wget` |
| jq | Latest | JSON processing | `apt install jq` |
| htop | Latest | System monitoring | `apt install htop` |
| net-tools | Latest | Network utilities | `apt install net-tools` |

## Service-Specific Dependencies

### Blockchain Node

**Required:**
- Python 3.13+
- PostgreSQL 15+ (for mempool storage)
- libpq-dev (PostgreSQL client library)

**Installation:**
```bash
apt install python3.13 python3.13-venv postgresql-15 libpq-dev
```

### Coordinator API

**Required:**
- Python 3.13+
- PostgreSQL 15+
- Redis 7+
- libpq-dev

**Installation:**
```bash
apt install python3.13 python3.13-venv postgresql-15 redis-server libpq-dev
```

### Agent Coordinator

**Required:**
- Python 3.13+
- Redis 7+

**Installation:**
```bash
apt install python3.13 python3.13-venv redis-server
```

### Governance Service

**Required:**
- Python 3.13+
- PostgreSQL 15+
- Redis 7+
- libpq-dev

**Installation:**
```bash
apt install python3.13 python3.13-venv postgresql-15 redis-server libpq-dev
```

### Monitoring Stack

**Required:**
- Prometheus 2.45+
- Grafana 10+
- Alertmanager 0.26+

**Installation:**
```bash
# Using official repositories
wget -qO- https://packages.grafana.com/gpg.key | apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" > /etc/apt/sources.list.d/grafana.list
apt update
apt install prometheus grafana alertmanager
```

## Database Configuration

### PostgreSQL

**Required Extensions:**
- pg_trgm (for text search)
- uuid-ossp (for UUID generation)

**Configuration:**
```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create databases
CREATE DATABASE aitbc;
CREATE DATABASE aitbc_governance;
CREATE DATABASE aitbc_mempool;

-- Create users
CREATE USER aitbc WITH PASSWORD '<secure_password>';
CREATE USER aitbc_governance WITH PASSWORD '<secure_password>';
CREATE USER aitbc_mempool WITH PASSWORD '<secure_password>';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aitbc TO aitbc;
GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;
GRANT ALL PRIVILEGES ON DATABASE aitbc_mempool TO aitbc_mempool;
```

**Performance Tuning:**
```ini
# /etc/postgresql/15/main/postgresql.conf
shared_buffers = 4GB
effective_cache_size = 12GB
maintenance_work_mem = 1GB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 2621kB
min_wal_size = 2GB
max_wal_size = 8GB
max_worker_processes = 8
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_parallel_maintenance_workers = 4
```

### Redis

**Configuration:**
```ini
# /etc/redis/redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfsync everysec
```

## Network Requirements

### Firewall Rules

**Required Ports:**

| Service | Port | Protocol | Direction | Purpose |
|---------|------|----------|-----------|---------|
| Coordinator API | 8000 | TCP | Inbound | API access |
| Agent Coordinator | 8100 | TCP | Inbound | Agent communication |
| Governance Service | 8105 | TCP | Inbound | Governance API |
| Blockchain Node | 8202 | TCP | Inbound | Blockchain RPC |
| Blockchain P2P | 8203 | TCP | Inbound/Outbound | P2P networking |
| PostgreSQL | 5432 | TCP | Local only | Database |
| Redis | 6379 | TCP | Local only | Cache |
| Prometheus | 9090 | TCP | Local only | Metrics |
| Grafana | 3000 | TCP | Inbound (VPN) | Monitoring |
| nginx | 80, 443 | TCP | Inbound | HTTP/HTTPS |

**UFW Configuration:**
```bash
# Allow SSH
ufw allow 22/tcp

# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Allow AITBC services (restrict to VPN in production)
ufw allow 8000/tcp
ufw allow 8100/tcp
ufw allow 8105/tcp
ufw allow 8202/tcp
ufw allow 8203/tcp

# Enable firewall
ufw enable
```

### DNS Requirements

**Required DNS Records:**

| Type | Name | Value | Purpose |
|------|------|-------|---------|
| A | api.aitbc.example.com | Server IP | Coordinator API |
| A | blockchain.aitbc.example.com | Server IP | Blockchain Node |
| A | governance.aitbc.example.com | Server IP | Governance Service |
| CNAME | www.aitbc.example.com | api.aitbc.example.com | Web interface |

## SSL/TLS Certificates

### Let's Encrypt (Recommended)

```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d api.aitbc.example.com -d blockchain.aitbc.example.com

# Auto-renewal is configured by default
certbot renew --dry-run
```

### Custom Certificates

Place certificates in:
- `/etc/ssl/certs/aitbc.crt`
- `/etc/ssl/private/aitbc.key`

Permissions:
```bash
chmod 644 /etc/ssl/certs/aitbc.crt
chmod 600 /etc/ssl/private/aitbc.key
```

## Storage Requirements

### Directory Structure

```
/opt/aitbc/              # Application code
/var/lib/aitbc/          # Runtime data
├── blockchain/          # Blockchain data
├── coordinator/        # Coordinator data
├── governance/         # Governance data
└── logs/               # Application logs
/etc/aitbc/             # Configuration
├── blockchain.env
├── coordinator.env
└── governance.env
/run/aitbc/secrets/     # Runtime secrets (tmpfs)
```

### Disk Space Allocation

| Directory | Minimum | Recommended | Purpose |
|-----------|---------|-------------|---------|
| /opt/aitbc | 10 GB | 20 GB | Application code |
| /var/lib/aitbc/blockchain | 50 GB | 200 GB | Blockchain data |
| /var/lib/aitbc/coordinator | 10 GB | 50 GB | Coordinator data |
| /var/lib/aitbc/governance | 10 GB | 50 GB | Governance data |
| /var/lib/postgresql | 20 GB | 100 GB | Database |
| /var/log/aitbc | 5 GB | 20 GB | Logs |

## Monitoring Dependencies

### System Monitoring

**Required:**
- Prometheus Node Exporter
- systemd

**Installation:**
```bash
apt install prometheus-node-exporter
systemctl enable prometheus-node-exporter
systemctl start prometheus-node-exporter
```

### Application Monitoring

**Required:**
- Prometheus (for metrics collection)
- Grafana (for visualization)

**Configuration:**
```yaml
# /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'aitbc'
    static_configs:
      - targets: ['localhost:8000', 'localhost:8100', 'localhost:8105', 'localhost:8202']
```

## Backup Dependencies

### Required Tools

- `pg_dump` (PostgreSQL backup)
- `redis-cli` (Redis backup)
- `rsync` (File backup)

**Installation:**
```bash
apt install postgresql-client redis-tools rsync
```

### Backup Script Dependencies

The backup script requires:
- Bash 4+
- gzip
- date utilities

## Security Dependencies

### Required

- `ufw` (firewall)
- `fail2ban` (intrusion prevention)
- `auditd` (audit logging)

**Installation:**
```bash
apt install ufw fail2ban auditd
```

### Optional

- `clamav` (antivirus)
- `rkhunter` (rootkit detection)

## Installation Verification

After installing all dependencies, run:

```bash
# Check Python
python3 --version  # Should be 3.13+

# Check PostgreSQL
sudo -u postgres psql --version  # Should be 15+

# Check Redis
redis-cli ping  # Should return PONG

# Check nginx
nginx -v  # Should be 1.24+

# Check services
systemctl status postgresql
systemctl status redis-server
systemctl status nginx
```

## Dependency Updates

### System Updates

```bash
# Update package list
apt update

# Upgrade packages
apt upgrade

# Security updates
apt upgrade -y --security
```

### PostgreSQL Updates

Follow official PostgreSQL upgrade guide:
https://www.postgresql.org/docs/migration.html

### Redis Updates

```bash
# Backup data
redis-cli BGSAVE

# Update
apt install --only-upgrade redis-server

# Verify
redis-cli ping
```

## Troubleshooting

### Missing Dependencies

```bash
# Check installed packages
dpkg -l | grep -E 'python|postgres|redis|nginx'

# Install missing
apt install python3.13 postgresql-15 redis-server nginx
```

### Version Conflicts

```bash
# Check Python version
python3 --version

# Use specific version
python3.13 --version
```

### Service Failures

```bash
# Check service status
systemctl status postgresql
systemctl status redis-server

# Check logs
journalctl -u postgresql -n 50
journalctl -u redis-server -n 50
```

## See Also

- [Development Dependencies](../development/DEPENDENCIES.md) - Python package dependencies
- [Single Server Deployment](single-server.md) - Complete deployment guide
- [Configuration Reference](configuration.md) - Environment configuration
- [Security Best Practices](../security/) - Security guidelines
