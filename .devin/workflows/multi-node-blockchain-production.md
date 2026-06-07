---
description: Production deployment, security hardening, monitoring, and scaling strategies
title: Multi-Node Blockchain Setup - Production Module
version: 1.0
---

# Multi-Node Blockchain Setup - Production Module

This module covers production deployment, security hardening, monitoring, alerting, scaling strategies, and CI/CD integration for the multi-node AITBC blockchain network.

## Prerequisites

- Complete [Core Setup Module](multi-node-blockchain-setup-core.md)
- Complete [Operations Module](multi-node-blockchain-operations.md)
- Complete [Advanced Features Module](multi-node-blockchain-advanced.md)
- Stable and optimized blockchain network
- Production environment requirements

## Production Readiness Checklist

### Security Hardening

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Configure automatic security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades

# Harden SSH configuration
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
sudo tee /etc/ssh/sshd_config > /dev/null << 'EOF'
Port 22
Protocol 2
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
sudo systemctl restart ssh

# Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 8006/tcp
sudo ufw allow 7070/tcp
sudo ufw enable

# Install fail2ban
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
```

### System Security

```bash
# Create dedicated user for AITBC services
sudo useradd -r -s /bin/false aitbc
sudo usermod -L aitbc

# Secure file permissions
sudo chown -R aitbc:aitbc /var/lib/aitbc
sudo chmod 750 /var/lib/aitbc
sudo chmod 640 /var/lib/aitbc/data/ait-mainnet/*.db

# Secure keystore
sudo chmod 700 /var/lib/aitbc/keystore
sudo chmod 600 /var/lib/aitbc/keystore/*.json

# Configure log rotation
sudo tee /etc/logrotate.d/aitbc > /dev/null << 'EOF'
/var/log/aitbc/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 aitbc aitbc
    postrotate
        systemctl reload rsyslog || true
    endscript
}
EOF
```

### Service Configuration

```bash
# Create production systemd service files
sudo tee /etc/systemd/system/aitbc-blockchain-node-production.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Blockchain Node (Production)
After=network.target
Wants=network.target

[Service]
Type=simple
User=aitbc
Group=aitbc
WorkingDirectory=/opt/aitbc
Environment=PYTHONPATH=/opt/aitbc
EnvironmentFile=/etc/aitbc/.env
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.main
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
LimitNOFILE=65536
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/aitbc-blockchain-rpc-production.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Blockchain RPC Service (Production)
After=aitbc-blockchain-node-production.service
Requires=aitbc-blockchain-node-production.service

[Service]
Type=simple
User=aitbc
Group=aitbc
WorkingDirectory=/opt/aitbc
Environment=PYTHONPATH=/opt/aitbc
EnvironmentFile=/etc/aitbc/.env
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.app
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
LimitNOFILE=65536
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
EOF

# Enable production services
sudo systemctl daemon-reload
sudo systemctl enable aitbc-blockchain-node-production.service
sudo systemctl enable aitbc-blockchain-rpc-production.service
```

## Production Configuration

### Environment Optimization

```bash
# Production environment configuration
sudo tee /etc/aitbc/.env.production > /dev/null << 'EOF'
# Production Configuration
CHAIN_ID=ait-mainnet-prod
ENABLE_BLOCK_PRODUCTION=true
PROPOSER_ID=ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871

# Performance Tuning
BLOCK_TIME_SECONDS=5
MAX_TXS_PER_BLOCK=2000
MAX_BLOCK_SIZE_BYTES=4194304
MEMPOOL_MAX_SIZE=50000
MEMPOOL_MIN_FEE=5

# Security
RPC_TLS_ENABLED=true
RPC_TLS_CERT=/etc/aitbc/certs/server.crt
RPC_TLS_KEY=/etc/aitbc/certs/server.key
RPC_TLS_CA=/etc/aitbc/certs/ca.crt
AUDIT_LOG_ENABLED=true
AUDIT_LOG_PATH=/var/log/aitbc/audit.log

# Monitoring
METRICS_ENABLED=true
METRICS_PORT=9090
HEALTH_CHECK_INTERVAL=30

# Database
DB_PATH=/var/lib/aitbc/data/ait-mainnet/chain.db
DB_BACKUP_ENABLED=true
DB_BACKUP_INTERVAL=3600
DB_BACKUP_RETENTION=168

# Gossip
GOSSIP_BACKEND=redis
GOSSIP_BROADCAST_URL=redis://localhost:6379
GOSSIP_ENCRYPTION=true
EOF

# Generate TLS certificates
sudo mkdir -p /etc/aitbc/certs
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/aitbc/certs/server.key \
    -out /etc/aitbc/certs/server.crt \
    -subj "/C=US/ST=State/L=City/O=AITBC/OU=Blockchain/CN=localhost"

# Set proper permissions
sudo chown -R aitbc:aitbc /etc/aitbc/certs
sudo chmod 600 /etc/aitbc/certs/server.key
sudo chmod 644 /etc/aitbc/certs/server.crt
```

### Database Optimization

```bash
# Production database configuration
sudo systemctl stop aitbc-blockchain-node-production.service

# Optimize SQLite for production
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db << 'EOF'
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;  -- 256MB memory-mapped I/O
PRAGMA optimize;
VACUUM;
ANALYZE;
EOF

# Configure automatic backups
sudo tee /etc/cron.d/aitbc-backup > /dev/null << 'EOF'
# AITBC Production Backups
0 2 * * * aitbc /opt/aitbc/scripts/backup_database.sh
0 3 * * 0 aitbc /opt/aitbc/scripts/cleanup_old_backups.sh
EOF

sudo mkdir -p /var/backups/aitbc
sudo chown aitbc:aitbc /var/backups/aitbc
sudo chmod 750 /var/backups/aitbc
```

## Monitoring and Alerting

### Prometheus Monitoring

```bash
# Install Prometheus
sudo apt install prometheus -y

# Configure Prometheus for AITBC
sudo tee /etc/prometheus/prometheus.yml > /dev/null << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'aitbc-blockchain'
    static_configs:
      - targets: ['localhost:9090', '10.1.223.40:9090']
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['localhost:9100', '10.1.223.40:9100']
EOF

sudo systemctl enable prometheus
sudo systemctl start prometheus
```

### Grafana Dashboard

```bash
# Install Grafana
sudo apt install grafana -y
sudo systemctl enable grafana-server
sudo systemctl start grafana-server

# Create AITBC dashboard configuration
sudo tee /etc/grafana/provisioning/dashboards/aitbc-dashboard.json > /dev/null << 'EOF'
{
  "dashboard": {
    "title": "AITBC Blockchain Production",
    "panels": [
      {
        "title": "Block Height",
        "type": "stat",
        "targets": [
          {
            "expr": "aitbc_block_height",
            "refId": "A"
          }
        ]
      },
      {
        "title": "Transaction Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(aitbc_transactions_total[5m])",
            "refId": "B"
          }
        ]
      },
      {
        "title": "Node Status",
        "type": "table",
        "targets": [
          {
            "expr": "aitbc_node_up",
            "refId": "C"
          }
        ]
      }
    ]
  }
}
EOF
```

### Alerting Rules

```bash
# Create alerting rules
sudo tee /etc/prometheus/alert_rules.yml > /dev/null << 'EOF'
groups:
  - name: aitbc_alerts
    rules:
      - alert: NodeDown
        expr: up{job="aitbc-blockchain"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AITBC node is down"
          description: "AITBC blockchain node {{ $labels.instance }} has been down for more than 1 minute"

      - alert: HeightDifference
        expr: abs(aitbc_block_height{instance="localhost:9090"} - aitbc_block_height{instance="10.1.223.40:9090"}) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Blockchain height difference detected"
          description: "Height difference between nodes is {{ $value }} blocks"

      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanizePercentage }}"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes{mountpoint="/var/lib/aitbc"} / node_filesystem_size_bytes{mountpoint="/var/lib/aitbc"}) < 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space"
          description: "Disk space is {{ $value | humanizePercentage }} available"
EOF
```

## Scaling Strategies

### Horizontal Scaling

```bash
# Add new follower node
NEW_NODE_IP="10.1.223.41"

# Deploy to new node
ssh $NEW_NODE_IP "
# Clone repository
git clone https://github.com/aitbc/blockchain.git /opt/aitbc
cd /opt/aitbc

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy configuration
scp aitbc:/etc/aitbc/.env.production /etc/aitbc/.env

# Create data directories
sudo mkdir -p /var/lib/aitbc/data/ait-mainnet
sudo mkdir -p /var/lib/aitbc/keystore
sudo chown -R aitbc:aitbc /var/lib/aitbc

# Start services
sudo systemctl enable aitbc-blockchain-node-production.service
sudo systemctl enable aitbc-blockchain-rpc-production.service
sudo systemctl start aitbc-blockchain-node-production.service
sudo systemctl start aitbc-blockchain-rpc-production.service
"

# Update load balancer configuration
sudo tee /etc/nginx/nginx.conf > /dev/null << 'EOF'
upstream aitbc_rpc {
    server 10.1.223.93:8006 max_fails=3 fail_timeout=30s;
    server 10.1.223.40:8006 max_fails=3 fail_timeout=30s;
    server 10.1.223.41:8006 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name rpc.aitbc.io;
    
    location / {
        proxy_pass http://aitbc_rpc;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
EOF

sudo systemctl restart nginx
```

### Vertical Scaling

```bash
# Resource optimization for high-load scenarios
sudo tee /etc/systemd/system/aitbc-blockchain-node-production.service.d/override.conf > /dev/null << 'EOF'
[Service]
LimitNOFILE=1048576
LimitNPROC=1048576
MemoryMax=8G
CPUQuota=200%
EOF

# Optimize kernel parameters
sudo tee /etc/sysctl.d/99-aitbc-production.conf > /dev/null << 'EOF'
# Network optimization
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
net.ipv4.tcp_congestion_control = bbr

# File system optimization
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
EOF

sudo sysctl -p /etc/sysctl.d/99-aitbc-production.conf
```

## Load Balancing

### HAProxy Configuration

```bash
# Install HAProxy
sudo apt install haproxy -y

# Configure HAProxy for RPC load balancing
sudo tee /etc/haproxy/haproxy.cfg > /dev/null << 'EOF'
global
    daemon
    maxconn 4096

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

frontend aitbc_rpc_frontend
    bind *:8006
    default_backend aitbc_rpc_backend

backend aitbc_rpc_backend
    balance roundrobin
    option httpchk GET /health
    server aitbc1 10.1.223.93:8006 check
    server aitbc2 10.1.223.40:8006 check
    server aitbc3 10.1.223.41:8006 check

frontend aitbc_p2p_frontend
    bind *:7070
    default_backend aitbc_p2p_backend

backend aitbc_p2p_backend
    balance source
    server aitbc1 10.1.223.93:7070 check
    server aitbc2 10.1.223.40:7070 check
    server aitbc3 10.1.223.41:7070 check
EOF

sudo systemctl enable haproxy
sudo systemctl start haproxy
```

## CI/CD Integration

### GitHub Actions Pipeline

```yaml
# .github/workflows/production-deploy.yml
name: Production Deployment

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest
      - name: Run tests
        run: pytest tests/

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run security scan
        run: |
          pip install bandit safety
          bandit -r apps/
          safety check

  deploy-staging:
    needs: [test, security-scan]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to staging
        run: |
          # Deploy to staging environment
          ./scripts/deploy-staging.sh

  deploy-production:
    needs: [deploy-staging]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to production
        run: |
          # Deploy to production environment
          ./scripts/deploy-production.sh
```

### Deployment Scripts

```bash
# Create deployment scripts
cat > /opt/aitbc/scripts/deploy-production.sh << 'EOF'
#!/bin/bash
set -e

echo "Deploying AITBC to production..."

# Backup current version
BACKUP_DIR="/var/backups/aitbc/deploy-$(date +%Y%m%d-%H%M%S)"
mkdir -p $BACKUP_DIR
sudo cp -r /opt/aitbc $BACKUP_DIR/

# Update code
git pull origin main

# Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run database migrations
python -m aitbc_chain.migrate

# Restart services with zero downtime
sudo systemctl reload aitbc-blockchain-rpc-production.service
sudo systemctl restart aitbc-blockchain-node-production.service

# Health check
sleep 30
if curl -sf http://localhost:8006/health > /dev/null; then
    echo "Deployment successful!"
else
    echo "Deployment failed - rolling back..."
    sudo systemctl stop aitbc-blockchain-node-production.service aitbc-blockchain-rpc-production.service
    sudo cp -r $BACKUP_DIR/aitbc/* /opt/aitbc/
    sudo systemctl start aitbc-blockchain-node-production.service aitbc-blockchain-rpc-production.service
    exit 1
fi
EOF

chmod +x /opt/aitbc/scripts/deploy-production.sh
```

## Disaster Recovery

### Backup Strategy

```bash
# Create comprehensive backup script
cat > /opt/aitbc/scripts/backup_production.sh << 'EOF'
#!/bin/bash
set -e

BACKUP_DIR="/var/backups/aitbc/production-$(date +%Y%m%d-%H%M%S)"
mkdir -p $BACKUP_DIR

echo "Starting production backup..."

# Stop services gracefully
sudo systemctl stop aitbc-blockchain-node-production.service aitbc-blockchain-rpc-production.service

# Backup database
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db $BACKUP_DIR/
sudo cp /var/lib/aitbc/data/ait-mainnet/mempool.db $BACKUP_DIR/

# Backup keystore
sudo cp -r /var/lib/aitbc/keystore $BACKUP_DIR/

# Backup configuration
sudo cp /etc/aitbc/.env.production $BACKUP_DIR/
sudo cp -r /etc/aitbc/certs $BACKUP_DIR/

# Backup logs
sudo cp -r /var/log/aitbc $BACKUP_DIR/

# Create backup manifest
cat > $BACKUP_DIR/MANIFEST.txt << EOF
Backup created: $(date)
Blockchain height: $(curl -s http://localhost:8006/rpc/head | jq .height)
Git commit: $(git rev-parse HEAD)
System info: $(uname -a)
EOF

# Compress backup
tar -czf $BACKUP_DIR.tar.gz -C $(dirname $BACKUP_DIR) $(basename $BACKUP_DIR)
rm -rf $BACKUP_DIR

# Restart services
sudo systemctl start aitbc-blockchain-node-production.service aitbc-blockchain-rpc-production.service

echo "Backup completed: $BACKUP_DIR.tar.gz"
EOF

chmod +x /opt/aitbc/scripts/backup_production.sh
```

### Recovery Procedures

```bash
# Create recovery script
cat > /opt/aitbc/scripts/recover_production.sh << 'EOF'
#!/bin/bash
set -e

BACKUP_FILE=$1
if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

echo "Recovering from backup: $BACKUP_FILE"

# Stop services
sudo systemctl stop aitbc-blockchain-node-production.service aitbc-blockchain-rpc-production.service

# Extract backup
TEMP_DIR="/tmp/aitbc-recovery-$(date +%s)"
mkdir -p $TEMP_DIR
tar -xzf $BACKUP_FILE -C $TEMP_DIR

# Restore database
sudo cp $TEMP_DIR/*/chain.db /var/lib/aitbc/data/ait-mainnet/
sudo cp $TEMP_DIR/*/mempool.db /var/lib/aitbc/data/ait-mainnet/

# Restore keystore
sudo rm -rf /var/lib/aitbc/keystore
sudo cp -r $TEMP_DIR/*/keystore /var/lib/aitbc/

# Restore configuration
sudo cp $TEMP_DIR/*/.env.production /etc/aitbc/.env
sudo cp -r $TEMP_DIR/*/certs /etc/aitbc/

# Set permissions
sudo chown -R aitbc:aitbc /var/lib/aitbc
sudo chmod 600 /var/lib/aitbc/keystore/*.json

# Start services
sudo systemctl start aitbc-blockchain-node-production.service aitbc-blockchain-rpc-production.service

# Verify recovery
sleep 30
if curl -sf http://localhost:8006/health > /dev/null; then
    echo "Recovery successful!"
else
    echo "Recovery failed!"
    exit 1
fi

# Cleanup
rm -rf $TEMP_DIR
EOF

chmod +x /opt/aitbc/scripts/recover_production.sh
```

## Dependencies

This production module depends on:
- **[Core Setup Module](multi-node-blockchain-setup-core.md)** - Basic node setup
- **[Operations Module](multi-node-blockchain-operations.md)** - Daily operations knowledge
- **[Advanced Features Module](multi-node-blockchain-advanced.md)** - Advanced features understanding

## Next Steps

After mastering production deployment, proceed to:
- **[Marketplace Module](multi-node-blockchain-marketplace.md)** - Marketplace testing and verification
- **[Reference Module](multi-node-blockchain-reference.md)** - Configuration and verification reference

## Safety Notes

⚠️ **Critical**: Production deployment requires careful planning and testing.

- Always test in staging environment first
- Have disaster recovery procedures ready
- Monitor system resources continuously
- Keep security updates current
- Document all configuration changes
- Use proper change management procedures
