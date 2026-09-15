# Miner Quick Start

**5 minutes** — Register your GPU and start earning the network tokens with the CLI and the `aitbc-miner` service.

## Prerequisites

- NVIDIA GPU with 16GB+ VRAM (V100, A100, RTX 3090+)
- Python 3.10+, CUDA drivers installed
- 50GB+ storage, stable internet

## 1. Install & Configure

```bash
pip install -e .                                        # from monorepo root
aitbc config set --key coordinator_url --value http://localhost:8203
export AITBC_API_KEY=your-key

# Verify installation
aitbc --version
aitbc --debug
```

## 2. Register & Start

```bash
# Register your GPU on-chain (creates a provider resource record)
aitbc gpu-onchain register \
  --gpu-id my-gpu-0 \
  --miner-id my-miner \
  --model "RTX 4090" \
  --memory-gb 24 \
  --region us-west \
  --price-per-hour 0.05 \
  --wallet my-miner-wallet

# Start the PoA mining loop against the blockchain RPC
aitbc mining start --wallet-name my-miner-wallet --threads 4

# The GPU inference miner (Ollama job polling) runs as a service
sudo systemctl start aitbc-miner
```

## 3. Verify & Monitor

```bash
# Mining / GPU status
aitbc mining status
aitbc gpu list-gpus                                      # local GPU inventory
aitbc gpu-onchain query --gpu-id my-gpu-0                # on-chain record
aitbc wallet balance                                     # check token balance
aitbc monitor dashboard                                  # real-time monitoring
```

## 4. Advanced Features

```bash
# Track earnings through your wallet transaction history
aitbc wallet transactions --limit 50

# Marketplace integration — publish a GPU-backed inference offer
# (verifies the model exists on the local Ollama at :11434 first)
aitbc market offer \
  --service-type ollama \
  --model-or-variant llama3.2:3b \
  --price 0.001 \
  --unit per_1k_tokens \
  --gpu-name "RTX-4090" \
  --gpu-device 0 \
  --description "RTX-4090 Ollama inference"
```

## 5. Configuration Management

```bash
# Configuration profiles (save the current config under a name, reload later)
aitbc config profiles save --name mining
aitbc config profiles load --name mining

# Performance monitoring
aitbc monitor metrics --period 1h
aitbc monitor alerts add --name gpu-miner-offline --type miner_offline --threshold 90
```

## Next

- [2_registration.md](../../mining/2_registration.md) — Advanced registration options
- [3_job-management.md](../../mining/3_job-management.md) — Job acceptance and completion
- [5_gpu-setup.md](../../mining/5_gpu-setup.md) — GPU driver and CUDA setup
