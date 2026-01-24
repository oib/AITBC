# Building a Custom Miner

This tutorial walks you through creating a custom GPU miner for the AITBC network.

## Prerequisites

- Linux system with NVIDIA GPU
- Python 3.10+
- CUDA toolkit installed
- Ollama or other inference backend

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Coordinator    │────▶│   Your Miner     │────▶│  GPU Backend    │
│  API            │◀────│   (Python)       │◀────│  (Ollama)       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

Your miner:
1. Polls the Coordinator for available jobs
2. Claims and processes jobs using your GPU
3. Returns results and receives payment

## Step 1: Basic Miner Structure

Create `my_miner.py`:

```python
#!/usr/bin/env python3
"""Custom AITBC GPU Miner"""

import asyncio
import httpx
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustomMiner:
    def __init__(self, coordinator_url: str, miner_id: str):
        self.coordinator_url = coordinator_url
        self.miner_id = miner_id
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def register(self):
        """Register miner with coordinator."""
        response = await self.client.post(
            f"{self.coordinator_url}/v1/miners/register",
            json={
                "miner_id": self.miner_id,
                "capabilities": ["llama3.2", "codellama"],
                "gpu_info": self.get_gpu_info()
            }
        )
        response.raise_for_status()
        logger.info(f"Registered as {self.miner_id}")
        
    def get_gpu_info(self) -> dict:
        """Collect GPU information."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True
            )
            name, memory = result.stdout.strip().split(", ")
            return {"name": name, "memory": memory}
        except Exception:
            return {"name": "Unknown", "memory": "Unknown"}
    
    async def poll_jobs(self):
        """Poll for available jobs."""
        response = await self.client.get(
            f"{self.coordinator_url}/v1/jobs/available",
            params={"miner_id": self.miner_id}
        )
        if response.status_code == 200:
            return response.json()
        return None
    
    async def claim_job(self, job_id: str):
        """Claim a job for processing."""
        response = await self.client.post(
            f"{self.coordinator_url}/v1/jobs/{job_id}/claim",
            json={"miner_id": self.miner_id}
        )
        return response.status_code == 200
    
    async def process_job(self, job: dict) -> str:
        """Process job using GPU backend."""
        # Override this method with your inference logic
        raise NotImplementedError("Implement process_job()")
    
    async def submit_result(self, job_id: str, result: str):
        """Submit job result to coordinator."""
        response = await self.client.post(
            f"{self.coordinator_url}/v1/jobs/{job_id}/complete",
            json={
                "miner_id": self.miner_id,
                "result": result,
                "completed_at": datetime.utcnow().isoformat()
            }
        )
        response.raise_for_status()
        logger.info(f"Completed job {job_id}")
    
    async def run(self):
        """Main mining loop."""
        await self.register()
        
        while True:
            try:
                job = await self.poll_jobs()
                if job:
                    job_id = job["job_id"]
                    if await self.claim_job(job_id):
                        logger.info(f"Processing job {job_id}")
                        result = await self.process_job(job)
                        await self.submit_result(job_id, result)
                else:
                    await asyncio.sleep(2)  # No jobs, wait
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(5)
```

## Step 2: Add Ollama Backend

Extend the miner with Ollama inference:

```python
class OllamaMiner(CustomMiner):
    def __init__(self, coordinator_url: str, miner_id: str, ollama_url: str = "http://localhost:11434"):
        super().__init__(coordinator_url, miner_id)
        self.ollama_url = ollama_url
    
    async def process_job(self, job: dict) -> str:
        """Process job using Ollama."""
        prompt = job.get("prompt", "")
        model = job.get("model", "llama3.2")
        
        response = await self.client.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            },
            timeout=120.0
        )
        response.raise_for_status()
        return response.json()["response"]

# Run the miner
if __name__ == "__main__":
    miner = OllamaMiner(
        coordinator_url="https://aitbc.bubuit.net/api",
        miner_id="my-custom-miner-001"
    )
    asyncio.run(miner.run())
```

## Step 3: Add Receipt Signing

Sign receipts for payment verification:

```python
from aitbc_crypto import sign_receipt, generate_keypair

class SigningMiner(OllamaMiner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.private_key, self.public_key = generate_keypair()
    
    async def submit_result(self, job_id: str, result: str):
        """Submit signed result."""
        receipt = {
            "job_id": job_id,
            "miner_id": self.miner_id,
            "result_hash": hashlib.sha256(result.encode()).hexdigest(),
            "completed_at": datetime.utcnow().isoformat()
        }
        
        signature = sign_receipt(receipt, self.private_key)
        receipt["signature"] = signature
        
        response = await self.client.post(
            f"{self.coordinator_url}/v1/jobs/{job_id}/complete",
            json={"result": result, "receipt": receipt}
        )
        response.raise_for_status()
```

## Step 4: Run as Systemd Service

Create `/etc/systemd/system/my-miner.service`:

```ini
[Unit]
Description=Custom AITBC Miner
After=network.target ollama.service

[Service]
Type=simple
User=miner
WorkingDirectory=/home/miner
ExecStart=/usr/bin/python3 /home/miner/my_miner.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable my-miner
sudo systemctl start my-miner
sudo journalctl -u my-miner -f
```

## Step 5: Monitor Performance

Add metrics collection:

```python
import time

class MetricsMiner(SigningMiner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jobs_completed = 0
        self.total_time = 0
    
    async def process_job(self, job: dict) -> str:
        start = time.time()
        result = await super().process_job(job)
        elapsed = time.time() - start
        
        self.jobs_completed += 1
        self.total_time += elapsed
        
        logger.info(f"Job completed in {elapsed:.2f}s (avg: {self.total_time/self.jobs_completed:.2f}s)")
        return result
```

## Best Practices

1. **Error Handling**: Always catch and log exceptions
2. **Graceful Shutdown**: Handle SIGTERM for clean exits
3. **Rate Limiting**: Don't poll too aggressively
4. **GPU Memory**: Monitor and clear GPU memory between jobs
5. **Logging**: Use structured logging for debugging

## Next Steps

- [Coordinator API Integration](coordinator-api-integration.md)
- [SDK Examples](sdk-examples.md)
- [Reference: Miner Node](../../reference/components/miner_node.md)
