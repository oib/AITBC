# Multi-GPU Support - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 adds multi-GPU server support, enabling precise hardware binding for software services by capturing GPU device ID and UUID from nvidia-smi.

## GPU Device Identification

The marketplace now supports multi-GPU servers by capturing GPU device ID and UUID from nvidia-smi.

### nvidia-smi Output Parsing
```
GPU 0: NVIDIA GeForce RTX 4060 Ti (UUID: GPU-ba5c6553-6396-ab66-5706-17e6de30a93a)
GPU 1: NVIDIA GeForce RTX 4090 (UUID: GPU-abc123...)
```

## New CLI Option

```bash
# Specify which GPU to use
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour --gpu-device 1

# Auto-detect (defaults to GPU 0)
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour
```

## Use Cases

- Run FFmpeg on GPU 3 (for video encoding)
- Run Ollama on GPU 1 (bigger GPU for LLM)
- Reserve GPU 0 for Hermes (no offers)
- Different pricing per GPU capability

## Blockchain Payload

```json
{
  "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
  "gpu_device": "0",
  "gpu_uuid": "GPU-ba5c6553-6396-ab66-5706-17e6de30a93a",
  ...
}
```

## Market List Display

```
GPU: NVIDIA GeForce RTX 4060 Ti [GPU 0]
GPU: NVIDIA GeForce RTX 4090 [GPU 1]
GPU: N/A (cloud)
```

## Deployment Type Inference

- Removed `--deployment-type` option
- Automatically inferred from model name suffix:
  - `model:cloud` → cloud deployment
  - Otherwise → local deployment

## SoftwareService Model Extension

- gpu_device field (VARCHAR)
- gpu_uuid field (VARCHAR)
- Blockchain payload includes GPU device and UUID

## Results

- ✅ GPU device ID and UUID captured from nvidia-smi
- ✅ `--gpu-device` option added to software_offer CLI
- ✅ SoftwareService model extended with `gpu_device` and `gpu_uuid` fields
- ✅ Blockchain payload includes GPU device and UUID
- ✅ Market list displays GPU device in format "GPU Name [GPU X]"
- ✅ Enables service placement on specific GPUs in multi-GPU servers
- ✅ Removed `--deployment-type` option (inferred from model name suffix)

---

*Last Updated: 2026-06-05*
