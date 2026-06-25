# GPU Setup & Configuration
Configure and optimize your GPU setup for mining.

## Prerequisites

### Driver Installation

```bash
# Ubuntu/Debian
apt install nvidia-driver-535

# Verify installation
nvidia-smi
```

### Incus/LXC Container GPU Passthrough

If the AITBC node runs inside an Incus/LXC container, the GPU and CUDA
UVM devices must be passed through from the host. Without this, `nvidia-smi`
works (it only needs NVML via `/dev/nvidia0`) but CUDA runtime fails with
`cuInit error 999` because `/dev/nvidia-uvm` is missing.

Run these commands **on the host** (not inside the container):

```bash
# 1. Pass through the GPU device (PCI passthrough)
incus config device add <container> gpu gpu

# 2. Pass through the NVIDIA UVM device (required by CUDA runtime)
#    Find the major number with: grep nvidia-uvm /proc/devices
incus config device add <container> nvidia-uvm unix-char \
    path=/dev/nvidia-uvm major=236 minor=0 mode=666

# 3. Pass through the NVIDIA UVM tools device
incus config device add <container> nvidia-uvm-tools unix-char \
    path=/dev/nvidia-uvm-tools major=236 minor=1 mode=666

# 4. Restart the container to apply
incus restart <container>
```

Verify inside the container after restart:

```bash
# Device nodes present
ls -la /dev/nvidia*

# CUDA runtime works
nvcc --version
nvidia-smi

# PyCUDA can access the GPU
/opt/aitbc/venv/bin/python -c "
import pycuda.driver as cuda; cuda.init(); import pycuda.autoinit
print(f'GPU: {cuda.Device(0).name()}')
"
```

See also: [GPU Issues](../troubleshooting/gpu-issues.md) for troubleshooting
`cuInit error 999` and other CUDA container problems.

### CUDA Installation

```bash
# Download CUDA from NVIDIA
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update
apt-get install cuda-toolkit-12-3
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
