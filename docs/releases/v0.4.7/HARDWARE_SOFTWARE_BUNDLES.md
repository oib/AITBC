# Hardware+Software Bundle Offers - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 introduces hardware+software bundle offers with GPU information, enabling shop owners to link software offers to specific GPU hardware.

## Features

### GPU Name Auto-Detection
GPU name is automatically detected from nvidia-smi for local deployments:
```bash
# Auto-detect GPU name
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour
# Output: Auto-detected GPU: NVIDIA GeForce RTX 4060 Ti

# Explicit GPU name
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour \
  --gpu-name "NVIDIA GeForce RTX 4060 Ti"

# Cloud deployment (no GPU)
aitbc market offer ollama nemotron-3-super:cloud 0.10 --unit per_hour
# Output: GPU name: N/A (cloud)
```

### GPU Offer Linking
Optional linking to GPU marketplace offer for cross-reference:
```bash
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour \
  --gpu-offer-id gpu_offer_20260605120000_abc12345
```

### Blockchain Payload
```json
{
  "action": "software_offer",
  "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
  "gpu_offer_id": "gpu_offer_...",
  ...
}
```

### Market List Output
```
Offer ID          | Type     | Service | Model          | Deploy  | GPU Name                     | Price
sw_offer_...      | SOFTWARE | ollama  | llama3.2:3b    | local   | NVIDIA GeForce RTX 4060 Ti  | 0.05 AIT/h
sw_offer_...      | SOFTWARE | ollama  | nemotron:cloud | cloud   | N/A (cloud)                  | 0.10 AIT/h
```

## CLI Options
- `--gpu-name` - GPU name (auto-detected from nvidia-smi)
- `--gpu-device` - GPU device ID (0, 1, 2, etc.) for multi-GPU servers
- `--gpu-offer-id` - GPU marketplace offer ID

## Results

- ✅ All software offers include GPU hardware information
- ✅ Auto-detection of GPU name from nvidia-smi
- ✅ Manual GPU name override via `--gpu-name` option
- ✅ Optional GPU offer ID linking via `--gpu-offer-id` option
- ✅ GPU name visible in offer listings
- ✅ Cloud deployment marked as "N/A (cloud)"

---

*Last Updated: 2026-06-05*
