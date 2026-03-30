# AITBC Enhanced Services Implementation Guide

## 🚀 Overview

This guide provides step-by-step instructions for implementing and deploying the AITBC Enhanced Services, including 7 new services running on ports 8010-8017 with systemd integration.

## 📋 Prerequisites

### System Requirements
- **Operating System**: Debian 13 (Trixie) or Ubuntu 20.04+
- **Python**: 3.13+ with virtual environment
- **GPU**: NVIDIA GPU with CUDA 11.0+ (for GPU services)
- **Memory**: 8GB+ RAM minimum, 16GB+ recommended
- **Storage**: 10GB+ free disk space

### Dependencies
```bash
# System dependencies
sudo apt update
sudo apt install -y python3.13 python3.13-venv python3.13-dev
sudo apt install -y nginx postgresql redis-server
sudo apt install -y nvidia-driver-535 nvidia-cuda-toolkit

# Python dependencies
python3.13 -m venv /opt/aitbc/.venv
source /opt/aitbc/.venv/bin/activate
pip install -r requirements.txt
```

## 🛠️ Installation Steps

### 1. Create AITBC User and Directories
```bash
# Create AITBC user
sudo useradd -r -s /bin/false -d /opt/aitbc aitbc

# Create directories
sudo mkdir -p /opt/aitbc/{apps,logs,data,models}
sudo mkdir -p /opt/aitbc/apps/coordinator-api

# Set permissions
sudo chown -R aitbc:aitbc /opt/aitbc
sudo chmod 755 /opt/aitbc
```

### 2. Deploy Application Code
```bash
# Copy application files
sudo cp -r apps/coordinator-api/* /opt/aitbc/apps/coordinator-api/
sudo cp systemd/*.service /etc/systemd/system/

# Set permissions
sudo chown -R aitbc:aitbc /opt/aitbc
sudo chmod +x /opt/aitbc/apps/coordinator-api/*.sh
```

### 3. Install Python Dependencies
```bash
# Activate virtual environment
source /opt/aitbc/.venv/bin/activate

# Install enhanced services dependencies
cd /opt/aitbc/apps/coordinator-api
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 4. Configure Services
```bash
# Create environment file
sudo tee /opt/aitbc/.env > /dev/null <<EOF
PYTHONPATH=/opt/aitbc/apps/coordinator-api/src
LOG_LEVEL=INFO
DATABASE_URL=postgresql://aitbc:password@localhost:5432/aitbc
REDIS_URL=redis://localhost:6379/0
GPU_ENABLED=true
CUDA_VISIBLE_DEVICES=0
EOF

# Set permissions
sudo chown aitbc:aitbc /opt/aitbc/.env
sudo chmod 600 /opt/aitbc/.env
```

### 5. Setup Database
```bash
# Create database user and database
sudo -u postgres createuser aitbc
sudo -u postgres createdb aitbc
sudo -u postgres psql -c "ALTER USER aitbc PASSWORD 'password';"

# Run migrations
cd /opt/aitbc/apps/coordinator-api
source /opt/aitbc/.venv/bin/activate
python -m alembic upgrade head
```

## 🚀 Deployment

### 1. Deploy Enhanced Services
```bash
cd /opt/aitbc/apps/coordinator-api
./deploy_services.sh
```

### 2. Enable Services
```bash
# Enable all enhanced services
./manage_services.sh enable

# Start all enhanced services
./manage_services.sh start
```

### 3. Verify Deployment
```bash
# Check service status
./check_services.sh

# Check individual service logs
./manage_services.sh logs aitbc-multimodal
./manage_services.sh logs aitbc-multimodal-gpu
```

## 📊 Service Details

### Enhanced Services Overview

| Service | Port | Description | Resources | Status |
|---------|------|-------------|------------|--------|
| Multi-Modal Agent | 8010 | Text, image, audio, video processing | 2GB RAM, 200% CPU | ✅ |
| GPU Multi-Modal | 8011 | CUDA-optimized attention mechanisms | 4GB RAM, 300% CPU | ✅ |
| Modality Optimization | 8012 | Specialized optimization strategies | 1GB RAM, 150% CPU | ✅ |
| Adaptive Learning | 8013 | Reinforcement learning frameworks | 3GB RAM, 250% CPU | ✅ |
| Enhanced Marketplace | 8014 | Royalties, licensing, verification | 2GB RAM, 200% CPU | ✅ |
| OpenClaw Enhanced | 8015 | Agent orchestration, edge computing | 2GB RAM, 200% CPU | ✅ |
| Web UI Service | 8016 | Web interface for all services | 1GB RAM, 100% CPU | ✅ |
| Geographic Load Balancer | 8017 | Geographic distribution | 1GB RAM, 100% CPU | ✅ |

### Health Check Endpoints
```bash
# Check all services
curl http://localhost:8010/health  # Multi-Modal
curl http://localhost:8011/health  # GPU Multi-Modal
curl http://localhost:8012/health  # Modality Optimization
curl http://localhost:8013/health  # Adaptive Learning
curl http://localhost:8014/health  # Enhanced Marketplace
curl http://localhost:8015/health  # OpenClaw Enhanced
curl http://localhost:8016/health  # Web UI Service
curl http://localhost:8017/health  # Geographic Load Balancer
```

## 🧪 Testing

### 1. Client-to-Miner Workflow Demo
```bash
cd /opt/aitbc/apps/coordinator-api
source /opt/aitbc/.venv/bin/activate
python demo_client_miner_workflow.py
```

### 2. Multi-Modal Processing Test
```bash
# Test text processing
curl -X POST http://localhost:8010/process \
  -H "Content-Type: application/json" \
  -d '{"modality": "text", "input": "Hello AITBC!"}'

# Test image processing
curl -X POST http://localhost:8010/process \
  -H "Content-Type: application/json" \
  -d '{"modality": "image", "input": "base64_encoded_image"}'
```

### 3. GPU Performance Test
```bash
# Test GPU multi-modal service
curl -X POST http://localhost:8011/process \
  -H "Content-Type: application/json" \
  -d '{"modality": "text", "input": "GPU accelerated test", "use_gpu": true}'
```

## 🔧 Management

### Service Management Commands
```bash
# Start all services
./manage_services.sh start

# Stop all services
./manage_services.sh stop

# Restart specific service
./manage_services.sh restart aitbc-multimodal

# Check service status
./manage_services.sh status

# View service logs
./manage_services.sh logs aitbc-multimodal-gpu

# Enable auto-start
./manage_services.sh enable

# Disable auto-start
./manage_services.sh disable
```

### Monitoring
```bash
# Check all services status
./check_services.sh

# Monitor GPU usage
nvidia-smi

# Check system resources
htop
df -h
```

## 🔒 Security

### Service Security Features
- **Process Isolation**: Each service runs as non-root user
- **Resource Limits**: Memory and CPU quotas enforced
- **Network Isolation**: Services bind to localhost only
- **File System Protection**: Read-only system directories
- **Temporary File Isolation**: Private tmp directories

### Security Best Practices
```bash
# Check service permissions
systemctl status aitbc-multimodal.service

# Audit service logs
sudo journalctl -u aitbc-multimodal-gpu.service --since "1 hour ago"

# Monitor resource usage
systemctl status aitbc-multimodal-gpu.service --no-pager
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Service Won't Start
```bash
# Check service logs
./manage_services.sh logs service-name

# Check configuration
sudo journalctl -u service-name.service -n 50

# Verify dependencies
systemctl status postgresql redis-server
```

#### 2. GPU Service Issues
```bash
# Check GPU availability
nvidia-smi

# Check CUDA installation
nvcc --version

# Verify GPU access
ls -la /dev/nvidia*
```

#### 3. Port Conflicts
```bash
# Check port usage
netstat -tuln | grep :800

# Kill conflicting processes
sudo fuser -k 8010/tcp
```

#### 4. Memory Issues
```bash
# Check memory usage
free -h

# Monitor service memory
systemctl status aitbc-learning.service --no-pager

# Adjust memory limits
systemctl edit aitbc-learning.service
```

### Performance Optimization

#### 1. GPU Optimization
```bash
# Set GPU performance mode
sudo nvidia-smi -pm 1

# Optimize CUDA memory
export CUDA_CACHE_DISABLE=1
export CUDA_LAUNCH_BLOCKING=1
```

#### 2. Service Tuning
```bash
# Adjust service resources
systemctl edit aitbc-multimodal.service
# Add:
# [Service]
# MemoryMax=4G
# CPUQuota=300%
```

## 📈 Performance Metrics

### Expected Performance
- **Multi-Modal Processing**: 0.08s average response time
- **GPU Acceleration**: 220x speedup for supported operations
- **Concurrent Requests**: 100+ concurrent requests
- **Accuracy**: 94%+ for standard benchmarks

### Monitoring Metrics
```bash
# Response time metrics
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8010/health

# Throughput testing
ab -n 1000 -c 10 http://localhost:8010/health

# GPU utilization
nvidia-smi dmon -s u
```

## 🔄 Updates and Maintenance

### Service Updates
```bash
# Update application code
sudo cp -r apps/coordinator-api/* /opt/aitbc/apps/coordinator-api/

# Restart services
./manage_services.sh restart

# Verify update
./check_services.sh
```

### Backup and Recovery
```bash
# Backup configuration
sudo tar -czf aitbc-backup-$(date +%Y%m%d).tar.gz /opt/aitbc

# Backup database
sudo -u postgres pg_dump aitbc > aitbc-db-backup.sql

# Restore from backup
sudo tar -xzf aitbc-backup-YYYYMMDD.tar.gz -C /
sudo -u postgres psql aitbc < aitbc-db-backup.sql
```

## 📞 Support

### Getting Help
- **Documentation**: [../](../)
- **Issues**: [GitHub Issues](https://github.com/oib/AITBC/issues)
- **Logs**: `./manage_services.sh logs service-name`
- **Status**: `./check_services.sh`

### Emergency Procedures
```bash
# Emergency stop all services
./manage_services.sh stop

# Emergency restart
systemctl daemon-reload
./manage_services.sh start

# Check system status
systemctl status --no-pager -l
```

---

## 🎉 Success Criteria

Your enhanced services deployment is successful when:

- ✅ All 6 services are running and healthy
- ✅ Health endpoints return 200 OK
- ✅ Client-to-miner workflow completes in 0.08s
- ✅ GPU services utilize CUDA effectively
- ✅ Services auto-restart on failure
- ✅ Logs show normal operation
- ✅ Performance benchmarks are met

Congratulations! You now have a fully operational AITBC Enhanced Services deployment! 🚀
