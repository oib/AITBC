# AITBC Miner for Debian Stable

## Overview

The AITBC Miner is a standalone binary for Debian stable (trixie) that allows GPU owners to participate in the AITBC decentralized compute marketplace.

**Inference Backends:**
- **vLLM** (recommended): Optimized LLM inference engine with better performance
- **Ollama**: Alternative inference backend for compatibility

## System Requirements

- **Operating System**: Debian 13 (trixie) or Ubuntu 24.04 LTS
- **GPU**: NVIDIA GPU with CUDA 12.4+ support
- **Memory**: 16GB+ RAM recommended
- **Storage**: 100GB+ SSD
- **Python**: Not required (binary is self-contained)

## Prerequisites

### GPU Drivers

```bash
# Install NVIDIA drivers
sudo apt install -y nvidia-driver-full

# Verify installation
nvidia-smi
```

### CUDA Toolkit

```bash
# Install CUDA Toolkit
sudo apt install -y nvidia-cuda-toolkit

# Verify installation
nvcc --version
```

### Ollama (Required if using Ollama backend)

Ollama is required for AI inference if using the Ollama backend:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull a model
ollama pull llama2
```

**Note:** vLLM is included in the binary and is recommended for better performance. To use vLLM, set `INFERENCE_BACKEND=vllm` in your configuration.

## Installation

### Download Binary

```bash
# Download the latest binary from GitHub releases
wget https://github.com/oib/aitbc/releases/download/v0.1.0/aitbc-miner-debian

# Make executable
chmod +x aitbc-miner-debian
```

### Verify Checksum

```bash
# Download checksums from GitHub releases
wget https://github.com/oib/aitbc/releases/download/v0.1.0/SHA256SUMS

# Verify
sha256sum -c SHA256SUMS
```

## Configuration

### Environment Variables

Create a configuration file or set environment variables:

```bash
# Required
export MINER_API_KEY="your-miner-api-key"
export COORDINATOR_URL="http://your-coordinator-url:8203"

# Optional
export LOG_PATH="/var/log/aitbc/miner.log"
export HEARTBEAT_INTERVAL=15
```

### Configuration File

Alternatively, create a `.env` file:

```bash
# /etc/aitbc/miner.env
MINER_API_KEY=your-miner-api-key
COORDINATOR_URL=http://your-coordinator-url:8203
LOG_PATH=/var/log/aitbc/miner.log
HEARTBEAT_INTERVAL=15
```

## Running the Miner

### Start Miner

```bash
# Using environment variables
./aitbc-miner-debian

# Using .env file
./aitbc-miner-debian
```

### Systemd Service

Create a systemd service for automatic startup:

```ini
# /etc/systemd/system/aitbc-miner.service
[Unit]
Description=AITBC GPU Miner
After=network.target ollama.service

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/miner
Environment="MINER_API_KEY=your-miner-api-key"
Environment="COORDINATOR_URL=http://coordinator:8203"
ExecStart=/opt/aitbc/miner/aitbc-miner-debian
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable aitbc-miner
sudo systemctl start aitbc-miner
sudo systemctl status aitbc-miner
```

## Verification

### Check GPU Detection

The miner will automatically detect and report GPU information on startup:

```
2026-05-11 12:15:53 - INFO - GPU detected: NVIDIA GeForce RTX 4060 Ti (16380MB)
```

### Check Ollama Connection

The miner will verify Ollama is running and list available models:

```
2026-05-11 12:15:53 - INFO - Ollama models available: llama2:7b, gemma4:31b-cloud
```

### Check Coordinator Connection

The miner will attempt to connect to the coordinator:

```
2026-05-11 12:15:53 - INFO - Coordinator is available!
```

### Check Registration

The miner will register with the coordinator:

```
2026-05-11 12:15:53 - INFO - Successfully registered miner
```

## Troubleshooting

### GPU Not Detected

```bash
# Check GPU
nvidia-smi

# Check driver
dmesg | grep -i nvidia

# Reinstall drivers if needed
sudo apt install --reinstall nvidia-driver-535
```

### Ollama Not Available

```bash
# Check Ollama status
systemctl status ollama

# Start Ollama
ollama serve

# Check models
ollama list
```

### Coordinator Connection Failed

```bash
# Check coordinator URL
curl http://your-coordinator-url:8203/v1/health

# Check firewall
sudo ufw status

# Check network
ping your-coordinator-url
```

### Registration Failed

```bash
# Check API key
echo $MINER_API_KEY

# Verify API key is valid
curl -H "X-Api-Key: $MINER_API_KEY" \
  http://your-coordinator-url:8203/v1/miners/heartbeat
```

## Logging

Logs are written to the configured log path (default: `/var/log/aitbc/miner.log`).

View logs:

```bash
# Real-time logs
tail -f /var/log/aitbc/miner.log

# Systemd logs
sudo journalctl -u aitbc-miner -f
```

## Uninstallation

```bash
# Stop service
sudo systemctl stop aitbc-miner
sudo systemctl disable aitbc-miner

# Remove files
sudo rm /opt/aitbc/miner/aitbc-miner-debian
sudo rm /etc/systemd/system/aitbc-miner.service

# Remove logs (optional)
sudo rm -rf /var/log/aitbc
```

## Support

- **Documentation**: https://aitbc.bubuit.net/docs/
- **GitHub Issues**: https://github.com/oib/AITBC/issues
- **Community**: https://community.aitbc.dev/

## License

MIT License - see LICENSE file for details.
