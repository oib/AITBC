---
title: Code Examples
description: Practical examples for building on AITBC
---

# Code Examples

This section provides practical examples for common tasks on the AITBC platform.

## Python Examples

### Basic Job Submission
```python
from aitbc import AITBCClient

client = AITBCClient(api_key="your_key")

job = client.jobs.create({
    "name": "image-classification",
    "type": "ai-inference",
    "model": {
        "type": "python",
        "entrypoint": "model.py",
        "requirements": ["torch", "pillow"]
    }
})

result = client.jobs.wait_for_completion(job["job_id"])
```

### Batch Job Processing
```python
import asyncio
from aitbc import AsyncAITBCClient

async def process_images(image_paths):
    client = AsyncAITBCClient(api_key="your_key")
    
    tasks = []
    for path in image_paths:
        job = await client.jobs.create({
            "name": f"process-{path}",
            "type": "image-analysis"
        })
        tasks.append(client.jobs.wait_for_completion(job["job_id"]))
    
    results = await asyncio.gather(*tasks)
    return results
```

## JavaScript Examples

### React Component
```jsx
import React, { useState, useEffect } from 'react';
import { AITBCClient } from '@aitbc/client';

function JobList() {
    const [jobs, setJobs] = useState([]);
    const client = new AITBCClient({ apiKey: 'your_key' });
    
    useEffect(() => {
        async function fetchJobs() {
            const jobList = await client.jobs.list();
            setJobs(jobList);
        }
        fetchJobs();
    }, []);
    
    return (
        <div>
            {jobs.map(job => (
                <div key={job.jobId}>
                    <h3>{job.name}</h3>
                    <p>Status: {job.status}</p>
                </div>
            ))}
        </div>
    );
}
```

### WebSocket Integration
```javascript
const client = new AITBCClient({ apiKey: 'your_key' });
const ws = client.websocket.connect();

ws.on('jobUpdate', (data) => {
    console.log(`Job ${data.jobId} updated to ${data.status}`);
});

ws.subscribe('jobs');
ws.start();
```

## CLI Examples

### Job Management
```bash
# Create job from file
aitbc job create job.yaml

# List all jobs
aitbc job list --status running

# Monitor job progress
aitbc job watch <job_id>

# Download results
aitbc job download <job_id> --output ./results/
```

### Marketplace Operations
```bash
# List available offers
aitbc marketplace list --type image-classification

# Create offer as miner
aitbc marketplace create-offer offer.yaml

# Accept offer
aitbc marketplace accept <offer_id> --job-id <job_id>
```

## Complete Examples

Find full working examples in our GitHub repositories:
- [Python SDK Examples](https://github.com/aitbc/python-sdk/tree/main/examples)
- [JavaScript SDK Examples](https://github.com/aitbc/js-sdk/tree/main/examples)
- [CLI Examples](https://github.com/aitbc/cli/tree/main/examples)
- [Smart Contract Examples](https://github.com/aitbc/contracts/tree/main/examples)
