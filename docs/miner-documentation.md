# Miner Documentation - AITBC

Become a miner on the AITBC network: Stake tokens, provide GPU compute, and earn rewards.

## Overview

Miners are essential to the AITBC network, providing both security through staking and compute power for AI workloads. As a miner, you can:

- Stake AITBC tokens to secure the network
- Provide GPU compute for AI inference and training
- Earn rewards from both staking and compute services
- Participate in network governance

## Getting Started

### Prerequisites

- Minimum 10,000 AITBC tokens for staking
- Modern GPU with 8GB+ VRAM (for compute mining)
- Stable internet connection
- Linux or Windows OS

### Quick Setup

```bash
# Download miner binary
wget https://gitea.bubuit.net/oib/aitbc/releases/download/latest/aitbc-miner-linux-amd64.tar.gz
tar -xzf aitbc-miner-linux-amd64.tar.gz

# Initialize miner
./aitbc-miner init

# Start mining
./aitbc-miner start
```

## Mining Types

### 1. Staking Only

Secure the network by staking tokens without providing compute.

**Requirements:**
- Minimum 10,000 AITBC
- Always-online node

**Rewards:**
- 15-25% APY
- Based on stake amount
- Distributed daily

### 2. Compute Mining

Provide GPU compute for AI workloads in addition to staking.

**Requirements:**
- 10,000 AITBC stake
- GPU with 8GB+ VRAM
- 50GB+ storage

**Rewards:**
- Base staking rewards + compute fees
- $0.02 per GPU second
- Bonus for high-performance GPUs

### 3. Authority Node

Advanced mining with block production rights.

**Requirements:**
- 100,000 AITBC stake
- Invitation from core team
- Proven reliability

**Rewards:**
- Highest APY (30-40%)
- Transaction fees
- Governance rights

## Hardware Requirements

### Minimum Requirements

- **CPU**: 4 cores
- **RAM**: 8GB
- **Storage**: 100GB SSD
- **Network**: 10 Mbps upload
- **GPU**: GTX 1060 / RX 580 or better

### Recommended Setup

- **CPU**: 8+ cores
- **RAM**: 16GB+
- **Storage**: 500GB NVMe SSD
- **Network**: 100 Mbps+
- **GPU**: RTX 3080 / RTX 4080 or better

## Installation Guide

### Linux Installation

```bash
# Install dependencies
sudo apt update
sudo apt install -y curl wget gnupg2

# Download miner
wget https://gitea.bubuit.net/oib/aitbc/releases/download/latest/aitbc-miner-linux-amd64.tar.gz
tar -xzf aitbc-miner-linux-amd64.tar.gz
sudo mv aitbc-miner /usr/local/bin/

# Create systemd service
sudo tee /etc/systemd/system/aitbc-miner.service > /dev/null <<EOF
[Unit]
Description=AITBC Miner
After=network.target

[Service]
Type=simple
User=aitbc
ExecStart=/usr/local/bin/aitbc-miner start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable aitbc-miner
sudo systemctl start aitbc-miner
```

### Windows Installation

1. Download the Windows installer from releases
2. Run the installer as Administrator
3. Follow the setup wizard
4. Configure your wallet address
5. Start mining from the desktop shortcut

## Configuration

### Basic Configuration

Edit `~/.aitbc/miner/config.toml`:

```toml
# Network settings
[network]
rpc_url = "https://aitbc.bubuit.net"
ws_url = "wss://aitbc.bubuit.net/ws"

# Mining settings
[mining]
stake_amount = 10000
compute_enabled = true
gpu_devices = [0]  # GPU indices to use

# Wallet settings
[wallet]
address = "your-wallet-address"
private_key = "encrypted-private-key"

# Performance settings
[performance]
max_concurrent_jobs = 2
gpu_memory_fraction = 0.8
```

### GPU Optimization

```toml
# GPU-specific settings
[gpu]
nvidia_smi = true
cuda_version = "12.0"
memory_limit = "10GB"
power_limit = 250  # Watts

# Supported models
[supported_models]
llama3.2 = true
stable-diffusion = true
codellama = true
```

## Mining Operations

### Checking Status

```bash
# Overall status
./aitbc-miner status

# GPU status
./aitbc-miner gpu status

# Earnings
./aitbc-miner earnings

# Network stats
./aitbc-miner network
```

### Managing Stake

```bash
# Increase stake
./aitbc-miner stake increase 5000

# Decrease stake (7-day unlock)
./aitbc-miner stake decrease 2000

# Withdraw rewards
./aitbc-miner rewards withdraw

# Check pending rewards
./aitbc-miner rewards pending
```

### Troubleshooting

```bash
# Check logs
./aitbc-miner logs

# GPU diagnostics
./aitbc-miner gpu check

# Network connectivity
./aitbc-miner network test

# Restart miner
./aitbc-miner restart
```

## Earnings Calculator

Use this calculator to estimate your earnings:

```javascript
// Monthly earnings formula
monthlyEarnings = (stake * APY / 12) + (gpuHours * hourlyRate)

// Example: 10,000 AITBC stake, 20% APY, 100 GPU hours/month
// at $0.02/hour and $1/token price
monthlyEarnings = (10000 * 0.20 / 12) + (100 * 0.02)
                = 166.67 + 2.00
                = $168.67/month
```

## Best Practices

### Security

1. **Use a hardware wallet** for storing large stakes
2. **Enable 2FA** on all accounts
3. **Regular backups** of wallet data
4. **Keep software updated**
5. **Monitor for unusual activity**

### Performance

1. **Optimize GPU settings** for each model
2. **Monitor temperature** and power usage
3. **Use NVMe storage** for faster data access
4. **Configure appropriate job limits**
5. **Regular maintenance** of hardware

### Reliability

1. **Set up monitoring** alerts
2. **Have backup power** (UPS)
3. **Multiple internet connections**
4. **Automated restarts** on failures
5. **Regular log reviews**

## Frequently Asked Questions

### How much can I earn mining AITBC?

Earnings vary based on stake amount, network participation, and whether you provide GPU compute. Typical APY ranges from 15-25% for staking, with GPU mining adding additional rewards.

### When do I get paid?

Rewards are distributed daily and automatically credited to your wallet. You can withdraw anytime after the initial lock period.

### Can I run multiple nodes?

Yes, you can run multiple nodes but each requires separate stakes. This can provide redundancy and potentially higher rewards.

### What happens if my node goes offline?

You won't earn rewards while offline, but your stake remains safe. Extended downtime may affect your reputation score.

### How do I become an authority node?

Authority nodes require invitation based on community contribution, technical expertise, and stake amount. Apply through the community forum.

## Getting Help

- Check the logs: `./aitbc-miner logs`
- Visit our Discord community
- Search issues on Gitea
- Email support: aitbc@bubuit.net

## Additional Resources

- [Mining Hardware Guide](hardware-guide.md)
- [GPU Optimization](gpu-optimization.md)
- [Network Statistics](https://stats.aitbc.bubuit.net)
- [Mining Calculator](https://calculator.aitbc.bubuit.net)

---

Happy mining! 🚀
