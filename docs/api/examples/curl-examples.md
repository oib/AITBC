# cURL Examples

> **Important:** This document provides cURL examples for interacting with the AITBC APIs. For the current operational state and deployment status, see [Current Operational State](../infrastructure/CURRENT_OPERATIONAL_STATE.md). For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

This document provides comprehensive cURL examples for interacting with the AITBC APIs.

## Common Headers

```bash
# Set API key header
export API_KEY="your-api-key"
export BASE_URL="http://localhost:8011"

# Common curl command pattern
curl -H "X-Api-Key: $API_KEY" $BASE_URL/v1/endpoint
```

## Coordinator API Examples

### Job Submission

#### Simple Job Submission

```bash
curl -X POST $BASE_URL/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{
    "payload": {
      "model": "llama2",
      "prompt": "Hello, world!"
    },
    "ttl_seconds": 900
  }'
```

#### Job with Constraints

```bash
curl -X POST $BASE_URL/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{
    "payload": {
      "model": "llama2",
      "prompt": "Hello, world!"
    },
    "constraints": {
      "min_gpu_memory": 8,
      "gpu_type": "nvidia-rtx-3090"
    },
    "ttl_seconds": 900
  }'
```

#### Job with Payment

```bash
curl -X POST $BASE_URL/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{
    "payload": {
      "model": "llama2",
      "prompt": "Hello, world!"
    },
    "payment_amount": 100.0,
    "payment_currency": "AITBC",
    "ttl_seconds": 900
  }'
```

### Job Status

#### Get Job Status

```bash
curl -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}
```

#### Poll for Completion

```bash
#!/bin/bash

JOB_ID="your-job-id"

while true; do
  STATUS=$(curl -s -H "X-Api-Key: $API_KEY" \
    $BASE_URL/v1/jobs/$JOB_ID | jq -r '.state')
  
  echo "State: $STATUS"
  
  if [[ "$STATUS" =~ ^(COMPLETED|FAILED|CANCELLED|EXPIRED)$ ]]; then
    break
  fi
  
  sleep 5
done
```

### Job Results

#### Get Job Result

```bash
curl -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}/result
```

#### Get Receipts

```bash
# Get latest receipt
curl -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}/receipt

# Get all receipts
curl -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}/receipts
```

### Job Cancellation

```bash
curl -X POST \
  -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}/cancel
```

### Payment Operations

#### Get Payment Status

```bash
curl -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}/payment
```

## Blockchain API Examples

### Block Operations

#### Get Head Block

```bash
export BLOCKCHAIN_URL="http://localhost:8006"

curl $BLOCKCHAIN_URL/v1/blocks/head
```

#### Get Block by Height

```bash
curl $BLOCKCHAIN_URL/v1/blocks/12345
```

#### Get Block Range

```bash
curl "$BLOCKCHAIN_URL/v1/blocks?from=12340&to=12350"
```

### Transaction Operations

#### Get Transaction

```bash
curl $BLOCKCHAIN_URL/v1/transactions/{tx_hash}
```

#### Submit Transaction

```bash
curl -X POST $BLOCKCHAIN_URL/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "from": "0x...",
    "to": "0x...",
    "value": 1000,
    "gas": 21000,
    "data": "0x...",
    "signature": "0x..."
  }'
```

### Network Status

#### Get Network Info

```bash
curl $BLOCKCHAIN_URL/v1/network
```

#### Get Peers

```bash
curl $BLOCKCHAIN_URL/v1/network/peers
```

### Smart Contract Operations

#### Call Contract (Read-only)

```bash
curl -X POST $BLOCKCHAIN_URL/v1/contracts/{address}/call \
  -H "Content-Type: application/json" \
  -d '{
    "method": "balanceOf",
    "args": ["0x..."]
  }'
```

#### Send Transaction to Contract (State-changing)

```bash
curl -X POST $BLOCKCHAIN_URL/v1/contracts/{address}/transact \
  -H "Content-Type: application/json" \
  -d '{
    "method": "transfer",
    "args": ["0x...", 1000],
    "gas": 100000,
    "value": 0
  }'
```

## Advanced cURL Examples

### Using jq for JSON Processing

```bash
# Extract job ID from response
JOB_ID=$(curl -s -X POST $BASE_URL/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"payload": {"model": "llama2", "prompt": "Hello"}, "ttl_seconds": 900}' \
  | jq -r '.job_id')

echo "Job ID: $JOB_ID"
```

### Pretty Print JSON Output

```bash
curl -s -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id} | jq '.'
```

### Extract Specific Fields

```bash
# Get job state only
curl -s -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id} | jq -r '.state'

# Get multiple fields
curl -s -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id} | jq '{state: .state, assigned_miner_id: .assigned_miner_id}'
```

### Batch Operations

```bash
# Submit multiple jobs
for prompt in "Hello" "World" "Test"; do
  curl -X POST $BASE_URL/v1/jobs \
    -H "Content-Type: application/json" \
    -H "X-Api-Key: $API_KEY" \
    -d "{\"payload\": {\"model\": \"llama2\", \"prompt\": \"$prompt\"}, \"ttl_seconds\": 900}" &
done

wait
```

### Error Handling

```bash
# Check HTTP status code
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id})

if [ $HTTP_CODE -eq 200 ]; then
  echo "Success"
else
  echo "Failed with status code: $HTTP_CODE"
fi
```

### Rate Limiting

```bash
# Add delay between requests to respect rate limits
for i in {1..10}; do
  curl -H "X-Api-Key: $API_KEY" \
    $BASE_URL/v1/jobs/{job_id}
  sleep 1  # 1 second delay
done
```

### Retry Logic

```bash
#!/bin/bash

MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "X-Api-Key: $API_KEY" \
    $BASE_URL/v1/jobs/{job_id})
  
  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | head -n-1)
  
  if [ $HTTP_CODE -eq 200 ]; then
    echo "$BODY"
    exit 0
  fi
  
  echo "Attempt $i failed with status $HTTP_CODE"
  sleep $RETRY_DELAY
done

echo "Max retries exceeded"
exit 1
```

### File Upload

```bash
# Upload file as job payload
curl -X POST $BASE_URL/v1/jobs \
  -H "Content-Type: multipart/form-data" \
  -H "X-Api-Key: $API_KEY" \
  -F "payload=@input.json" \
  -F "ttl_seconds=900"
```

### Download Results

```bash
# Download job result to file
curl -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}/result \
  -o result.json
```

### WebSocket Testing

```bash
# Test WebSocket connection (requires websocat)
websocat ws://localhost:8011/v1/jobs/{job_id}/ws
```

## Configuration Files

### .curlrc Configuration

```bash
# ~/.curlrc
header = "X-Api-Key: your-api-key"
header = "Content-Type: application/json"
silent = false
show-error = true
```

### Environment Variables

```bash
# ~/.bashrc or ~/.zshrc
export AITBC_API_KEY="your-api-key"
export AITBC_BASE_URL="http://localhost:8011"
export AITBC_BLOCKCHAIN_URL="http://localhost:8006"
```

### Shell Functions

```bash
# Add to ~/.bashrc or ~/.zshrc

# Submit job function
aitbc-submit() {
  curl -X POST $AITBC_BASE_URL/v1/jobs \
    -H "Content-Type: application/json" \
    -H "X-Api-Key: $AITBC_API_KEY" \
    -d "$1"
}

# Get job function
aitbc-job() {
  curl -H "X-Api-Key: $AITBC_API_KEY" \
    $AITBC_BASE_URL/v1/jobs/$1
}

# Get result function
aitbc-result() {
  curl -H "X-Api-Key: $AITBC_API_KEY" \
    $AITBC_BASE_URL/v1/jobs/$1/result
}
```

## Debugging

### Verbose Output

```bash
curl -v -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}
```

### Include Headers in Response

```bash
curl -i -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}
```

### Timing Information

```bash
curl -w "@curl-format.txt" \
  -H "X-Api-Key: $API_KEY" \
  $BASE_URL/v1/jobs/{job_id}
```

### curl-format.txt

```
     time_namelookup:  %{time_namelookup}s\n
        time_connect:  %{time_connect}s\n
     time_appconnect:  %{time_appconnect}s\n
    time_pretransfer:  %{time_pretransfer}s\n
       time_redirect:  %{time_redirect}s\n
  time_starttransfer:  %{time_starttransfer}s\n
                     ----------\n
          time_total:  %{time_total}s\n
```
