---
title: Quickstart Guide
description: Get up and running with AITBC in minutes
---

# Quickstart Guide

This guide will help you get started with AITBC quickly. You'll learn how to set up a development environment, create your first AI job, and interact with the marketplace.

## Prerequisites

Before you begin, ensure you have:

- Python 3.8 or higher
- Docker and Docker Compose
- Git
- A terminal or command line interface
- Basic knowledge of AI/ML concepts (optional but helpful)

## 1. Installation

### Option A: Using Docker (Recommended)

The fastest way to get started is with Docker:

```bash
# Clone the AITBC repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc

# Start all services with Docker Compose
docker-compose up -d

# Wait for services to be ready (takes 2-3 minutes)
docker-compose logs -f
```

### Option B: Local Development

For local development, install components individually:

```bash
# Install the AITBC CLI
pip install aitbc-cli

# Initialize a new project
aitbc init my-ai-project
cd my-ai-project

# Start local services
aitbc dev start
```

## 2. Verify Installation

Check that everything is working:

```bash
# Check coordinator API health
curl http://localhost:8011/v1/health

# Expected response:
# {"status":"ok","env":"dev"}
```

## 3. Create Your First AI Job

### Step 1: Prepare Your AI Model

Create a simple Python script for your AI model:

```python
# model.py
import numpy as np
from typing import Dict, Any

def process_image(image_data: bytes) -> Dict[str, Any]:
    """Process an image and return results"""
    # Your AI processing logic here
    # This is a simple example
    result = {
        "prediction": "cat",
        "confidence": 0.95,
        "processing_time": 0.123
    }
    return result

if __name__ == "__main__":
    import sys
    with open(sys.argv[1], 'rb') as f:
        data = f.read()
    result = process_image(data)
    print(result)
```

### Step 2: Create a Job Specification

Create a job file:

```yaml
# job.yaml
name: "image-classification"
description: "Classify images using AI model"
type: "ai-inference"

model:
  type: "python"
  entrypoint: "model.py"
  requirements:
    - numpy==1.21.0
    - pillow==8.3.0
    - torch==1.9.0

input:
  type: "image"
  format: "jpeg"
  max_size: "10MB"

output:
  type: "json"
  schema:
    prediction: string
    confidence: float
    processing_time: float

resources:
  cpu: "1000m"
  memory: "2Gi"
  gpu: "1"

pricing:
  max_cost: "0.10"
  per_inference: "0.001"
```

### Step 3: Submit the Job

Submit your job to the marketplace:

```bash
# Using the CLI
aitbc job submit job.yaml

# Or using curl directly
curl -X POST http://localhost:8011/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d @job.json
```

You'll receive a job ID in response:
```json
{
  "job_id": "job_1234567890",
  "status": "submitted",
  "estimated_completion": "2024-01-01T12:00:00Z"
}
```

## 4. Monitor Job Progress

Track your job's progress:

```bash
# Check job status
aitbc job status job_1234567890

# Stream logs
aitbc job logs job_1234567890 --follow
```

## 5. Get Results

Once the job completes, retrieve the results:

```bash
# Get job results
aitbc job results job_1234567890

# Download output files
aitbc job download job_1234567890 --output ./results/
```

## 6. Interact with the Marketplace

### Browse Available Services

```bash
# List all available services
aitbc marketplace list

# Search for specific services
aitbc marketplace search --type "image-classification"
```

### Use a Service

```bash
# Use a service directly
aitbc marketplace use service_456 \
  --input ./test-image.jpg \
  --output ./result.json
```

## 7. Set Up a Wallet

Create a wallet to manage payments and rewards:

```bash
# Create a new wallet
aitbc wallet create

# Get wallet address
aitbc wallet address

# Check balance
aitbc wallet balance

# Fund your wallet (testnet only)
aitbc wallet fund --amount 10
```

## 8. Become a Miner

Run a miner to earn rewards:

```bash
# Configure mining settings
aitbc miner config \
  --gpu-count 1 \
  --max-jobs 5

# Start mining
aitbc miner start

# Check mining status
aitbc miner status
```

## Next Steps

Congratulations! You've successfully:
- ✅ Set up AITBC
- ✅ Created and submitted an AI job
- ✅ Interacted with the marketplace
- ✅ Set up a wallet
- ✅ Started mining

### What to explore next:

1. **Advanced Job Configuration**
   - Learn about [complex job types](user-guide/creating-jobs.md#advanced-jobs)
   - Explore [resource optimization](user-guide/creating-jobs.md#optimization)

2. **Marketplace Features**
   - Read about [pricing strategies](user-guide/marketplace.md#pricing)
   - Understand [reputation system](user-guide/marketplace.md#reputation)

3. **Development**
   - Check out the [Python SDK](developer-guide/sdks/python.md)
   - Explore [API documentation](api/coordinator/endpoints.md)

4. **Production Deployment**
   - Learn about [deployment strategies](operations/deployment.md)
   - Set up [monitoring](operations/monitoring.md)

## Troubleshooting

### Common Issues

**Service won't start**
```bash
# Check Docker logs
docker-compose logs coordinator

# Restart services
docker-compose restart
```

**Job submission fails**
```bash
# Verify API key
aitbc auth verify

# Check service status
aitbc status
```

**Connection errors**
```bash
# Check network connectivity
curl -v http://localhost:8011/v1/health

# Verify configuration
aitbc config show
```

### Get Help

- 📖 [Full Documentation](../)
- 💬 [Discord Community](https://discord.gg/aitbc)
- 🐛 [Report Issues](https://github.com/aitbc/issues)
- 📧 [Email Support](mailto:support@aitbc.io)

---

!!! tip "Pro Tip"
    Join our [Discord](https://discord.gg/aitbc) to connect with other developers and get real-time help from the AITBC team.

!!! note "Testnet vs Mainnet"
    This quickstart uses the AITBC testnet. All transactions are free and don't involve real money. When you're ready for production, switch to mainnet with `aitbc config set network mainnet`.
