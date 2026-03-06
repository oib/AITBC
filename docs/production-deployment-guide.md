# AITBC Production Deployment Guide

## 🚀 Production Deployment Readiness Checklist

### ✅ Pre-Deployment Requirements
- [ ] All development tasks completed
- [ ] All tests passing (unit, integration, performance, security)
- [ ] CI/CD pipeline configured and tested
- [ ] Infrastructure provisioned (servers, databases, networking)
- [ ] Security certificates and SSL configured
- [ ] Monitoring and alerting systems set up
- [ ] Backup and disaster recovery plans in place
- [ ] Team training and documentation complete

---

## 📋 Production Deployment Steps

### Phase 1: Infrastructure Preparation

#### 1.1 Server Infrastructure
```bash
# Production servers (minimum requirements)
# Application Servers: 4x 8-core, 16GB RAM, 500GB SSD
# Database Servers: 2x 16-core, 64GB RAM, 1TB SSD (primary + replica)
# Load Balancers: 2x 4-core, 8GB RAM
# Monitoring: 1x 4-core, 8GB RAM, 200GB SSD

# Network Configuration
# - Load balancer with SSL termination
# - Application servers behind load balancer
# - Database in private network
# - Redis cluster for caching
# - CDN for static assets
```

#### 1.2 Database Setup
```bash
# PostgreSQL Production Setup
sudo -u postgres psql
CREATE DATABASE aitbc_prod;
CREATE USER aitbc_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_prod TO aitbc_user;

# Redis Production Setup
redis-server --port 6379 --requirepass 'redis_password' --maxmemory 4gb --maxmemory-policy allkeys-lru
```

#### 1.3 SSL Certificates
```bash
# Generate SSL certificates (Let's Encrypt)
sudo certbot --nginx -d aitbc.dev -d api.aitbc.dev -d marketplace.aitbc.dev
```

### Phase 2: Application Deployment

#### 2.1 Deploy Core Services
```bash
# Clone production branch
git clone https://github.com/aitbc/aitbc.git /opt/aitbc
cd /opt/aitbc
git checkout production

# Set environment variables
export NODE_ENV=production
export DATABASE_URL=postgresql://aitbc_user:secure_password@localhost:5432/aitbc_prod
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET=your_jwt_secret_here
export ENCRYPTION_KEY=your_encryption_key_here

# Build and deploy services
./scripts/deploy.sh production latest us-east-1
```

#### 2.2 Service Configuration
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: aitbc_prod
      POSTGRES_USER: aitbc_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: unless-stopped
    
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    restart: unless-stopped
    
  blockchain-node:
    image: aitbc/blockchain-node:latest
    environment:
      - NODE_ENV=production
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    ports:
      - "8007:8007"
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      
  # ... other services
```

#### 2.3 Load Balancer Configuration
```nginx
# /etc/nginx/sites-available/aitbc-prod
upstream aitbc_api {
    server 10.0.1.10:8001 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8001 max_fails=3 fail_timeout=30s;
}

upstream aitbc_exchange {
    server 10.0.1.10:8010 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8010 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name api.aitbc.dev;
    
    ssl_certificate /etc/letsencrypt/live/api.aitbc.dev/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.aitbc.dev/privkey.pem;
    
    location / {
        proxy_pass http://aitbc_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Phase 3: Monitoring Setup

#### 3.1 Prometheus Configuration
```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'aitbc-services'
    static_configs:
      - targets: 
        - 'localhost:8001'  # coordinator-api
        - 'localhost:8010'  # exchange-integration
        - 'localhost:8012'  # trading-engine
        - 'localhost:8013'  # plugin-registry
        - 'localhost:8014'  # plugin-marketplace
        - 'localhost:8017'  # global-infrastructure
        - 'localhost:8018'  # ai-agents
```

#### 3.2 Grafana Dashboards
```bash
# Import pre-configured dashboards
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @monitoring/grafana/dashboards/aitbc-overview.json \
  http://localhost:3000/api/dashboards/db
```

### Phase 4: Security Configuration

#### 4.1 Firewall Setup
```bash
# UFW Configuration
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow from 10.0.0.0/8 to any port 5432  # Database access
sudo ufw allow from 10.0.0.0/8 to any port 6379  # Redis access
sudo ufw enable
```

#### 4.2 Application Security
```bash
# Set secure file permissions
chmod 600 /opt/aitbc/.env
chmod 700 /opt/aitbc/.aitbc
chown -R aitbc:aitbc /opt/aitbc

# Configure log rotation
sudo tee /etc/logrotate.d/aitbc << EOF
/opt/aitbc/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 aitbc aitbc
    postrotate
        systemctl reload aitbc-services
    endscript
}
EOF
```

### Phase 5: Backup Strategy

#### 5.1 Database Backups
```bash
#!/bin/bash
# /opt/aitbc/scripts/backup-db.sh
BACKUP_DIR="/opt/aitbc/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="aitbc_prod"

# Create backup
pg_dump -h localhost -U aitbc_user -d $DB_NAME | gzip > $BACKUP_DIR/aitbc_backup_$DATE.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "aitbc_backup_*.sql.gz" -mtime +30 -delete

# Upload to cloud storage (AWS S3 example)
aws s3 cp $BACKUP_DIR/aitbc_backup_$DATE.sql.gz s3://aitbc-backups/database/
```

#### 5.2 Application Backups
```bash
#!/bin/bash
# /opt/aitbc/scripts/backup-app.sh
BACKUP_DIR="/opt/aitbc/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup application data
tar -czf $BACKUP_DIR/aitbc_app_backup_$DATE.tar.gz \
    /opt/aitbc/data \
    /opt/aitbc/.aitbc \
    /opt/aitbc/config

# Upload to cloud storage
aws s3 cp $BACKUP_DIR/aitbc_app_backup_$DATE.tar.gz s3://aitbc-backups/application/
```

### Phase 6: Health Checks and Monitoring

#### 6.1 Service Health Check Script
```bash
#!/bin/bash
# /opt/aitbc/scripts/health-check.sh

services=(
    "coordinator-api:8001"
    "exchange-integration:8010"
    "trading-engine:8012"
    "plugin-registry:8013"
    "plugin-marketplace:8014"
    "global-infrastructure:8017"
    "ai-agents:8018"
)

for service in "${services[@]}"; do
    name=$(echo $service | cut -d: -f1)
    port=$(echo $service | cut -d: -f2)
    
    if curl -f -s http://localhost:$port/health > /dev/null; then
        echo "✅ $name is healthy"
    else
        echo "❌ $name is unhealthy"
        # Send alert
        curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"🚨 AITBC Alert: '$name' is unhealthy"}' \
            $SLACK_WEBHOOK_URL
    fi
done
```

#### 6.2 Performance Monitoring
```bash
#!/bin/bash
# /opt/aitbc/scripts/performance-monitor.sh

# Monitor CPU and memory
cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
memory_usage=$(free | grep Mem | awk '{printf("%.1f", $3/$2 * 100.0)}')

# Monitor disk space
disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

# Send alerts if thresholds exceeded
if (( $(echo "$cpu_usage > 80" | bc -l) )); then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"🚨 High CPU usage: '$cpu_usage'%"}' \
        $SLACK_WEBHOOK_URL
fi

if (( $(echo "$memory_usage > 85" | bc -l) )); then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"🚨 High memory usage: '$memory_usage'%"}' \
        $SLACK_WEBHOOK_URL
fi

if (( disk_usage > 90 )); then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"🚨 High disk usage: '$disk_usage'%"}' \
        $SLACK_WEBHOOK_URL
fi
```

### Phase 7: Deployment Automation

#### 7.1 Zero-Downtime Deployment
```bash
#!/bin/bash
# /opt/aitbc/scripts/zero-downtime-deploy.sh

NEW_VERSION=$1
CURRENT_VERSION=$(docker service ls --format '{{.Image}}' | head -1 | cut -d: -f2)

echo "Deploying version: $NEW_VERSION"
echo "Current version: $CURRENT_VERSION"

# Pull new images
docker pull aitbc/coordinator-api:$NEW_VERSION
docker pull aitbc/exchange-integration:$NEW_VERSION
docker pull aitbc/trading-engine:$NEW_VERSION

# Update services one by one
services=("coordinator-api" "exchange-integration" "trading-engine")

for service in "${services[@]}"; do
    echo "Updating $service..."
    
    # Scale up to ensure availability
    docker service scale $service=2
    
    # Update one instance
    docker service update \
        --image aitbc/$service:$NEW_VERSION \
        --update-parallelism 1 \
        --update-delay 30s \
        $service
    
    # Wait for update to complete
    docker service ps $service --format "{{.CurrentState}}" | grep -q "Running"
    
    # Scale back down
    docker service scale $service=1
    
    echo "$service updated successfully"
done

echo "Deployment completed!"
```

### Phase 8: Post-Deployment Verification

#### 8.1 Smoke Tests
```bash
#!/bin/bash
# /opt/aitbc/scripts/smoke-tests.sh

echo "Running smoke tests..."

# Test API endpoints
endpoints=(
    "http://api.aitbc.dev/health"
    "http://api.aitbc.dev/api/v1/pairs"
    "http://marketplace.aitbc.dev/api/v1/marketplace/featured"
    "http://api.aitbc.dev/api/v1/network/dashboard"
)

for endpoint in "${endpoints[@]}"; do
    if curl -f -s $endpoint > /dev/null; then
        echo "✅ $endpoint is responding"
    else
        echo "❌ $endpoint is not responding"
        exit 1
    fi
done

# Test CLI functionality
docker exec aitbc-cli python -m aitbc_cli.main --version > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ CLI is working"
else
    echo "❌ CLI is not working"
    exit 1
fi

echo "All smoke tests passed!"
```

#### 8.2 Load Testing
```bash
#!/bin/bash
# /opt/aitbc/scripts/load-test.sh

echo "Running load tests..."

# Test API load
ab -n 1000 -c 10 http://api.aitbc.dev/health

# Test marketplace load
ab -n 500 -c 5 http://marketplace.aitbc.dev/api/v1/marketplace/featured

echo "Load tests completed!"
```

---

## 📊 Production Deployment Success Metrics

### Key Performance Indicators
- **Uptime**: > 99.9%
- **Response Time**: < 200ms (95th percentile)
- **Error Rate**: < 0.1%
- **Throughput**: > 1000 requests/second
- **Database Performance**: < 100ms query time
- **Memory Usage**: < 80% of available memory
- **CPU Usage**: < 70% of available CPU

### Monitoring Alerts
- **Service Health**: All services healthy
- **Performance**: Response times within SLA
- **Security**: No security incidents
- **Resources**: Resource usage within limits
- **Backups**: Daily backups successful

---

## 🎯 Production Deployment Complete!

**🚀 AITBC is now running in production!**

### What's Next?
1. **Monitor System Performance**: Keep an eye on all metrics
2. **User Onboarding**: Start bringing users to the platform
3. **Plugin Marketplace**: Launch plugin ecosystem
4. **Community Building**: Grow the developer community
5. **Continuous Improvement**: Monitor, optimize, and enhance

### Support Channels
- **Technical Support**: support@aitbc.dev
- **Documentation**: docs.aitbc.dev
- **Status Page**: status.aitbc.dev
- **Community**: community.aitbc.dev

**🎊 Congratulations! AITBC is now live in production!**
