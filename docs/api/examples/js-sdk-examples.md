# JavaScript/TypeScript SDK Examples

This document provides comprehensive examples for using the AITBC JavaScript/TypeScript SDK.

## Installation

```bash
npm install @aitbc/aitbc-sdk
```

## Basic Setup

```typescript
import { AITBCClient } from '@aitbc/aitbc-sdk';

// Initialize client
const client = new AITBCClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:8203'
});
```

## Job Submission

### Simple Job Submission

```typescript
// Submit a simple job
const job = await client.submitJob({
  payload: {
    model: 'llama2',
    prompt: 'Hello, world!'
  },
  ttlSeconds: 900
});

console.log(`Job ID: ${job.jobId}`);
console.log(`State: ${job.state}`);
```

### Job with Constraints

```typescript
// Submit job with GPU constraints
const job = await client.submitJob({
  payload: {
    model: 'llama2',
    prompt: 'Hello, world!'
  },
  constraints: {
    minGpuMemory: 8,
    gpuType: 'nvidia-rtx-3090'
  },
  ttlSeconds: 900
});
```

### Job with Payment

```typescript
// Submit job with payment
const job = await client.submitJob({
  payload: {
    model: 'llama2',
    prompt: 'Hello, world!'
  },
  paymentAmount: 100.0,
  paymentCurrency: 'AITBC',
  ttlSeconds: 900
});

console.log(`Payment ID: ${job.paymentId}`);
```

## Job Status Monitoring

### Get Job Status

```typescript
// Get current job status
const status = await client.getJob('your-job-id');
console.log(`State: ${status.state}`);
console.log(`Assigned Miner: ${status.assignedMinerId}`);
console.log(`Error: ${status.error}`);
```

### Poll for Completion

```typescript
async function waitForCompletion(jobId: string): Promise<void> {
  while (true) {
    const status = await client.getJob(jobId);
    console.log(`State: ${status.state}`);
    
    if (['COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED'].includes(status.state)) {
      break;
    }
    
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
}

waitForCompletion('your-job-id');
```

### WebSocket for Real-time Updates

```typescript
// Monitor job status via WebSocket
const ws = client.watchJob('your-job-id', (update) => {
  console.log(`Status update: ${JSON.stringify(update)}`);
});

// Close connection when done
ws.close();
```

## Job Results

### Get Job Result

```typescript
// Get job result
const result = await client.getJobResult('your-job-id');
console.log(`Output: ${JSON.stringify(result.result)}`);
console.log(`Receipt: ${JSON.stringify(result.receipt)}`);
```

### Get Receipts

```typescript
// Get latest receipt
const receipt = await client.getReceipt('your-job-id');
console.log(`Signature: ${receipt.signature}`);

// Get all receipts
const receipts = await client.listReceipts('your-job-id');
for (const receipt of receipts) {
  console.log(`Receipt: ${receipt.signature}`);
}
```

## Job Cancellation

```typescript
// Cancel a job
const cancelledJob = await client.cancelJob('your-job-id');
console.log(`State: ${cancelledJob.state}`);
```

## Payment Operations

### Get Payment Status

```typescript
// Get payment information
const payment = await client.getPayment('your-job-id');
console.log(`Status: ${payment.status}`);
console.log(`Amount: ${payment.amount}`);
```

## Blockchain Operations

### Initialize Blockchain Client

```typescript
import { BlockchainClient } from '@aitbc/aitbc-sdk';

const blockchain = new BlockchainClient({
  baseUrl: 'http://localhost:8006'
});
```

### Get Block Information

```typescript
// Get head block
const headBlock = await blockchain.getHeadBlock();
console.log(`Current height: ${headBlock.height}`);

// Get block by height
const block = await blockchain.getBlock(12345);
console.log(`Block hash: ${block.hash}`);
```

### Network Status

```typescript
// Get network information
const network = await blockchain.getNetworkInfo();
console.log(`Peer count: ${network.peerCount}`);
console.log(`Chain ID: ${network.chainId}`);

// Get peers
const peers = await blockchain.getPeers();
for (const peer of peers) {
  console.log(`Peer: ${peer.address}`);
}
```

### Transaction Operations

```typescript
// Get transaction
const tx = await blockchain.getTransaction('0x...');
console.log(`From: ${tx.from}`);
console.log(`To: ${tx.to}`);
console.log(`Value: ${tx.value}`);
```

## Error Handling

```typescript
import { APIError, AuthenticationError } from '@aitbc/aitbc-sdk';

try {
  const job = await client.submitJob({
    payload: { model: 'llama2', prompt: 'Hello' }
  });
} catch (error) {
  if (error instanceof AuthenticationError) {
    console.error('Invalid API key');
  } else if (error instanceof APIError) {
    console.error(`API error: ${error.message}`);
  } else {
    console.error(`Unexpected error: ${error}`);
  }
}
```

## Advanced Examples

### Batch Job Submission

```typescript
// Submit multiple jobs
const prompts = ['Hello', 'World', 'Test'];
const jobs = await Promise.all(
  prompts.map(prompt =>
    client.submitJob({
      payload: { model: 'llama2', prompt },
      ttlSeconds: 900
    })
  )
);

console.log(`Submitted ${jobs.length} jobs`);
```

### Job History

```typescript
// Get job history
const history = await client.getJobHistory({ limit: 10 });
for (const job of history) {
  console.log(`Job ${job.jobId}: ${job.state}`);
}
```

### Custom Headers

```typescript
// Use custom headers
const client = new AITBCClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:8203',
  headers: {
    'X-Custom-Header': 'value'
  }
});
```

## TypeScript Configuration

```typescript
// Enable strict type checking
{
  "compilerOptions": {
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  }
}
```

## Configuration

### Environment Variables

```typescript
import dotenv from 'dotenv';
dotenv.config();

const client = new AITBCClient({
  apiKey: process.env.AITBC_API_KEY || '',
  baseUrl: process.env.AITBC_BASE_URL || 'http://localhost:8203'
});
```

### Timeout Configuration

```typescript
const client = new AITBCClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:8203',
  timeout: 30000 // 30 second timeout
});
```

## React Integration

```typescript
import { useState, useEffect } from 'react';
import { AITBCClient } from '@aitbc/aitbc-sdk';

function JobComponent({ jobId }: { jobId: string }) {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const client = new AITBCClient({
      apiKey: 'your-api-key',
      baseUrl: 'http://localhost:8203'
    });

    const fetchStatus = async () => {
      try {
        const job = await client.getJob(jobId);
        setStatus(job.state);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      }
    };

    fetchStatus();
  }, [jobId]);

  if (error) return <div>Error: {error}</div>;
  return <div>Job Status: {status}</div>;
}
```

## Node.js Integration

```typescript
import express from 'express';
import { AITBCClient } from '@aitbc/aitbc-sdk';

const app = express();
const client = new AITBCClient({
  apiKey: process.env.AITBC_API_KEY!,
  baseUrl: process.env.AITBC_BASE_URL!
});

app.post('/api/jobs', async (req, res) => {
  try {
    const job = await client.submitJob(req.body);
    res.json(job);
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : 'Unknown error' });
  }
});

app.listen(3000);
```

## Testing

```typescript
import { describe, it, expect, vi } from 'vitest';
import { AITBCClient } from '@aitbc/aitbc-sdk';

describe('AITBCClient', () => {
  it('should submit job successfully', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: 'test-id',
        state: 'QUEUED'
      })
    });

    global.fetch = mockFetch;

    const client = new AITBCClient({
      apiKey: 'test-key',
      baseUrl: 'http://localhost:8203'
    });

    const job = await client.submitJob({
      payload: { model: 'test', prompt: 'Hello' }
    });

    expect(job.jobId).toBe('test-id');
  });
});
```

## Receipt Verification

```typescript
import { verifyReceipt } from '@aitbc/aitbc-sdk';

// Verify receipt signature
const receipt = await client.getReceipt('your-job-id');
const isValid = verifyReceipt(
  receipt.signature,
  receipt.data,
  'miner-public-key'
);

if (isValid) {
  console.log('Receipt is valid');
} else {
  console.log('Receipt is invalid');
}
```
