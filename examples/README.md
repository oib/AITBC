# AITBC Examples

This directory contains runnable examples that demonstrate how to use the AITBC platform end-to-end.

## Available examples

| Example | What it shows | Run |
|---|---|---|
| [`gpu_inference_miner.py`](gpu_inference_miner.py) | Register a GPU-capable miner, poll for inference jobs, optionally run them through Ollama, and submit results. | `python examples/gpu_inference_miner.py --api-key $MINER_API_KEY` |
| [`gpu_inference_client.py`](gpu_inference_client.py) | Submit an inference job to the coordinator, poll for completion, and print the result. | `python examples/gpu_inference_client.py --prompt "..."` |

## End-to-end GPU inference demo

1. Start the coordinator API:
   ```bash
   cd apps/coordinator-api
   PYTHONPATH=src poetry run uvicorn coordinator_api.main:app --reload
   ```

2. Set the shared secret:
   ```bash
   export JWT_SECRET="test-secret-32-characters-for-tests"
   export MINER_API_KEY="test-miner-key-32-characters-long-xxx"
   ```

3. In one terminal, start the miner:
   ```bash
   python examples/gpu_inference_miner.py --api-key "$MINER_API_KEY" --miner-id demo-miner
   ```

4. In another terminal, submit a job:
   ```bash
   python examples/gpu_inference_client.py \
     --jwt-secret "$JWT_SECRET" \
     --prompt "Explain the Byzantine generals problem in one paragraph." \
     --model llama2
   ```

If [Ollama](https://ollama.com/) is running on `localhost:11434` with `llama2` pulled, the miner will execute real inference. Otherwise it returns a deterministic mock result so the demo still works.

## Legacy stubs

Older stub/example packages that are not yet runnable are kept in `apps/<service>/examples/` while they are being migrated or replaced.
