# @aitbc/aitbc-sdk

JavaScript/TypeScript SDK for interacting with AITBC coordinator services, blockchain nodes, and marketplace components.

## Installation

```bash
npm install @aitbc/aitbc-sdk
# or
yarn add @aitbc/aitbc-sdk
# or
pnpm add @aitbc/aitbc-sdk
```

## Quick Start

```typescript
import { createClient } from '@aitbc/aitbc-sdk';

// Initialize client
const client = createClient({
  baseUrl: 'https://aitbc.bubuit.net',
  apiKey: 'your-api-key',
});

// Submit a job
const job = await client.submitJob({
  service_type: 'llm_inference',
  model: 'llama3.2',
  parameters: {
    prompt: 'Hello, world!',
    max_tokens: 100
  }
});

// Check job status
const status = await client.getJobStatus(job.id);
console.log(`Job status: ${status.status}`);

// Get results when complete
if (status.status === 'completed') {
  const result = await client.getJobResult(job.id);
  console.log(`Result:`, result.output);
}
```

## Features

- **Job Management**: Submit, monitor, and retrieve computation jobs
- **Receipt Verification**: Cryptographically verify job completion receipts
- **Marketplace Integration**: Browse and participate in GPU marketplace
- **Blockchain Integration**: Interact with AITBC blockchain for settlement
- **Authentication**: Secure session management for marketplace operations
- **Type Safety**: Full TypeScript support with comprehensive type definitions

## API Reference

### Client Initialization

```typescript
import { AitbcClient, createClient } from '@aitbc/aitbc-sdk';

// Method 1: Using createClient helper
const client = createClient({
  baseUrl: 'https://aitbc.bubuit.net',
  apiKey: 'your-api-key',
  timeout: 30000,
});

// Method 2: Using class directly
const client = new AitbcClient({
  baseUrl: 'https://aitbc.bubuit.net',
  apiKey: 'your-api-key',
  basicAuth: {
    username: 'user',
    password: 'pass'
  },
  fetchImpl: fetch, // Optional custom fetch implementation
  timeout: 30000,
});
```

### Job Operations

```typescript
// Submit a job
const job = await client.submitJob({
  service_type: 'llm_inference',
  model: 'llama3.2',
  parameters: {
    prompt: 'Explain quantum computing',
    max_tokens: 500
  }
});

// Get job details
const jobDetails = await client.getJob(job.id);

// Get job status
const status = await client.getJobStatus(job.id);

// Get job result
const result = await client.getJobResult(job.id);

// Cancel a job
await client.cancelJob(job.id);

// List all jobs
const jobs = await client.listJobs();
```

### Receipt Operations

```typescript
// Get job receipts
const receipts = await client.getJobReceipts(job.id);

// Verify receipt authenticity
const verification = await client.verifyReceipt(receipts.items[0]);
console.log(`Receipt valid: ${verification.valid}`);
```

### Marketplace Operations

```typescript
// Get marketplace statistics
const stats = await client.getMarketplaceStats();

// List available offers
const offers = await client.getMarketplaceOffers();

// Get specific offer details
const offer = await client.getMarketplaceOffer(offer.id);

// Submit a bid
await client.submitMarketplaceBid({
  provider: 'gpu-provider-123',
  capacity: 1000,
  price: 0.05,
  notes: 'Need GPU for ML training'
});
```

### Blockchain Explorer

```typescript
// Get latest blocks
const blocks = await client.getBlocks();

// Get specific block
const block = await client.getBlock(12345);

// Get transactions
const transactions = await client.getTransactions();

// Get address details
const address = await client.getAddress('0x1234...abcd');
```

### Authentication

```typescript
// Login for marketplace operations
const session = await client.login({
  username: 'user@example.com',
  password: 'secure-password'
});

// Logout
await client.logout();
```

### Coordinator API

```typescript
// Health check
const health = await client.health();
console.log(`Service status: ${health.status}`);

// Get metrics
const metrics = await client.metrics();
console.log(`Raw metrics: ${metrics.raw}`);

// Find matching miners
const matches = await client.match({
  jobId: 'job-123',
  requirements: {
    gpu_memory: '8GB',
    compute_capability: '7.5'
  },
  topK: 3
});
```

## Error Handling

The SDK throws descriptive errors for failed requests:

```typescript
try {
  const job = await client.submitJob(jobData);
} catch (error) {
  if (error instanceof Error) {
    console.error(`Job submission failed: ${error.message}`);
    // Handle specific error codes
    if (error.message.includes('400')) {
      // Bad request - invalid parameters
    } else if (error.message.includes('401')) {
      // Unauthorized - invalid API key
    } else if (error.message.includes('500')) {
      // Server error - try again later
    }
  }
}
```

## Configuration

### Environment Variables

```bash
# Optional: Set default base URL
AITBC_BASE_URL=https://aitbc.bubuit.net

# Optional: Set default API key
AITBC_API_KEY=your-api-key
```

### Advanced Configuration

```typescript
const client = createClient({
  baseUrl: process.env.AITBC_BASE_URL || 'https://aitbc.bubuit.net',
  apiKey: process.env.AITBC_API_KEY,
  timeout: 30000,
  fetchImpl: async (url, options) => {
    // Custom fetch implementation (e.g., with retry logic)
    return fetch(url, options);
  }
});
```

## TypeScript Support

The SDK provides comprehensive TypeScript definitions:

```typescript
import type { 
  Job, 
  JobSubmission, 
  MarketplaceOffer, 
  ReceiptSummary,
  BlockSummary 
} from '@aitbc/aitbc-sdk';

// Full type safety and IntelliSense support
const job: Job = await client.getJob(jobId);
const offers: MarketplaceOffer[] = await client.getMarketplaceOffers();
```

## Browser Support

The SDK works in all modern browsers with native `fetch` support. For older browsers, include a fetch polyfill:

```html
<!-- For older browsers -->
<script src="https://cdn.jsdelivr.net/npm/whatwg-fetch@3.6.2/dist/fetch.umd.js"></script>
```

## Node.js Usage

In Node.js environments, the SDK uses the built-in `fetch` (Node.js 18+) or requires a fetch polyfill:

```bash
npm install node-fetch
```

```typescript
import fetch from 'node-fetch';

const client = createClient({
  baseUrl: 'https://aitbc.bubuit.net',
  fetchImpl: fetch as any,
});
```

## Development

Install in development mode:

```bash
git clone https://github.com/oib/AITBC.git
cd AITBC/packages/js/aitbc-sdk
npm install
npm run build
```

Run tests:

```bash
npm test
```

Run tests in watch mode:

```bash
npm run test:watch
```

## License

MIT License - see LICENSE file for details.

## Support

- **Documentation**: https://aitbc.bubuit.net/docs/
- **Issues**: https://github.com/oib/AITBC/issues
- **Discussions**: https://github.com/oib/AITBC/discussions
- **Email**: team@aitbc.dev

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Changelog

### 0.1.0
- Initial release
- Full TypeScript support
- Job management API
- Marketplace integration
- Blockchain explorer
- Receipt verification
- Authentication support
