# Debian Stable Miner Installation Guide

**Last Updated:** 2026-05-28

This guide provides step-by-step instructions for installing the AITBC miner on Debian stable (trixie).

## Prerequisites

### System Requirements

- **Operating System**: Debian 13 (trixie) or Ubuntu 24.04 LTS
- **GPU**: NVIDIA GPU with CUDA 12.4+ support
- **Memory**: 16GB+ RAM recommended
- **Storage**: 100GB+ SSD
- **Network**: Stable internet connection

### Hardware Compatibility

Tested GPUs:
- NVIDIA RTX 3090
- NVIDIA RTX 4090
- NVIDIA RTX 4060 Ti
- NVIDIA A100
- NVIDIA H100

Other NVIDIA GPUs with CUDA 12.4+ support should work but may not be tested.

## Pre-Installation

### 1. Update System

```bash
apt update
apt upgrade -y
apt autoremove -y
```

### 2. Install NVIDIA Drivers

```bash
# Install NVIDIA driver
apt install -y nvidia-driver-full

# Reboot
reboot
```

### 3. Verify GPU

After reboot, verify GPU is detected:

```bash
nvidia-smi
```

Expected output:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.0.00    Driver Version: 535.0.00    CUDA Version: 12.4 |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ...  On   | 00000000:01:00.0  On |                  N/A |
|  30%   42C    P8    13W / 350W |    521MiB / 16384MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

### 4. Install CUDA Toolkit

```bash
# Install CUDA Toolkit
apt install -y nvidia-cuda-toolkit

# Verify installation
nvcc --version
```

### 5. Install Ollama (Optional - for Ollama backend)

Ollama is required only if using the Ollama inference backend. The miner includes vLLM for optimized inference, which is recommended.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull a model (in another terminal)
ollama pull llama2
```

**Note:** vLLM is included in the binary and provides better performance. To use vLLM, set `INFERENCE_BACKEND=vllm` in the configuration.

### 6. Verify Ollama

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Expected output:
# {"models":[{"name":"llama2:7b","modified":"..."}]}
```

## Installation

### Option 1: Using Installation Script (Recommended)

```bash
# Download the release package
wget https://github.com/oib/AITBC/releases/download/v0.1.0/aitbc-miner-debian-package.tar.gz

# Extract
tar -xzf aitbc-miner-debian-package.tar.gz
cd aitbc-miner-debian

# Run installation script
./install.sh
```

### Option 2: Manual Installation

#### Step 1: Download Binary

```bash
# Download binary
wget https://github.com/oib/AITBC/releases/download/v0.1.0/aitbc-miner-debian

# Download checksums
wget https://github.com/oib/AITBC/releases/download/v0.1.0/SHA256SUMS

# Verify checksum
sha256sum -c SHA256SUMS

# Make executable
chmod +x aitbc-miner-debian
```

#### Step 2: Create User

```bash
useradd -m -s /bin/bash aitbc
```

#### Step 3: Create Installation Directory

```bash
mkdir -p /opt/aitbc/miner
chown aitbc:aitbc /opt/aitbc/miner
```

#### Step 4: Copy Binary

```bash
cp aitbc-miner-debian /opt/aitbc/miner/
chmod +x /opt/aitbc/miner/aitbc-miner-debian
chown aitbc:aitbc /opt/aitbc/miner/aitbc-miner-debian
```

#### Step 5: Create Configuration

```bash
-u aitbc nano /opt/aitbc/miner/miner.env
```

Add the following configuration:

```bash
# Required
MINER_API_KEY=your-miner-api-key
COORDINATOR_URL=http://your-coordinator-url:8011

# Optional
LOG_PATH=/var/log/aitbc/miner.log
HEARTBEAT_INTERVAL=15
MAX_RETRIES=10
RETRY_DELAY=30
```

#### Step 6: Create Log Directory

```bash
mkdir -p /var/log/aitbc
chown aitbc:aitbc /var/log/aitbc
```

#### Step 7: Create Systemd Service

```bash
nano /etc/systemd/system/aitbc-miner.service
```

Add the following:

```ini
[Unit]
Description=AITBC GPU Miner
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/miner
EnvironmentFile=/opt/aitbc/miner/miner.env
ExecStart=/opt/aitbc/miner/aitbc-miner-debian
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### Step 8: Enable and Start Service

```bash
systemctl daemon-reload
systemctl enable aitbc-miner
systemctl start aitbc-miner
```

## Configuration

### Get Miner API Key

Register as a miner with the Coordinator API:

```bash
curl -X POST http://your-coordinator-url:8011/v1/miners/register \
  -H "Content-Type: application/json" \
  -d '{
    "miner_id": "your-miner-id",
    "gpu_type": "nvidia-rtx-3090",
    "gpu_memory": 24
  }'
```

The response will include your API key.

### Configure Coordinator URL

Set the Coordinator URL in `/opt/aitbc/miner/miner.env`:

```bash
COORDINATOR_URL=http://your-coordinator-url:8011
```

## Verification

### Run Verification Script

```bash
cd /opt/aitbc/miner
./verify-install.sh
```

The script will check:
- Binary integrity
- GPU detection
- CUDA installation
- Ollama status
- Configuration
- Systemd service

### Check Service Status

```bash
systemctl status aitbc-miner
```

Expected output:
```
● aitbc-miner.service - AITBC GPU Miner
     Loaded: loaded (/etc/systemd/system/aitbc-miner.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2026-05-11 12:00:00 UTC
   Main PID: 12345 (aitbc-miner-deb)
      Tasks: 1 (limit: 4915)
     Memory: 150.0M
        CPU: 2.3%
```

### View Logs

```bash
# Real-time logs
journalctl -u aitbc-miner -f

# Last 100 lines
journalctl -u aitbc-miner -n 100
```

Expected log output:
```
2026-05-11 12:00:00 - INFO - Starting Real GPU Miner Client on Host...
2026-05-11 12:00:00 - INFO - GPU detected: NVIDIA GeForce RTX 4060 Ti (16380MB)
2026-05-11 12:00:00 - INFO - Ollama models available: llama2:7b, gemma4:31b-cloud
2026-05-11 12:00:00 - INFO - Coordinator is available!
2026-05-11 12:00:00 - INFO - Successfully registered miner
2026-05-11 12:00:00 - INFO - Miner registered successfully, starting main loop...
```

### Check Miner Registration

```bash
curl -H "X-Api-Key: your-miner-api-key" \
  http://your-coordinator-url:8011/v1/miners/your-miner-id
```

## Troubleshooting

### GPU Not Detected

**Problem**: Miner cannot detect GPU

**Solution**:
```bash
# Check GPU
nvidia-smi

# Reinstall drivers
apt install --reinstall nvidia-driver-535

# Check kernel modules
lsmod | grep nvidia

# Reboot
reboot
```

### Ollama Not Available

**Problem**: Miner cannot connect to Ollama

**Solution**:
```bash
# Check Ollama status
systemctl status ollama

# Start Ollama manually
ollama serve

# Check Ollama is listening
netstat -tulpn | grep 11434
```

### Coordinator Connection Failed

**Problem**: Miner cannot connect to Coordinator

**Solution**:
```bash
# Test Coordinator URL
curl http://your-coordinator-url:8011/v1/health

# Check firewall
ufw status

# Allow Coordinator port
ufw allow 8011/tcp

# Check network
ping your-coordinator-url
```

### Registration Failed

**Problem**: Miner registration returns 404 or 401

**Solution**:
```bash
# Check API key
echo $MINER_API_KEY

# Verify API key is valid
curl -H "X-Api-Key: your-miner-api-key" \
  http://your-coordinator-url:8011/v1/miners/heartbeat

# Check Coordinator logs
journalctl -u coordinator-api -n 50
```

### Service Won't Start

**Problem**: Systemd service fails to start

**Solution**:
```bash
# Check service logs
journalctl -u aitbc-miner -n 50

# Check configuration
-u aitbc cat /opt/aitbc/miner/miner.env

# Test binary manually
-u aitbc /opt/aitbc/miner/aitbc-miner-debian
```

### Permission Denied

**Problem**: Permission errors accessing files

**Solution**:
```bash
# Fix permissions
chown -R aitbc:aitbc /opt/aitbc/miner
chown -R aitbc:aitbc /var/log/aitbc

# Fix binary permissions
chmod +x /opt/aitbc/miner/aitbc-miner-debian
```

## Upgrading

### Upgrade Binary

```bash
# Stop service
systemctl stop aitbc-miner

# Backup current binary
cp /opt/aitbc/miner/aitbc-miner-debian /opt/aitbc/miner/aitbc-miner-debian.backup

# Download new binary
cd /tmp
wget https://github.com/oib/AITBC/releases/download/v0.2.0/aitbc-miner-debian

# Verify checksum
sha256sum -c SHA256SUMS

# Replace binary
cp aitbc-miner-debian /opt/aitbc/miner/
chmod +x /opt/aitbc/miner/aitbc-miner-debian
chown aitbc:aitbc /opt/aitbc/miner/aitbc-miner-debian

# Start service
systemctl start aitbc-miner

# Verify
systemctl status aitbc-miner
```

## Uninstallation

### Remove Miner

```bash
# Stop service
systemctl stop aitbc-miner
systemctl disable aitbc-miner

# Remove files
rm -rf /opt/aitbc/miner
rm /etc/systemd/system/aitbc-miner.service

# Remove logs (optional)
rm -rf /var/log/aitbc

# Remove user (optional)
userdel aitbc

# Reload systemd
systemctl daemon-reload
```

## Advanced Configuration

### Multiple GPUs

If you have multiple GPUs, run multiple miner instances:

```bash
# Create additional configuration files
-u aitbc cp /opt/aitbc/miner/miner.env /opt/aitbc/miner/miner-gpu0.env
-u aitbc cp /opt/aitbc/miner/miner.env /opt/aitbc/miner/miner-gpu1.env

# Create additional services
cp /etc/systemd/system/aitbc-miner.service \
  /etc/systemd/system/aitbc-miner-gpu0.service

# Edit service to use different config and GPU
nano /etc/systemd/system/aitbc-miner-gpu0.service

# Add CUDA_VISIBLE_DEVICES to specify GPU
[Service]
Environment="CUDA_VISIBLE_DEVICES=0"
EnvironmentFile=/opt/aitbc/miner/miner-gpu0.env
```

### Custom Log Location

To use a custom log location:

```bash
# Edit miner.env
-u aitbc nano /opt/aitbc/miner/miner.env

# Add custom log path
LOG_PATH=/custom/path/miner.log

# Create directory
mkdir -p /custom/path
chown aitbc:aitbc /custom/path
```

### Performance Tuning

Adjust heartbeat interval and retry settings:

```bash
# Edit miner.env
-u aitbc nano /opt/aitbc/miner/miner.env

# Reduce heartbeat interval (more frequent updates)
HEARTBEAT_INTERVAL=10

# Increase retries (more resilient)
MAX_RETRIES=20
RETRY_DELAY=30
```

## Security

### Firewall Configuration

```bash
# Allow outgoing connections
ufw allow out 8011/tcp
ufw allow out 11434/tcp

# Allow incoming connections if needed
ufw allow in 8011/tcp
```

### API Key Security

- Never commit API keys to version control
- Use environment variables or secret management
- Rotate API keys regularly
- Use different keys for different environments

### System Hardening

```bash
# Install fail2ban
apt install -y fail2ban

# Configure fail2ban for AITBC
nano /etc/fail2ban/jail.local
```

## Monitoring

### GPU Monitoring

```bash
# Real-time GPU monitoring
watch -n 1 nvidia-smi
```

### Service Monitoring

```bash
# Check service status
systemctl status aitbc-miner

# Monitor logs
journalctl -u aitbc-miner -f
```

### Performance Monitoring

```bash
# Check CPU and memory
htop

# Check disk usage
df -h

# Check network
iftop
```

## Support

- **Documentation**: https://aitbc.bubuit.net/docs/
- **GitHub Issues**: https://github.com/oib/AITBC/issues
- **Community**: https://community.aitbc.dev/
- **Email**: support@aitbc.dev

## Appendix

### Systemd Service Template

```ini
[Unit]
Description=AITBC GPU Miner
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/miner
EnvironmentFile=/opt/aitbc/miner/miner.env
ExecStart=/opt/aitbc/miner/aitbc-miner-debian
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Configuration Template

```bash
# Required
MINER_API_KEY=your-miner-api-key
COORDINATOR_URL=http://your-coordinator-url:8011

# Optional
LOG_PATH=/var/log/aitbc/miner.log (symlink to /var/lib/aitbc/logs/)
HEARTBEAT_INTERVAL=15
MAX_RETRIES=10
RETRY_DELAY=30
```

### Quick Reference

```bash
# Start miner
systemctl start aitbc-miner

# Stop miner
systemctl stop aitbc-miner

# Restart miner
systemctl restart aitbc-miner

# View logs
journalctl -u aitbc-miner -f

# Check status
systemctl status aitbc-miner

# Enable auto-start
systemctl enable aitbc-miner

# Disable auto-start
systemctl disable aitbc-miner
```
