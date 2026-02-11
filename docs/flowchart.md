# AITBC System Flow: From CLI Prompt to Response

This document illustrates the complete flow of a job submission through the CLI client, detailing each system component, message, RPC call, and port involved.

## Overview Diagram

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CLI       │     │   Client     │     │Coordinator  │     │  Blockchain │     │   Miner     │     │   Ollama    │
│  Wrapper    │────▶│   Python     │────▶│   Service   │────▶│    Node     │────▶│  Daemon     │────▶│   Server    │
│(aitbc-cli.sh)│     │  (client.py) │     │  (port 18000)│     │ (RPC:26657) │     │ (port 18001)│     │ (port 11434)│
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

## Detailed Flow Sequence

### 1. CLI Wrapper Execution

**User Command:**
```bash
./scripts/aitbc-cli.sh submit inference --prompt "What is machine learning?" --model llama3.2:latest
```

**Internal Process:**
1. Bash script (`aitbc-cli.sh`) parses arguments
2. Sets environment variables:
   - `AITBC_URL=http://127.0.0.1:18000`
   - `CLIENT_KEY=${CLIENT_API_KEY}`
3. Calls Python client: `python3 cli/client.py --url $AITBC_URL --api-key $CLIENT_KEY submit inference --prompt "..."`

### 2. Python Client Processing

**File:** `/cli/client.py`

**Steps:**
1. Parse command-line arguments
2. Prepare job submission payload:
   ```json
   {
     "type": "inference",
     "prompt": "What is machine learning?",
     "model": "llama3.2:latest",
     "client_key": "${CLIENT_API_KEY}",
     "timestamp": "2025-01-29T14:50:00Z"
   }
   ```

### 3. Coordinator API Call

**HTTP Request:**
```http
POST /v1/jobs
Host: 127.0.0.1:18000
Content-Type: application/json
X-Api-Key: ${CLIENT_API_KEY}

{
  "type": "inference",
  "prompt": "What is machine learning?",
  "model": "llama3.2:latest"
}
```

**Coordinator Service (Port 18000):**
1. Receives HTTP request
2. Validates API key and job parameters
3. Generates unique job ID: `job_123456`
4. Creates job record in database
5. Returns initial response:
   ```json
   {
     "job_id": "job_123456",
     "status": "pending",
     "submitted_at": "2025-01-29T14:50:01Z"
   }
   ```

### 4. Blockchain Transaction

**Coordinator → Blockchain Node (RPC Port 26657):**

1. Coordinator creates blockchain transaction:
   ```json
   {
     "type": "submit_job",
     "job_id": "job_123456",
     "client": "${CLIENT_API_KEY}",
     "payload_hash": "abc123...",
     "reward": "100aitbc"
   }
   ```

2. RPC Call to blockchain node:
   ```bash
   curl -X POST http://127.0.0.1:26657 \
     -d '{
       "jsonrpc": "2.0",
       "method": "broadcast_tx_sync",
       "params": {"tx": "base64_encoded_transaction"}
     }'
   ```

3. Blockchain validates and includes transaction in next block
4. Transaction hash returned: `0xdef456...`

### 5. Job Queue and Miner Assignment

**Coordinator Internal Processing:**
1. Job added to pending queue (Redis/Database)
2. Miner selection algorithm runs:
   - Check available miners
   - Select based on stake, reputation, capacity
3. Selected miner: `${MINER_API_KEY}`

**Coordinator → Miner Daemon (Port 18001):**
```http
POST /v1/jobs/assign
Host: 127.0.0.1:18001
Content-Type: application/json
X-Api-Key: ${ADMIN_API_KEY}

{
  "job_id": "job_123456",
  "job_data": {
    "type": "inference",
    "prompt": "What is machine learning?",
    "model": "llama3.2:latest"
  },
  "reward": "100aitbc"
}
```

### 6. Miner Processing

**Miner Daemon (Port 18001):**
1. Receives job assignment
2. Updates job status to `running`
3. Notifies coordinator:
   ```http
   POST /v1/jobs/job_123456/status
   {"status": "running", "started_at": "2025-01-29T14:50:05Z"}
   ```

### 7. Ollama Inference Request

**Miner → Ollama Server (Port 11434):**
```http
POST /api/generate
Host: 127.0.0.1:11434
Content-Type: application/json

{
  "model": "llama3.2:latest",
  "prompt": "What is machine learning?",
  "stream": false,
  "options": {
    "temperature": 0.7,
    "num_predict": 500
  }
}
```

**Ollama Processing:**
1. Loads model into GPU memory
2. Processes prompt through neural network
3. Generates response text
4. Returns result:
   ```json
   {
     "model": "llama3.2:latest",
     "response": "Machine learning is a subset of artificial intelligence...",
     "done": true,
     "total_duration": 12500000000,
     "prompt_eval_count": 15,
     "eval_count": 150
   }
   ```

### 8. Result Submission to Coordinator

**Miner → Coordinator (Port 18000):**
```http
POST /v1/jobs/job_123456/complete
Host: 127.0.0.1:18000
Content-Type: application/json
X-Miner-Key: ${MINER_API_KEY}

{
  "job_id": "job_123456",
  "result": "Machine learning is a subset of artificial intelligence...",
  "metrics": {
    "compute_time": 12.5,
    "tokens_generated": 150,
    "gpu_utilization": 0.85
  },
  "proof": {
    "hash": "hash_of_result",
    "signature": "miner_signature"
  }
}
```

### 9. Receipt Generation

**Coordinator Processing:**
1. Verifies miner's proof
2. Calculates payment: `12.5 seconds × 0.02 AITBC/second = 0.25 AITBC`
3. Creates receipt:
   ```json
   {
     "receipt_id": "receipt_789",
     "job_id": "job_123456",
     "client": "${CLIENT_API_KEY}",
     "miner": "${MINER_API_KEY}",
     "amount_paid": "0.25aitbc",
     "result_hash": "hash_of_result",
     "block_height": 12345,
     "timestamp": "2025-01-29T14:50:18Z"
   }
   ```

### 10. Blockchain Receipt Recording

**Coordinator → Blockchain (RPC Port 26657):**
```json
{
  "type": "record_receipt",
  "receipt": {
    "receipt_id": "receipt_789",
    "job_id": "job_123456",
    "payment": "0.25aitbc"
  }
}
```

### 11. Client Polling for Result

**CLI Client Status Check:**
```bash
./scripts/aitbc-cli.sh status job_123456
```

**HTTP Request:**
```http
GET /v1/jobs/job_123456
Host: 127.0.0.1:18000
X-Api-Key: ${CLIENT_API_KEY}
```

**Response:**
```json
{
  "job_id": "job_123456",
  "status": "completed",
  "result": "Machine learning is a subset of artificial intelligence...",
  "receipt_id": "receipt_789",
  "completed_at": "2025-01-29T14:50:18Z"
}
```

### 12. Final Output to User

**CLI displays:**
```
Job ID: job_123456
Status: completed
Result: Machine learning is a subset of artificial intelligence...
Receipt: receipt_789
Completed in: 17 seconds
Cost: 0.25 AITBC
```

## System Components Summary

| Component | Port | Protocol | Responsibility |
|-----------|------|----------|----------------|
| CLI Wrapper | N/A | Bash | User interface, argument parsing |
| Client Python | N/A | Python | HTTP client, job formatting |
| Coordinator | 18000 | HTTP/REST | Job management, API gateway |
| Blockchain Node | 26657 | JSON-RPC | Transaction processing, consensus |
| Miner Daemon | 18001 | HTTP/REST | Job execution, GPU management |
| Ollama Server | 11434 | HTTP/REST | AI model inference |

## Message Flow Timeline

```
0s: User submits CLI command
└─> 0.1s: Python client called
   └─> 0.2s: HTTP POST to Coordinator (port 18000)
      └─> 0.3s: Coordinator validates and creates job
         └─> 0.4s: RPC to Blockchain (port 26657)
            └─> 0.5s: Transaction in mempool
               └─> 1.0s: Job queued for miner
                  └─> 2.0s: Miner assigned (port 18001)
                     └─> 2.1s: Miner accepts job
                        └─> 2.2s: Ollama request (port 11434)
                           └─> 14.7s: Inference complete (12.5s processing)
                              └─> 14.8s: Result to Coordinator
                                 └─> 15.0s: Receipt generated
                                    └─> 15.1s: Receipt on Blockchain
                                       └─> 17.0s: Client polls and gets result
```

## Error Handling Paths

1. **Invalid Prompt**:
   - Coordinator returns 400 error
   - CLI displays error message

2. **Miner Unavailable**:
   - Job stays in queue
   - Timeout after 60 seconds
   - Job marked as failed

3. **Ollama Error**:
   - Miner reports failure to Coordinator
   - Job marked as failed
   - No payment deducted

4. **Network Issues**:
   - Client retries with exponential backoff
   - Maximum 3 retries before giving up

## Security Considerations

1. **API Keys**: Each request authenticated with X-Api-Key header
2. **Proof of Work**: Miner provides cryptographic proof of computation
3. **Payment Escrow**: Tokens held in smart contract until completion
4. **Rate Limiting**: Coordinator limits requests per client

## Monitoring Points

- Coordinator logs all API calls to `/var/log/aitbc/coordinator.log`
- Miner logs GPU utilization to `/var/log/aitbc/miner.log`
- Blockchain logs all transactions to `/var/log/aitbc/node.log`
- Prometheus metrics available at `http://localhost:9090/metrics`
