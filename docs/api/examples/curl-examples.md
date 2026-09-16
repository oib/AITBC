# cURL Examples

> **Important:** This document provides cURL examples for interacting with the AITBC APIs. For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

This document provides comprehensive cURL examples for interacting with the AITBC APIs.

## Common Headers

```bash
# Coordinator customer auth: Bearer JWT from the wallet-signed login flow
# (POST /v1/auth/nonce -> POST /v1/login returns session_token)
export JWT="<YOUR_JWT>"
export BASE_URL="http://localhost:8203"

# Common curl command pattern (coordinator)
curl -H "Authorization: Bearer $JWT" $BASE_URL/v1/endpoint

# Service/legacy callers (and miner routes) may instead use:
#   -H "X-Api-Key: <key>"
# Blockchain RPC mutations use:  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY"
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
export BLOCKCHAIN_URL="http://localhost:8202"

curl $BLOCKCHAIN_URL/v1/head
```

#### Get Block by Height

```bash
curl $BLOCKCHAIN_URL/v1/blocks/12345
```

#### Get Block Range

```bash
curl "$BLOCKCHAIN_URL/v1/blocks-range?start=12340&end=12350"
```

### Transaction Operations

#### Get Transaction

```bash
curl $BLOCKCHAIN_URL/rpc/transaction/{tx_hash}
```

#### Submit Transaction

The transaction schema is `{chain_id?, from, to, amount, fee, nonce, type, payload, signature}` — integer `amount`/`fee` in compute-units, `nonce` equal to the sender's account nonce, and `signature` over the whole body. There are no `value`/`gas`/`data` fields.

```bash
curl -X POST $BLOCKCHAIN_URL/rpc/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "from": "0x...",
    "to": "0x...",
    "amount": 1000,
    "fee": 1,
    "nonce": 7,
    "type": "TRANSFER",
    "payload": {"to": "0x...", "amount": 1000},
    "signature": "0x..."
  }'
```

### Network Status

#### Get Network Info

```bash
curl $BLOCKCHAIN_URL/rpc/network-info
```

#### Get Subscribers (Peers)

```bash
curl $BLOCKCHAIN_URL/rpc/subscribers
```

### Smart Contract Operations

#### Call Contract (Read-only)

Contract calls go through `POST /rpc/contracts/call` (also mounted at `/v1/contracts/call`) with the contract address in the body — there is no per-address `/v1/contracts/{address}/call` route.

```bash
curl -X POST $BLOCKCHAIN_URL/v1/contracts/call \
  -H "Content-Type: application/json" \
  -d '{
    "address": "0x...",
    "method": "balanceOf",
    "params": {"account": "0x..."}
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

The coordinator-api has **no** WebSocket endpoints — job status is polled via `GET /v1/jobs/{job_id}`. The blockchain node has two WebSocket endpoints (see [websocket.md](../websocket.md)):

```bash
# Follower block subscription — requires a lease first:
#   curl -X POST $BLOCKCHAIN_URL/rpc/subscribe -H "X-API-Key: $PEER_KEY" -d '{"node_id": "...", "chain_id": "..."}'
# then connect and send {"node_id": "...", "chain_id": "...", "transport": "websocket"}
websocat ws://localhost:8202/rpc/subscribe/ws

# Public gossip topic (subscribe-only without validator auth)
websocat "ws://localhost:8202/rpc/gossip/ws?topic=mempool"
```

## Configuration Files

### .curlrc Configuration

```bash
# ~/.curlrc  (coordinator calls)
header = "Authorization: Bearer <YOUR_JWT>"
header = "Content-Type: application/json"
silent = false
show-error = true
```

### Environment Variables

```bash
# ~/.bashrc or ~/.zshrc
export AITBC_JWT="<YOUR_JWT>"
export AITBC_BASE_URL="http://localhost:8203"
export AITBC_BLOCKCHAIN_URL="http://localhost:8202"
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
