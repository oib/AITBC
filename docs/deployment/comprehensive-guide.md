# Comprehensive Deployment Guide

This guide provides detailed instructions for deploying the AITBC platform in various scenarios.

> **Note:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md). For the current operational state and deployment status, see [Current Operational State](../infrastructure/CURRENT_OPERATIONAL_STATE.md).

## Table of Contents

- [Prerequisites](#prerequisites)
- [System Requirements](#system-requirements)
- [Deployment Scenarios](#deployment-scenarios)
- [Local Development Setup](#local-development-setup)
- [Single-Server Production Deployment](#single-server-production-deployment)
- [Multi-Server Deployment](#multi-server-deployment)
- [Cloud Deployment](#cloud-deployment)
- [Docker Containerized Deployment](#docker-containerized-deployment)
- [Configuration](#configuration)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Health Checks](#health-checks)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Software Requirements

- **Operating System**: Debian 12 (bookworm) or Ubuntu 22.04 LTS
- **Python**: 3.13 or higher
- **Node.js**: 24.14.0 or higher (for JavaScript SDK)
- **CUDA Toolkit**: 12.4 (for GPU support)
- **Docker**: 24.0 or higher (for containerized deployment)
- **Docker Compose**: 2.20 or higher

### Hardware Requirements

#### Minimum (Development)
- CPU: 4 cores
- RAM: 8 GB
- Storage: 100 GB SSD
- GPU: Not required for development

#### Recommended (Production)
- CPU: 8+ cores
- RAM: 16+ GB
- Storage: 500 GB NVMe SSD
- GPU: NVIDIA RTX 3090 or better (for mining)

#### Multi-Node
- Each node: 8+ cores, 16+ GB RAM, 100+ GB SSD
- GPU nodes: NVIDIA RTX 3090 or better
- Network: 10 Gbps interconnect

### Network Requirements

- Public IP address (for blockchain node)
- Open ports: 8006 (blockchain RPC), 7070 (P2P), 8011 (coordinator), 8015 (wallet), 8102 (marketplace)
- DNS configuration (optional but recommended)
- Firewall rules configured

> **Port Reference:** For complete port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## System Requirements

### Operating System

**Supported:**
- Debian 12 (bookworm)
- Ubuntu 22.04 LTS

**Recommended:**
- Debian 12 (bookworm) for production

### Dependencies

```bash
# System dependencies
sudo apt update
sudo apt install -y \
    build-essential \
    python3-dev \
    python3-venv \
    python3-pip \
    git \
    curl \
    wget \
    gnupg \
    lsb-release \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# CUDA dependencies (for GPU support)
sudo apt install -y \
    nvidia-cuda-toolkit \
    nvidia-cudnn \
    libnvidia-common
```

### Python Environment

```bash
# Create virtual environment
python3 -m venv /opt/aitbc/venv
source /opt/aitbc/venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

## Deployment Scenarios

### Scenario Comparison

| Scenario | Complexity | Scalability | Cost | Use Case |
|----------|-----------|-------------|------|----------|
| Local Development | Low | None | Low | Development, testing |
| Single-Server | Medium | Low | Low | Small deployments, POC |
| Multi-Server | High | High | High | Production, HA |
| Cloud | Medium | High | Variable | Flexible scaling |
| Docker | Medium | High | Variable | Container orchestration |

## Local Development Setup

### Quick Start

```bash
# Clone repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install local packages
pip install -e packages/py/aitbc-crypto
pip install -e packages/py/aitbc-sdk

# Start services
./scripts/setup.sh
```

### Service Configuration

```bash
# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start blockchain node
python -m apps.blockchain_node.main

# Start coordinator API
python -m apps.coordinator_api.main

# Start marketplace service
python -m apps.marketplace_service.main
```

### Verification

```bash
# Check service health
curl http://localhost:8006/health  # Blockchain RPC
curl http://localhost:8011/health  # Coordinator
curl http://localhost:8102/health  # Marketplace
```

## Single-Server Production Deployment

### Installation Steps

1. **Prepare Server**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Create user
sudo useradd -m -s /bin/bash aitbc
sudo usermod -aG docker aitbc
```

2. **Install Dependencies**

```bash
# Install system dependencies
sudo apt install -y \
    build-essential \
    python3-dev \
    python3-venv \
    git \
    curl \
    nginx \
    postgresql \
    redis-server \
    docker.io \
    docker-compose
```

3. **Deploy Application**

```bash
# Clone repository
sudo -u aitbc git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Setup virtual environment
sudo -u aitbc python3 -m venv /opt/aitbc/venv
sudo -u aitbc /opt/aitbc/venv/bin/pip install -r requirements.txt

# Setup database
sudo -u postgres psql -c "CREATE DATABASE aitbc;"
sudo -u postgres psql -c "CREATE USER aitbc WITH PASSWORD 'secure-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aitbc TO aitbc;"
```

4. **Configure Systemd Services**

```bash
# Setup services
sudo ./scripts/setup.sh

# Enable services
sudo systemctl enable aitbc-blockchain
sudo systemctl enable aitbc-coordinator-api
sudo systemctl enable aitbc-marketplace

# Start services
sudo systemctl start aitbc-blockchain
sudo systemctl start aitbc-coordinator-api
sudo systemctl start aitbc-marketplace
```

5. **Configure Nginx**

```nginx
# /etc/nginx/sites-available/aitbc
upstream coordinator {
    server 127.0.0.1:8011;
}

upstream blockchain {
    server 127.0.0.1:8006;
}

upstream marketplace {
    server 127.0.0.1:8102;
}

server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://coordinator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /blockchain/ {
        proxy_pass http://blockchain;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /marketplace/ {
        proxy_pass http://marketplace;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Multi-Server Deployment

### Architecture

```
                    Load Balancer
                         |
        +----------------+----------------+
        |                |                |
   Blockchain Node   Coordinator API   Marketplace
        |                |                |
        +----------------+----------------+
                         |
                   PostgreSQL Cluster
                         |
                   Redis Cluster
```

### Node Types

1. **Blockchain Node**
   - Runs blockchain consensus
   - Maintains ledger
   - Requires public IP

2. **Coordinator API**
   - Job submission and management
   - Payment processing
   - API gateway

3. **Marketplace Service**
   - GPU offer management
   - Matching engine
   - Price discovery

4. **Database Node**
   - PostgreSQL cluster
   - Redis cache
   - Data persistence

### Setup Steps

1. **Configure Network**

```bash
# On each node, configure network
sudo apt install -y etcd
sudo systemctl enable etcd
sudo systemctl start etcd
```

2. **Deploy Blockchain Node**

```bash
# On blockchain node
sudo apt install -y nvidia-cuda-toolkit
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/setup/blockchain.sh
```

3. **Deploy Coordinator API**

```bash
# On coordinator node
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/setup/coordinator.sh
```

4. **Deploy Marketplace Service**

```bash
# On marketplace node
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/setup/marketplace.sh
```

5. **Configure Database Cluster**

```bash
# On database node
sudo apt install -y postgresql redis-server
sudo -u postgres psql -c "CREATE DATABASE aitbc;"
```

## Cloud Deployment

### AWS Deployment

#### EC2 Setup

```bash
# Launch EC2 instances
- Blockchain: t3.xlarge or g4dn.xlarge (GPU)
- Coordinator: t3.large
- Marketplace: t3.large
- Database: RDS PostgreSQL

# Security groups
- Allow ports 8006, 7070, 8011, 8015, 8102
- Configure VPC and subnets
```

#### EKS Deployment

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: coordinator-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: coordinator-api
  template:
    metadata:
      labels:
        app: coordinator-api
    spec:
      containers:
      - name: coordinator-api
        image: aitbc/coordinator-api:latest
        ports:
        - containerPort: 8011
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-secret
              key: url
```

### GCP Deployment

#### GKE Setup

```bash
# Create GKE cluster
gcloud container clusters create aitbc-cluster \
    --num-nodes=3 \
    --machine-type=n1-standard-4 \
    --zone=us-central1-a

# Deploy services
kubectl apply -f kubernetes/
```

## Docker Containerized Deployment

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  blockchain:
    build: ./apps/blockchain_node
    ports:
      - "8006:8006"
    volumes:
      - blockchain-data:/data
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/aitbc

  coordinator:
    build: ./apps/coordinator-api
    ports:
      - "8011:8011"
    depends_on:
      - blockchain
      - postgres
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/aitbc

  marketplace:
    build: ./apps/marketplace_service
    ports:
      - "8102:8102"
    depends_on:
      - postgres
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/aitbc

  postgres:
    image: postgres:15
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=aitbc
      - POSTGRES_USER=aitbc
      - POSTGRES_PASSWORD=secure-password

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  blockchain-data:
  postgres-data:
```

### Build and Run

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## Configuration

### Environment Variables

```bash
# /etc/aitbc/blockchain.env
BLOCKCHAIN_NETWORK_ID=1
BLOCKCHAIN_GENESIS_BLOCK_HASH=0x...
BLOCKCHAIN_CONSENSUS_ALGORITHM=proof_of_stake
BLOCKCHAIN_VALIDATOR_PRIVATE_KEY=0x...

# /etc/aitbc/coordinator.env
COORDINATOR_API_KEY=your-api-key
COORDINATOR_DATABASE_URL=postgresql://user:pass@localhost:5432/aitbc
COORDINATOR_REDIS_URL=redis://localhost:6379
COORDINATOR_JWT_SECRET=your-jwt-secret

# /etc/aitbc/marketplace.env
MARKETPLACE_DATABASE_URL=postgresql://user:pass@localhost:5432/aitbc
MARKETPLACE_REDIS_URL=redis://localhost:6379
MARKETPLACE_API_KEY=your-api-key
```

### Configuration Files

```yaml
# /etc/aitbc/config.yaml
services:
  blockchain:
    port: 8006
    host: 0.0.0.0
    database:
      host: localhost
      port: 5432
      name: aitbc

  coordinator:
    port: 8011
    host: 0.0.0.0
    database:
      host: localhost
      port: 5432
      name: aitbc
    cache:
      host: localhost
      port: 6379

  marketplace:
    port: 8102
    host: 0.0.0.0
    database:
      host: localhost
      port: 5432
      name: aitbc
```

## SSL/TLS Configuration

### Let's Encrypt

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### Manual Certificate

```bash
# Generate self-signed certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/aitbc.key \
  -out /etc/ssl/certs/aitbc.crt

# Configure Nginx
sudo nano /etc/nginx/sites-available/aitbc
```

### Nginx SSL Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/aitbc.crt;
    ssl_certificate_key /etc/ssl/private/aitbc.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://localhost:8011;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## Health Checks

### Service Health Endpoints

```bash
# Blockchain health
curl http://localhost:8006/health

# Coordinator health
curl http://localhost:8011/health

# Marketplace health
curl http://localhost:8102/health
```

### Monitoring Script

```bash
#!/bin/bash
# health-check.sh

services=("blockchain:8006" "coordinator:8011" "marketplace:8102")

for service in "${services[@]}"; do
    name="${service%%:*}"
    port="${service##*:}"
    
    if curl -f "http://localhost:$port/health" > /dev/null 2>&1; then
        echo "✓ $name is healthy"
    else
        echo "✗ $name is unhealthy"
        # Send alert
    fi
done
```

### Systemd Health Monitoring

```ini
# /etc/systemd/system/aitbc-health-check.service
[Unit]
Description=AITBC Health Check
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/aitbc/scripts/health-check.sh

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check logs
sudo journalctl -u aitbc-coordinator-api -n 50

# Check port conflicts
sudo netstat -tulpn | grep -E '8006|7070|8011|8102'

# Check permissions
sudo -u aitbc ls -la /opt/aitbc
```

#### Database Connection Failed

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connection
psql -h localhost -U aitbc -d aitbc

# Check firewall
sudo ufw status
```

#### GPU Not Detected

```bash
# Check GPU
nvidia-smi

# Check CUDA
nvcc --version

# Check driver
sudo dmesg | grep -i nvidia
```

### Performance Issues

#### High CPU Usage

```bash
# Check process CPU
top -p $(pgrep -f coordinator-api)

# Profile with cProfile
python -m cProfile -o profile.stats apps/coordinator_api/main.py
```

#### High Memory Usage

```bash
# Check memory
free -h

# Check process memory
ps aux | grep coordinator-api

# Check for memory leaks
valgrind --leak-check=full python apps/coordinator_api/main.py
```

### Network Issues

#### Connection Refused

```bash
# Check service status
sudo systemctl status aitbc-coordinator-api

# Check firewall
sudo iptables -L -n

# Check network
ping localhost
telnet localhost 8011
```

#### Slow Performance

```bash
# Check network latency
ping -c 10 localhost

# Check bandwidth
iperf3 -s
iperf3 -c localhost

# Check DNS
nslookup your-domain.com
```

## Maintenance

### Backup

```bash
# Database backup
sudo -u postgres pg_dump aitbc > backup-$(date +%Y%m%d).sql

# Blockchain data backup
tar -czf blockchain-backup-$(date +%Y%m%d).tar.gz /var/lib/aitbc/blockchain

# Configuration backup
tar -czf config-backup-$(date +%Y%m%d).tar.gz /etc/aitbc
```

### Updates

```bash
# Update application
cd /opt/aitbc
git pull origin main
source venv/bin/activate
pip install -r requirements.txt

# Restart services
sudo systemctl restart aitbc-coordinator-api
sudo systemctl restart aitbc-blockchain
sudo systemctl restart aitbc-marketplace
```

### Monitoring

```bash
# Check service logs
sudo journalctl -u aitbc-coordinator-api -f

# Check system metrics
htop

# Check network
iftop
```
