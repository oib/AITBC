# Miner Quick Start

**5 minutes** — Register your GPU and start earning AITBC tokens.

## Prerequisites

- NVIDIA GPU with 16GB+ VRAM (V100, A100, RTX 3090+)
- Python 3.10+, CUDA drivers installed
- 50GB+ storage, stable internet

## 1. Install & Configure

```bash
pip install -e .                                        # from monorepo root
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key
```

## 2. Register & Start

```bash
aitbc miner register --name my-gpu --gpu v100 --count 1
aitbc miner poll                                         # start accepting jobs
```

## 3. Verify

```bash
aitbc miner status                                       # GPU status + earnings
aitbc wallet balance                                     # check token balance
```

## Next

- [2_registration.md](./2_registration.md) — Advanced registration options
- [3_job-management.md](./3_job-management.md) — Job acceptance and completion
- [5_gpu-setup.md](./5_gpu-setup.md) — GPU driver and CUDA setup
