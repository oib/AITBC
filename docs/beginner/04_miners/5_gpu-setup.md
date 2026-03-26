# GPU Setup & Configuration
Configure and optimize your GPU setup for mining.

## Prerequisites

### Driver Installation

```bash
# Ubuntu/Debian
sudo apt install nvidia-driver-535

# Verify installation
nvidia-smi
```

### CUDA Installation

```bash
# Download CUDA from NVIDIA
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get install cuda-toolkit-12-3
```

## Configuration

### Miner Config

Create `~/.aitbc/miner.yaml`:

```yaml
gpu:
  type: v100
  count: 1
  cuda_devices: 0
  
performance:
  max_memory_percent: 90
  max_gpu_temp: 80
  power_limit: 250
  
jobs:
  max_concurrent: 4
  timeout_grace: 300
```

### Environment Variables

```bash
export CUDA_VISIBLE_DEVICES=0
export NVIDIA_VISIBLE_DEVICES=all
export AITBC_GPU_MEMORY_LIMIT=0.9
```

## Optimization

### Memory Settings

```yaml
performance:
  tensor_cores: true
  fp16: true  # Use half precision
  max_memory_percent: 90
```

### Thermal Management

```yaml
thermal:
  target_temp: 70
  max_temp: 85
  fan_curve:
    - temp: 50
      fan: 30
    - temp: 70
      fan: 60
    - temp: 85
      fan: 100
```

## Troubleshooting

### GPU Not Detected

```bash
# Check driver
nvidia-smi

# Check CUDA
nvcc --version

# Restart miner
aitbc miner restart
```

### Temperature Issues

```bash
# Monitor temperature
nvidia-smi -l 1

# Check cooling
ipmitool sdr list | grep Temp
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Monitoring](./6_monitoring.md) - Monitor your miner
- [Job Management](./3_job-management.md) — Job management
