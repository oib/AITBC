# Creating Marketplace Extensions

This tutorial shows how to build extensions for the AITBC Marketplace.

## Overview

Marketplace extensions allow you to:
- Add new AI service types
- Create custom pricing models
- Build specialized interfaces
- Integrate third-party services

## Extension Types

| Type | Description | Example |
|------|-------------|---------|
| **Service** | New AI capability | Custom model hosting |
| **Widget** | UI component | Prompt builder |
| **Integration** | External service | Slack bot |
| **Analytics** | Metrics/reporting | Usage dashboard |

## Project Structure

```
my-extension/
├── manifest.json       # Extension metadata
├── src/
│   ├── index.ts       # Entry point
│   ├── service.ts     # Service logic
│   └── ui/            # UI components
├── assets/
│   └── icon.png       # Extension icon
└── package.json
```

## Step 1: Create Manifest

`manifest.json`:

```json
{
  "name": "my-custom-service",
  "version": "1.0.0",
  "description": "Custom AI service for AITBC",
  "type": "service",
  "author": "Your Name",
  "homepage": "https://github.com/you/my-extension",
  "permissions": [
    "jobs.submit",
    "jobs.read",
    "receipts.read"
  ],
  "entry": "src/index.ts",
  "icon": "assets/icon.png",
  "config": {
    "apiEndpoint": {
      "type": "string",
      "required": true,
      "description": "Your service API endpoint"
    },
    "apiKey": {
      "type": "secret",
      "required": true,
      "description": "API key for authentication"
    }
  }
}
```

## Step 2: Implement Service

`src/service.ts`:

```typescript
import { AITBCService, Job, JobResult } from '@aitbc/sdk';

export class MyCustomService implements AITBCService {
  name = 'my-custom-service';
  
  constructor(private config: { apiEndpoint: string; apiKey: string }) {}
  
  async initialize(): Promise<void> {
    // Validate configuration
    const response = await fetch(`${this.config.apiEndpoint}/health`);
    if (!response.ok) {
      throw new Error('Service endpoint not reachable');
    }
  }
  
  async processJob(job: Job): Promise<JobResult> {
    const response = await fetch(`${this.config.apiEndpoint}/process`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.config.apiKey}`
      },
      body: JSON.stringify({
        prompt: job.prompt,
        params: job.params
      })
    });
    
    if (!response.ok) {
      throw new Error(`Service error: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    return {
      output: data.result,
      metadata: {
        model: data.model,
        tokens_used: data.tokens
      }
    };
  }
  
  async estimateCost(job: Job): Promise<number> {
    // Estimate cost in AITBC tokens
    const estimatedTokens = job.prompt.length / 4;
    return estimatedTokens * 0.001; // 0.001 AITBC per token
  }
  
  getCapabilities(): string[] {
    return ['text-generation', 'summarization'];
  }
}
```

## Step 3: Create Entry Point

`src/index.ts`:

```typescript
import { ExtensionContext, registerService } from '@aitbc/sdk';
import { MyCustomService } from './service';

export async function activate(context: ExtensionContext): Promise<void> {
  const config = context.getConfig();
  
  const service = new MyCustomService({
    apiEndpoint: config.apiEndpoint,
    apiKey: config.apiKey
  });
  
  await service.initialize();
  
  registerService(service);
  
  console.log('My Custom Service extension activated');
}

export function deactivate(): void {
  console.log('My Custom Service extension deactivated');
}
```

## Step 4: Add UI Widget (Optional)

`src/ui/PromptBuilder.tsx`:

```tsx
import React, { useState } from 'react';
import { useAITBC } from '@aitbc/react';

export function PromptBuilder() {
  const [prompt, setPrompt] = useState('');
  const { submitJob, isLoading } = useAITBC();
  
  const handleSubmit = async () => {
    const result = await submitJob({
      service: 'my-custom-service',
      prompt,
      params: { max_tokens: 256 }
    });
    console.log('Result:', result);
  };
  
  return (
    <div className="prompt-builder">
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Enter your prompt..."
      />
      <button onClick={handleSubmit} disabled={isLoading}>
        {isLoading ? 'Processing...' : 'Submit'}
      </button>
    </div>
  );
}
```

## Step 5: Package and Deploy

### Build

```bash
npm run build
```

### Test Locally

```bash
npm run dev
# Extension runs at http://localhost:3000
```

### Deploy to Marketplace

```bash
# Package extension
npm run package
# Creates my-extension-1.0.0.zip

# Submit to marketplace
aitbc-cli extension submit my-extension-1.0.0.zip
```

## Pricing Models

### Per-Request Pricing

```typescript
async estimateCost(job: Job): Promise<number> {
  return 1.0; // Fixed 1 AITBC per request
}
```

### Token-Based Pricing

```typescript
async estimateCost(job: Job): Promise<number> {
  const inputTokens = job.prompt.length / 4;
  const outputTokens = job.params.max_tokens || 256;
  return (inputTokens + outputTokens) * 0.001;
}
```

### Tiered Pricing

```typescript
async estimateCost(job: Job): Promise<number> {
  const tokens = job.prompt.length / 4;
  if (tokens < 100) return 0.5;
  if (tokens < 1000) return 2.0;
  return 5.0;
}
```

## Best Practices

1. **Validate inputs** - Check all user inputs before processing
2. **Handle errors gracefully** - Return meaningful error messages
3. **Respect rate limits** - Don't overwhelm external services
4. **Cache when possible** - Reduce redundant API calls
5. **Log appropriately** - Use structured logging for debugging
6. **Version your API** - Support backward compatibility

## Testing

```typescript
import { MyCustomService } from './service';

describe('MyCustomService', () => {
  it('should process job successfully', async () => {
    const service = new MyCustomService({
      apiEndpoint: 'http://localhost:8080',
      apiKey: 'test-key'
    });
    
    const result = await service.processJob({
      prompt: 'Hello, world!',
      params: {}
    });
    
    expect(result.output).toBeDefined();
  });
});
```

## Next Steps

- [Coordinator API Integration](coordinator-api-integration.md)
- [SDK Examples](sdk-examples.md)
- [Existing Extensions](../../tutorials/marketplace-extensions.md)
