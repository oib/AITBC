# Deployment Prerequisites

This guide covers software and hardware requirements for deploying the AITBC platform.

> **Note:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Software Requirements

- **Operating System**: Debian 12 (bookworm) or Ubuntu 22.04 LTS
- **Python**: 3.13 or higher
- **Node.js**: 24.14.0 or higher (for JavaScript SDK)
- **CUDA Toolkit**: 12.4 (for GPU support)
- **Docker**: 24.0 or higher (for containerized deployment)
- **Docker Compose**: 2.20 or higher

## Hardware Requirements

### Minimum (Development)
- CPU: 4 cores
- RAM: 8 GB
- Storage: 100 GB SSD
- GPU: Not required for development

### Recommended (Production)
- CPU: 8+ cores
- RAM: 16+ GB
- Storage: 500 GB NVMe SSD
- GPU: NVIDIA RTX 3090 or better (for mining)

### Multi-Node
- Each node: 8+ cores, 16+ GB RAM, 100+ GB SSD
- GPU nodes: NVIDIA RTX 3090 or better
- Network: 10 Gbps interconnect

## Network Requirements

- Public IP address (for blockchain node)
- Open ports: 8006 (blockchain RPC), 7070 (P2P), 8011 (coordinator), 8015 (wallet), 8102 (marketplace)
- DNS configuration (optional but recommended)
- Firewall rules configured

> **Port Reference:** For complete port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## System Dependencies

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

## Python Environment

```bash
# Create virtual environment
python3 -m venv /opt/aitbc/venv
source /opt/aitbc/venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

## See Also

- [Local Setup](local-setup.md) - Local development deployment
- [Single Server](single-server.md) - Single server production deployment
- [Multi Server](multi-server.md) - Multi-server deployment
