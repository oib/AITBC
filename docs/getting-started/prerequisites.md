# Prerequisites

This guide covers the system and software requirements for installing AITBC.

## System Requirements

- **Operating System**: Ubuntu Linux (20.04 LTS or later recommended)
- **Python**: 3.13.5 or higher
- **pip3**: Latest version
- **git**: Latest version
- **systemd**: For service management
- **Root privileges**: Required for installation

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

## Software Dependencies

### Core Requirements
- Python 3.13.5+
- pip3
- git
- systemd

### Optional Requirements
- PostgreSQL (for production databases)
- Redis (for caching and pub/sub)
- nginx (for reverse proxy)
- CUDA Toolkit 12.4 (for GPU support)
- Docker 24.0+ (for containerized deployment)

## System Dependencies

```bash
# System dependencies
apt update
apt install -y \
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
    ca-certificates

# CUDA dependencies (for GPU support)
apt install -y \
    nvidia-cuda-toolkit \
    nvidia-cudnn \
    libnvidia-common
```

## Verification

Check your system meets the prerequisites:

```bash
# Check Python version
python3 --version

# Check pip3
pip3 --version

# Check git
git --version

# Check systemd
systemctl --version

# Check root privileges
whoami
```

## See Also

- [Quick Start](quick-start.md)
- [Requirements Management](requirements-management.md)
- [Installation](installation.md)
