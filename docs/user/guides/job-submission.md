# Job Submission Workflow

This guide explains how to submit AI compute jobs to the AITBC network and track their progress.

## Overview

The job submission workflow:

1. **Prepare** - Choose model and parameters
2. **Submit** - Send job to Coordinator API
3. **Queue** - Job enters the processing queue
4. **Execute** - Miner processes your job
5. **Complete** - Receive results and receipt

## Submission Methods

### Web Interface

1. Go to [Marketplace](https://aitbc.bubuit.net/marketplace/)
2. Select a service (e.g., "Text Generation", "Image Generation")
3. Enter your prompt and configure options
4. Click **Submit Job**
5. View job status in your dashboard

### CLI

```bash
# Basic submission
./aitbc-cli.sh submit "Explain machine learning in simple terms"

# With model selection
./aitbc-cli.sh submit "Generate a haiku about coding" --model llama3.2

# With parameters
./aitbc-cli.sh submit "Write a story" --model llama3.2 --max-tokens 500 --temperature 0.7

# Check job status
./aitbc-cli.sh status <job_id>

# List your jobs
./aitbc-cli.sh jobs
```

### Python SDK

```python
from aitbc_sdk import AITBCClient

client = AITBCClient(
    api_url="https://aitbc.bubuit.net/api",
    api_key="your-api-key"  # Optional for authenticated requests
)

# Submit a text generation job
job = client.submit_job(
    prompt="What is the capital of France?",
    model="llama3.2",
    params={
        "max_tokens": 100,
        "temperature": 0.5
    }
)

print(f"Job ID: {job.id}")
print(f"Status: {job.status}")

# Wait for completion
result = client.wait_for_job(job.id, timeout=60)
print(f"Output: {result.output}")
```

### Direct API

```bash
# Submit job
curl -X POST https://aitbc.bubuit.net/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello, world!",
    "model": "llama3.2",
    "params": {"max_tokens": 50}
  }'

# Check status
curl https://aitbc.bubuit.net/api/v1/jobs/<job_id>
```

## Job Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | required | Input text or instruction |
| `model` | string | `llama3.2` | AI model to use |
| `max_tokens` | int | 256 | Maximum output tokens |
| `temperature` | float | 0.7 | Creativity (0.0-1.0) |
| `top_p` | float | 0.9 | Nucleus sampling |
| `stream` | bool | false | Stream output chunks |

## Available Models

| Model | Type | Use Case |
|-------|------|----------|
| `llama3.2` | Text | General chat, Q&A, writing |
| `llama3.2:1b` | Text | Fast, lightweight tasks |
| `codellama` | Code | Code generation, debugging |
| `stable-diffusion` | Image | Image generation |

## Job States

| State | Description |
|-------|-------------|
| `pending` | Job submitted, waiting for miner |
| `running` | Miner is processing the job |
| `completed` | Job finished successfully |
| `failed` | Job failed (see error message) |
| `cancelled` | Job was cancelled by user |

## Tracking Your Jobs

### View in Explorer

Visit [Explorer](https://aitbc.bubuit.net/explorer/) to see:
- Recent jobs and their status
- Your job history (if authenticated)
- Receipt details and proofs

### Programmatic Tracking

```python
# Poll for status
import time

while True:
    job = client.get_job(job_id)
    print(f"Status: {job.status}")
    
    if job.status in ["completed", "failed", "cancelled"]:
        break
    
    time.sleep(2)
```

## Cancelling Jobs

```bash
# CLI
./aitbc-cli.sh cancel <job_id>

# API
curl -X POST https://aitbc.bubuit.net/api/v1/jobs/<job_id>/cancel
```

## Best Practices

1. **Be specific** - Clear prompts get better results
2. **Set appropriate limits** - Use `max_tokens` to control costs
3. **Handle errors** - Always check job status before using output
4. **Use streaming** - For long outputs, enable streaming for faster feedback

## Next Steps

- [Payments and Receipts](payments-receipts.md) - Understanding costs and proofs
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
