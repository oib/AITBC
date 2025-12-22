---
title: JavaScript SDK
description: JavaScript/TypeScript SDK for AITBC platform integration
---

# JavaScript SDK

The AITBC JavaScript SDK provides a convenient way to interact with the AITBC platform from JavaScript and TypeScript applications.

## Installation

```bash
# npm
npm install @aitbc/client

# yarn
yarn add @aitbc/client

# pnpm
pnpm add @aitbc/client
```

## Quick Start

```javascript
import { AITBCClient } from '@aitbc/client';

// Initialize the client
const client = new AITBCClient({
  apiKey: 'your_api_key_here',
  baseUrl: 'https://api.aitbc.io'
});

// Create a job
const job = await client.jobs.create({
  name: 'image-classification',
  type: 'ai-inference',
  model: {
    type: 'python',
    entrypoint: 'model.js'
  }
});

console.log('Job created:', job.jobId);
```

## Configuration

### Environment Variables
```bash
AITBC_API_KEY=your_api_key
AITBC_BASE_URL=https://api.aitbc.io
AITBC_NETWORK=mainnet
```

### Code Configuration
```javascript
const client = new AITBCClient({
  apiKey: process.env.AITBC_API_KEY,
  baseUrl: process.env.AITBC_BASE_URL,
  timeout: 30000,
  retries: 3
});
```

## Jobs API

### Create a Job
```javascript
const job = await client.jobs.create({
  name: 'my-ai-job',
  type: 'ai-inference',
  model: {
    type: 'javascript',
    entrypoint: 'model.js',
    dependencies: ['@tensorflow/tfjs']
  },
  input: {
    type: 'image',
    format: 'jpeg'
  },
  output: {
    type: 'json'
  }
});
```

### Monitor Job Progress
```javascript
// Get job status
const status = await client.jobs.getStatus(job.jobId);
console.log('Status:', status.status);

// Stream updates
client.jobs.onUpdate(job.jobId, (update) => {
  console.log('Update:', update);
});

// Wait for completion
const result = await client.jobs.waitForCompletion(job.jobId, {
  timeout: 300000,
  pollInterval: 5000
});
```

## Marketplace API

### List Offers
```javascript
const offers = await client.marketplace.listOffers({
  jobType: 'image-classification',
  maxPrice: '0.01'
});

offers.forEach(offer => {
  console.log(`Offer: ${offer.offerId}, Price: ${offer.price}`);
});
```

### Accept Offer
```javascript
const transaction = await client.marketplace.acceptOffer({
  offerId: 'offer_123',
  jobId: 'job_456',
  bidPrice: '0.001'
});
```

## Wallet API

### Wallet Operations
```javascript
// Get balance
const balance = await client.wallet.getBalance();
console.log('Balance:', balance);

// Send tokens
const tx = await client.wallet.send({
  to: '0x123...',
  amount: '1.0',
  token: 'AITBC'
});

// Stake tokens
await client.wallet.stake({
  amount: '100.0'
});
```

## WebSocket API

### Real-time Updates
```javascript
// Connect to WebSocket
const ws = client.websocket.connect();

// Subscribe to events
ws.subscribe('jobs', { jobId: 'job_123' });
ws.subscribe('marketplace');

// Handle events
ws.on('jobUpdate', (data) => {
  console.log('Job updated:', data);
});

ws.on('marketplaceUpdate', (data) => {
  console.log('Marketplace updated:', data);
});

// Start listening
ws.start();
```

## TypeScript Support

The SDK is fully typed for TypeScript:

```typescript
import { AITBCClient, Job, JobStatus } from '@aitbc/client';

const client: AITBCClient = new AITBCClient({
  apiKey: 'your_key'
});

const job: Job = await client.jobs.create({
  name: 'typed-job',
  type: 'ai-inference'
});

const status: JobStatus = await client.jobs.getStatus(job.jobId);
```

## Error Handling

```javascript
import { 
  AITBCError,
  APIError,
  AuthenticationError,
  NotFoundError,
  RateLimitError 
} from '@aitbc/client';

try {
  const job = await client.jobs.create({});
} catch (error) {
  if (error instanceof AuthenticationError) {
    console.error('Invalid API key');
  } else if (error instanceof RateLimitError) {
    console.error(`Rate limited. Retry in ${error.retryAfter}ms`);
  } else if (error instanceof APIError) {
    console.error(`API error: ${error.message}`);
  }
}
```

## React Integration

```jsx
import React, { useState, useEffect } from 'react';
import { AITBCClient } from '@aitbc/client';

function JobComponent() {
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
        <div key={job.jobId}>{job.name}</div>
      ))}
    </div>
  );
}
```

## Node.js Integration

```javascript
const express = require('express');
const { AITBCClient } = require('@aitbc/client');

const app = express();
const client = new AITBCClient({ apiKey: process.env.API_KEY });

app.post('/jobs', async (req, res) => {
  try {
    const job = await client.jobs.create(req.body);
    res.json(job);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(3000);
```

## Examples

Check out the [examples directory](https://github.com/aitbc/js-sdk/tree/main/examples) for complete working examples:

- [Basic Job Submission](https://github.com/aitbc/js-sdk/blob/main/examples/basic-job.js)
- [React Integration](https://github.com/aitbc/js-sdk/blob/main/examples/react-app/)
- [WebSocket Streaming](https://github.com/aitbc/js-sdk/blob/main/examples/websocket.js)

## Support

- 📖 [Documentation](../../)
- 🐛 [Issue Tracker](https://github.com/aitbc/js-sdk/issues)
- 💬 [Discord](https://discord.gg/aitbc)
- 📧 [js-sdk@aitbc.io](mailto:js-sdk@aitbc.io)
