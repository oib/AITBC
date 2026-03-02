# Miner Quick Start

**5 minutes** — Register your GPU and start earning AITBC tokens with the enhanced CLI.

## Prerequisites

- NVIDIA GPU with 16GB+ VRAM (V100, A100, RTX 3090+)
- Python 3.10+, CUDA drivers installed
- 50GB+ storage, stable internet

## 1. Install & Configure

```bash
pip install -e .                                        # from monorepo root
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key

# Verify installation
aitbc --version
aitbc --debug
```

## 2. Register & Start

```bash
# Enhanced miner registration
aitbc miner register \
  --name my-gpu \
  --gpu v100 \
  --count 1 \
  --region us-west \
  --price-per-hour 0.05

# Start accepting jobs
aitbc miner poll
```

## 3. Verify & Monitor

```bash
# Enhanced monitoring
aitbc miner status                                       # GPU status + earnings
aitbc wallet balance                                     # check token balance
aitbc monitor dashboard                                 # real-time monitoring
```

## 4. Advanced Features

```bash
# GPU optimization
aitbc optimize enable --agent-id my-gpu-agent \
  --mode performance \
  --auto-tune

# Earnings tracking
aitbc miner earnings --period daily
aitbc miner earnings --period weekly

# Marketplace integration
aitbc marketplace offer create \
  --miner-id my-gpu \
  --gpu-model "RTX-4090" \
  --gpu-memory "24GB" \
  --price-per-hour "0.05" \
  --models "gpt2,llama" \
  --endpoint "http://localhost:11434"
```

## 5. Configuration Management

```bash
# Configuration profiles
aitbc config profiles create mining
aitbc config profiles set mining gpu_count 4
aitbc config profiles use mining

# Performance monitoring
aitbc monitor metrics --component gpu
aitbc monitor alerts --type gpu_temperature
```

## Next

- [2_registration.md](./2_registration.md) — Advanced registration options
- [3_job-management.md](./3_job-management.md) — Job acceptance and completion
- [5_gpu-setup.md](./5_gpu-setup.md) — GPU driver and CUDA setup
