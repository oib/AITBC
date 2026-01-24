---
name: ollama-gpu-provider
description: End-to-end Ollama prompt payment test against the GPU miner provider
version: 1.0.0
author: Cascade
tags: [gpu, miner, ollama, payments, receipts, test]
---

# Ollama GPU Provider Test Skill

This skill runs an end-to-end client → coordinator → GPU miner → receipt flow using an Ollama prompt.

## Overview

The test submits a prompt (default: "hello") to the coordinator via the host proxy, waits for completion, and verifies that the job result and signed receipt are returned.

## Prerequisites

- Host GPU miner running and registered (RTX 4060 Ti + Ollama)
- Incus proxy forwarding `127.0.0.1:18000` → container `127.0.0.1:8000`
- Coordinator running in container (`coordinator-api.service`)
- Receipt signing key configured in `/opt/coordinator-api/src/.env`

## Test Command

```bash
python3 cli/test_ollama_gpu_provider.py --url http://127.0.0.1:18000 --prompt "hello"
```

## Expected Outcome

- Job reaches `COMPLETED`
- Output returned from Ollama
- Receipt present with a `receipt_id`

## Notes

- Use `--timeout` to allow longer runs for large models.
- If the receipt is missing, verify `receipt_signing_key_hex` is set and restart the coordinator.
