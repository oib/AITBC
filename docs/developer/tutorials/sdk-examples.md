# SDK Usage Examples

This tutorial provides practical examples for using the AITBC SDKs in Python and JavaScript.

## Python SDK

### Installation

```bash
pip install aitbc-sdk
```

### Basic Usage

```python
from aitbc_sdk import AITBCClient

# Initialize client
client = AITBCClient(
    api_url="https://aitbc.bubuit.net/api",
    api_key="your-api-key"  # Optional
)

# Submit a simple job
result = client.submit_and_wait(
    prompt="What is the capital of France?",
    model="llama3.2"
)
print(result.output)
# Output: The capital of France is Paris.
```

### Job Management

```python
# Submit job (non-blocking)
job = client.submit_job(
    prompt="Write a haiku about coding",
    model="llama3.2",
    params={"max_tokens": 50, "temperature": 0.8}
)
print(f"Job ID: {job.id}")

# Check status
status = client.get_job_status(job.id)
print(f"Status: {status}")

# Wait for completion
result = client.wait_for_job(job.id, timeout=60)
print(f"Output: {result.output}")

# List recent jobs
jobs = client.list_jobs(limit=10, status="completed")
for j in jobs:
    print(f"{j.id}: {j.status}")
```

### Streaming Responses

```python
# Stream output as it's generated
for chunk in client.stream_job(
    prompt="Tell me a long story",
    model="llama3.2"
):
    print(chunk, end="", flush=True)
```

### Batch Processing

```python
# Submit multiple jobs
prompts = [
    "Translate 'hello' to French",
    "Translate 'hello' to Spanish",
    "Translate 'hello' to German"
]

jobs = client.submit_batch(prompts, model="llama3.2")

# Wait for all to complete
results = client.wait_for_batch(jobs, timeout=120)

for prompt, result in zip(prompts, results):
    print(f"{prompt} -> {result.output}")
```

### Receipt Handling

```python
from aitbc_sdk import ReceiptClient

receipt_client = ReceiptClient(api_url="https://aitbc.bubuit.net/api")

# Get receipt for a job
receipt = receipt_client.get_receipt(job_id="job-abc123")
print(f"Receipt ID: {receipt.receipt_id}")
print(f"Units: {receipt.units}")
print(f"Price: {receipt.price} AITBC")

# Verify receipt signature
is_valid = receipt_client.verify_receipt(receipt)
print(f"Valid: {is_valid}")

# List your receipts
receipts = receipt_client.list_receipts(client_address="ait1...")
total_spent = sum(r.price for r in receipts)
print(f"Total spent: {total_spent} AITBC")
```

### Error Handling

```python
from aitbc_sdk import AITBCClient, AITBCError, JobFailedError, TimeoutError

client = AITBCClient(api_url="https://aitbc.bubuit.net/api")

try:
    result = client.submit_and_wait(
        prompt="Complex task...",
        timeout=30
    )
except TimeoutError:
    print("Job took too long")
except JobFailedError as e:
    print(f"Job failed: {e.message}")
except AITBCError as e:
    print(f"API error: {e}")
```

### Async Support

```python
import asyncio
from aitbc_sdk import AsyncAITBCClient

async def main():
    client = AsyncAITBCClient(api_url="https://aitbc.bubuit.net/api")
    
    # Submit multiple jobs concurrently
    tasks = [
        client.submit_and_wait(f"Question {i}?")
        for i in range(5)
    ]
    
    results = await asyncio.gather(*tasks)
    
    for i, result in enumerate(results):
        print(f"Answer {i}: {result.output[:50]}...")

asyncio.run(main())
```

## JavaScript SDK

### Installation

```bash
npm install @aitbc/sdk
```

### Basic Usage

```javascript
import { AITBCClient } from '@aitbc/sdk';

const client = new AITBCClient({
  apiUrl: 'https://aitbc.bubuit.net/api',
  apiKey: 'your-api-key' // Optional
});

// Submit and wait
const result = await client.submitAndWait({
  prompt: 'What is 2 + 2?',
  model: 'llama3.2'
});

console.log(result.output);
// Output: 2 + 2 equals 4.
```

### Job Management

```javascript
// Submit job
const job = await client.submitJob({
  prompt: 'Explain quantum computing',
  model: 'llama3.2',
  params: { maxTokens: 256 }
});

console.log(`Job ID: ${job.id}`);

// Poll for status
const status = await client.getJobStatus(job.id);
console.log(`Status: ${status}`);

// Wait for completion
const result = await client.waitForJob(job.id, { timeout: 60000 });
console.log(`Output: ${result.output}`);
```

### Streaming

```javascript
// Stream response
const stream = client.streamJob({
  prompt: 'Write a poem',
  model: 'llama3.2'
});

for await (const chunk of stream) {
  process.stdout.write(chunk);
}
```

### React Hook

```jsx
import { useAITBC } from '@aitbc/react';

function ChatComponent() {
  const { submitJob, isLoading, result, error } = useAITBC();
  const [prompt, setPrompt] = useState('');

  const handleSubmit = async () => {
    await submitJob({ prompt, model: 'llama3.2' });
  };

  return (
    <div>
      <input
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Ask something..."
      />
      <button onClick={handleSubmit} disabled={isLoading}>
        {isLoading ? 'Thinking...' : 'Ask'}
      </button>
      {error && <p className="error">{error.message}</p>}
      {result && <p className="result">{result.output}</p>}
    </div>
  );
}
```

### TypeScript Types

```typescript
import { AITBCClient, Job, JobResult, Receipt } from '@aitbc/sdk';

interface MyJobParams {
  prompt: string;
  model: string;
  maxTokens?: number;
}

async function processJob(params: MyJobParams): Promise<JobResult> {
  const client = new AITBCClient({ apiUrl: '...' });
  
  const job: Job = await client.submitJob(params);
  const result: JobResult = await client.waitForJob(job.id);
  
  return result;
}
```

### Error Handling

```javascript
import { AITBCClient, AITBCError, TimeoutError } from '@aitbc/sdk';

const client = new AITBCClient({ apiUrl: '...' });

try {
  const result = await client.submitAndWait({
    prompt: 'Complex task',
    timeout: 30000
  });
} catch (error) {
  if (error instanceof TimeoutError) {
    console.log('Job timed out');
  } else if (error instanceof AITBCError) {
    console.log(`API error: ${error.message}`);
  } else {
    throw error;
  }
}
```

## Common Patterns

### Retry with Exponential Backoff

```python
import time
from aitbc_sdk import AITBCClient, AITBCError

def submit_with_retry(client, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.submit_and_wait(prompt)
        except AITBCError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt
            print(f"Retry in {wait_time}s...")
            time.sleep(wait_time)
```

### Caching Results

```python
import hashlib
import json
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_query(prompt_hash: str) -> str:
    # Cache based on prompt hash
    return client.submit_and_wait(prompt).output

def query(prompt: str) -> str:
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
    return cached_query(prompt_hash)
```

### Rate Limiting

```python
import time
from threading import Lock

class RateLimitedClient:
    def __init__(self, client, requests_per_minute=60):
        self.client = client
        self.min_interval = 60.0 / requests_per_minute
        self.last_request = 0
        self.lock = Lock()
    
    def submit(self, prompt):
        with self.lock:
            elapsed = time.time() - self.last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request = time.time()
        
        return self.client.submit_and_wait(prompt)
```

### Logging and Monitoring

```python
import logging
from aitbc_sdk import AITBCClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LoggingClient:
    def __init__(self, client):
        self.client = client
    
    def submit_and_wait(self, prompt, **kwargs):
        logger.info(f"Submitting job: {prompt[:50]}...")
        start = time.time()
        
        try:
            result = self.client.submit_and_wait(prompt, **kwargs)
            elapsed = time.time() - start
            logger.info(f"Job completed in {elapsed:.2f}s")
            return result
        except Exception as e:
            logger.error(f"Job failed: {e}")
            raise
```

## Next Steps

- [Coordinator API Integration](coordinator-api-integration.md)
- [Building a Custom Miner](building-custom-miner.md)
- [Python SDK Reference](../../reference/components/coordinator_api.md)
