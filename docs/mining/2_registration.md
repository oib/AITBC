# Miner Registration

Register your miner with the the network.

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

GPU provider registration uses the `aitbc gpu` group (GPU market /
coordinator registration). The `aitbc-miner` systemd service then polls the
coordinator for inference jobs automatically.

### Discover Local GPUs

```bash
# Inventory the GPUs visible on this host
aitbc gpu discover
aitbc gpu list-gpus
```

### Basic Registration

```bash
aitbc gpu register --gpu-id my-miner-gpu-0
```

### Advanced Registration

```bash
aitbc gpu register \
  --gpu-id my-miner-gpu-0 \
  --specs '{"model": "A100", "memory_gb": 80, "region": "us-east", "price_per_hour": "0.10", "max_concurrent": 4}'
```

### Flags Reference

| Flag | Description |
|------|-------------|
| `--gpu-id` | GPU unique identifier (required) |
| `--specs` | GPU specifications as a JSON string (auto-discovered if omitted) |

For an on-chain resource record with full pricing metadata, use
`aitbc gpu-onchain register`:

```bash
aitbc gpu-onchain register \
  --gpu-id my-miner-gpu-0 \
  --miner-id my-miner \
  --model "A100" \
  --memory-gb 80 \
  --region us-east \
  --capabilities inference \
  --price-per-hour 0.10 \
  --wallet my-miner-wallet
```

## Verification

```bash
aitbc gpu-onchain query --gpu-id my-miner-gpu-0
aitbc mining status
```

Shows:

- On-chain GPU registration record
- Mining loop status and current work

## Update Registration

```bash
aitbc gpu update --gpu-id my-miner-gpu-0 \
  --pricing '{"price_per_hour": "0.12", "max_concurrent": 8}'
```

## De-register

```bash
aitbc gpu unregister --gpu-id my-miner-gpu-0
```

## Next

- [Job Management](./3_job-management.md) — Job management
- [Earnings](./4_earnings.md) — Earnings tracking
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
