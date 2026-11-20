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

~~Create `~/.aitbc/miner.yaml`~~ — **nothing reads this file**; the miner is env-var configured (`apps/miner/production_miner.py`):

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

The miner is configured entirely through its systemd environment file
(`/etc/aitbc/aitbc-miner.env` on deployed nodes) — there is no config file.
The keys `apps/miner/production_miner.py` actually reads:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINER_ID` | — (required) | Public miner identifier |
| `MINER_AUTH_TOKEN` / `MINER_API_KEY` | — (required) | Coordinator credential |
| `MINER_WALLET_ADDRESS` | — | Payout address; without it the coordinator will not assign escrowed (paid) jobs |
| `COORDINATOR_URL` | `http://127.0.0.1:8107` | Coordinator API base URL |
| `MINER_REGION` | `localhost` | Region the miner registers under (coordinator registration, capabilities, pool hub) |
| `MINER_REGISTER_GPU` | off | Set to `1` to self-register this miner's GPU in the coordinator market registry |
| `MINER_GPU_RESOURCE_ID` | — | Stable resource id for the market GPU row (keeps re-registers idempotent) |
| `MINER_GPU_REGION` | `MINER_REGION` | Region written to the market GPU row |
| `MINER_GPU_PRICE_PER_HOUR` | `0.05` | Price advertised on the market GPU row |
| `MINER_GPU_REREGISTER_SECONDS` | `300` | Interval between market GPU re-registers |
| `MINER_MAX_CONCURRENT_JOBS` | `1` | Concurrent-job ceiling advertised to the coordinator |
| `MINER_ENDPOINT` | `http://localhost:8101` | Public miner endpoint reported to the pool hub |
| `POOL_HUB_URL` | `http://127.0.0.1:8210` | Pool hub base URL (`HUB_POOL_HUB_URL` also accepted) <!-- check-ports: ignore --> |

Protected `gpu_compute` dispatch note (#2305): job payloads carry
`constraints.region` copied from the market GPU row, and dispatch silently
skips a miner whose registered region differs — a miner left at the
`localhost` default never receives protected-resource jobs. Set
`MINER_REGION` to the same region as the GPU row, and for self-registration
set `MINER_REGISTER_GPU=1` (plus `MINER_GPU_RESOURCE_ID` for a stable row).

```bash
export CUDA_VISIBLE_DEVICES=0
export NVIDIA_VISIBLE_DEVICES=all
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
sudo systemctl restart aitbc-miner
```

### Temperature Issues

```bash
# Monitor temperature
nvidia-smi -l 1

# Check cooling
ipmitool sdr list | grep Temp
```

## Next

- [Miner Quick Start](../getting-started/mining/miner-quick-start.md) — Get started
- [Monitoring](./6_monitoring.md) - Monitor your miner
- [Job Management](./3_job-management.md) — Job management
