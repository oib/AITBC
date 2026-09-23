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

## Network Requirements

Ensure your firewall allows the following ports:

### Required Ports

- **Outbound**: Port 443 to hub.example.net (all hub APIs are proxied
  through nginx — `/rpc/*` for the blockchain RPC, `/agent/*` for the agent
  coordinator; the raw service ports 8202/8107 are loopback/LAN-only on the
  hub)
- **Inbound**: none strictly required on a follower/customer node — it dials
  out to the hub. (If you run the chain node's P2P listener it binds on
  8200 by default, not 7070 — 7070 is the hub-only gossip relay.)

### UFW Configuration Example

```bash
# Allow outbound to the hub (nginx proxies all APIs on 443)
ufw allow out to hub.example.net port 443

# Followers need no inbound rules; if you do run a P2P listener it
# defaults to 8200, not 7070:
# ufw allow 8200/tcp

ufw enable
```

### DNS Resolution

Ensure your system can resolve hub.example.net:

```bash
# Test DNS resolution
nslookup hub.example.net
ping hub.example.net
```

## See Also

- [Quick Start](quick-start.md)
- [Requirements Management](requirements-management.md)
- [Installation](installation.md)
