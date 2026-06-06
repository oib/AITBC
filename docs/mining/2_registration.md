# Miner Registration
Register your miner with the AITBC network.

## Requirements

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU VRAM | 8GB | 16GB+ |
| RAM | 16GB | 32GB+ |
| Storage | 50GB | 100GB+ |
| Bandwidth | 10 Mbps | 100 Mbps |

### Supported GPUs

- NVIDIA V100 (16GB/32GB)
- NVIDIA A100 (40GB/80GB)
- NVIDIA RTX 3090 (24GB)
- NVIDIA RTX 4090 (24GB)

## Registration

### Basic Registration

```bash
aitbc miner register --name my-miner --gpu v100 --count 1
```

### Advanced Registration

```bash
aitbc miner register \
  --name my-miner \
  --gpu a100 \
  --count 4 \
  --location us-east \
  --price 0.10 \
  --max-concurrent 4
```

### Flags Reference

| Flag | Description |
|------|-------------|
| `--name` | Miner name |
| `--gpu` | GPU type (v100, a100, rtx3090, rtx4090) |
| `--count` | Number of GPUs |
| `--location` | Geographic location |
| `--price` | Price per GPU/hour in AITBC |
| `--max-concurrent` | Maximum concurrent jobs |

## Verification

```bash
aitbc miner status
```

Shows:
- Registration status
- GPU availability
- Current jobs

## Update Registration

```bash
aitbc miner update --price 0.12 --max-concurrent 8
```

## De-register

```bash
aitbc miner deregister --confirm
```

## Next

- [Job Management](./3_job-management.md) — Job management
- [Earnings](./4_earnings.md) — Earnings tracking
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
