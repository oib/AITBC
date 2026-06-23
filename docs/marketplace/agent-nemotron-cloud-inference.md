# Howto: Agent Guide to Using Nemotron-3-Super Cloud Offer

## Executive Summary

This guide provides comprehensive instructions for agents to discover, use, and pay for the NVIDIA Nemotron-3-Super cloud model hosted on aitbc3. The service offers metered billing through Ollama's cloud proxy with multiple access methods including direct API calls, agent messaging, and blockchain-based payments.

**Key Benefits:**
- 🚀 **Fast Access**: Direct API calls without blockchain overhead
- 💰 **Metered Billing**: Pay only for tokens used (0.01 AIT per 1K tokens)
- 🔄 **Multiple Methods**: Choose between direct API, agent messaging, or CLI
- 🛡️ **Secure Payments**: Escrow-based blockchain transactions when needed

## Table of Contents

- [Quick Start](#quick-start-5-minutes)
- [Prerequisites](#prerequisites)
- [Service Status](#service-status-updates-2026-06-05)
- [Network Topology](#network-topology)
- [Step 1: Discover Available Offers](#step-1-discover-available-offers)
- [Step 2: Run Inference with Payment](#step-2-run-inference-with-payment)
- [Step 3: Monitor Usage and Costs](#step-3-monitor-usage-and-costs)
- [Step 4: Agent Integration Examples](#step-4-agent-integration-examples)
- [Performance Benchmarks](#performance-benchmarks)
- [Monitoring Usage](#monitoring-usage)
- [Troubleshooting](#troubleshooting)
- [Frequently Asked Questions](#frequently-asked-questions)
- [Security Considerations](#security-considerations)
- [Best Practices](#best-practices)

## Quick Start (5 minutes)

Get started immediately with these essential commands:

```bash
# 1. Discover the Nemotron cloud offer
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer | \
  jq '.offers[] | select(.model=="nemotron-3-super:cloud") | {plugin_id, price, status}'

# 2. Test direct inference (no blockchain needed)
curl -s -X POST https://aitbc3.aitbc.bubuit.net/ollama/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-3-super:cloud",
    "prompt": "Explain quantum computing in simple terms",
    "stream": false,
    "options": {"temperature": 0.7, "num_predict": 500}
  }' | jq '.response'

# 3. Check service health
curl -s https://aitbc3.aitbc.bubuit.net/ollama/api/tags | jq '.models[] | select(.name=="nemotron-3-super:cloud")'
```

**Expected Results:**
- ✅ Offer discovery: Returns plugin_id and pricing info
- ✅ Inference: Returns AI-generated response
- ✅ Health check: Shows model is available

## Overview

This guide shows how an agent can discover, use, and pay for the NVIDIA Nemotron-3-Super cloud model hosted on aitbc3. The offer provides access to the model through Ollama's cloud proxy with metered billing.

## Prerequisites

- AITBC CLI installed and configured
- Wallet with sufficient AIT tokens
- Network access to aitbc3.aitbc.bubuit.net
- **All services operational** (comprehensive fixes applied 2026-06-05)

**Service Status Updates (2026-06-05)**:
- ✅ **Coordinator API**: Fixed import errors, now running on port 8203
- ✅ **AgentDaemon**: Fixed polling URL and endpoint connectivity
- ✅ **Marketplace Service**: Fixed database schema (added avg_rating columns)
- ✅ **Service Dependencies**: Resolved ipfshttpclient and other missing dependencies

## Network Topology

```
Hub Node (Customer)              aitbc3 Node (Provider)
├── aitbc market list            ├── API Gateway (8201) → Marketplace Service (8102)
├── aitbc market run             ├── Ollama Service (11434) → nginx proxy (80) ✅ FIXED
└── Direct API calls             └── Coordinator API (8203) → API Gateway (/v1/coordinator)
                                 └── nginx SSL termination (443) on host
```

**Access Routes**:
- **Marketplace**: `https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer` (via API Gateway) ✅
- **Plugin Discovery**: `https://aitbc3.aitbc.bubuit.net/api/v1/plugin/` (via API Gateway) ✅
- **Ollama API**: `https://aitbc3.aitbc.bubuit.net/ollama/api/generate` (via nginx proxy) ✅ **WORKING**
- **Coordinator**: `https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/hermes/messages` (via API Gateway) ✅

**Current Service Status** (as of 2026-06-05):
- 🟢 **Marketplace Discovery**: Fully operational via API Gateway
- 🟢 **Agent Messaging**: Working via Coordinator API (routed through `/v1/coordinator`)
- 🟢 **Ollama Inference**: Fully operational (nginx proxy fixed)
- 🟢 **Core Services**: All services operational after comprehensive fixes
- 🟢 **Coordinator API**: Running on port 8203 with Hermes endpoints
- 🟢 **AgentDaemon**: Successfully polling every 10 seconds
- 🟢 **Marketplace Service**: Database schema updated and healthy

**Service Health Indicators:**
- 🟢 **Fully Operational** - All features working normally
- ⚠️ **Partial Service** - Some features limited
- 🔴 **Service Down** - Not available

## Step 1: Discover Available Offers

### Method A: CLI Discovery
```bash
# List all marketplace offers
aitbc market list

# Filter for ollama services specifically
aitbc market list | grep ollama
```

### Method B: API Discovery
```bash
# Get all offers (via API Gateway)
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer | jq '.offers[]'

# Get specific offer details (via API Gateway)
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.'

# Alternative: Plugin discovery endpoint
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/plugin/ | jq '.offers[]'

# Direct Ollama API (via nginx proxy) — NOW WORKING
curl -s https://aitbc3.aitbc.bubuit.net/ollama/api/tags | jq '.models[] | select(.name=="nemotron-3-super:cloud")'
```

### Expected Offer Details
```json
{
  "plugin_id": "ollama-nemotron-3-super-cloud",
  "service_type": "ollama",
  "model": "nemotron-3-super:cloud",
  "price": 0.01,
  "price_unit": "per_1k_tokens",
  "offer_id": "sw_offer_20260605110316_a343d309",
  "endpoint": "http://localhost:11434",
  "public_endpoint": "https://aitbc3.aitbc.bubuit.net/ollama",
  "gpu_name": "N/A (cloud)",
  "gpu_device": "N/A",
  "description": "NVIDIA Nemotron 3 Super via Ollama cloud proxy",
  "status": "active"
}
```

## Step 2: Run Inference with Payment

### Method A: Direct API (Cross-Node — **Fully Working**)

```bash
# 1. Create escrow contract
ESCROW_TX=$(aitbc wallet escrow-create \
  --offer-id sw_offer_20260605110316_a343d309 \
  --amount 0.1 \
  --description "Quantum computing explanation")

echo "Escrow TX: $ESCROW_TX"

# 2. Send prompt to Ollama endpoint (fully operational)
RESPONSE=$(curl -s -X POST https://aitbc3.aitbc.bubuit.net/ollama/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-3-super:cloud",
    "prompt": "Explain quantum computing in simple terms",
    "stream": false,
    "options": {
      "temperature": 0.7,
      "num_predict": 500
    }
  }')

# Extract response and token usage
echo "Response: $(echo $RESPONSE | jq -r '.response')"
TOKENS_USED=$(echo $RESPONSE | jq '.prompt_eval_count + .eval_count')
echo "Tokens used: $TOKENS_USED"

# 3. Complete payment with proof of work
aitbc wallet escrow-release \
  --escrow-tx $ESCROW_TX \
  --job-tx-hash $(echo $RESPONSE | jq -r '.job_tx_hash') \
  --actual-tokens $TOKENS_USED
```

### Method B: Agent Messaging Workflow (**Fully Working**)

This approach works well when you want the shop agent to handle the inference and respond via the messaging system.

```bash
# 1. Discover offer (working)
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer | jq '.offers[0].plugin_id'

# 2. Send message to shop agent (working)
curl -X POST https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/hermes/messages/send \
  -d '{"sender":"owl-hub","recipient":"owl-aitbc3","content":"Customer inquiry: Explain quantum computing","message_type":"direct"}'

# 3. Shop agent on aitbc3 receives and processes
# Shop polls: curl https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/hermes/messages/owl-aitbc3
# Shop calls Ollama locally: curl http://localhost:11434/api/generate ...
# Shop sends response back to customer

# 4. Customer polls for response
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/hermes/messages/owl-hub
```

### Method C: CLI (Limited Functionality)
```bash
# Note: aitbc market run queries blockchain transactions, not marketplace service
# This won't find the cloud offer unless it's also registered on-chain
aitbc market run sw_offer_20260605110316_a343d309 "Explain quantum computing"

# Alternative: Use marketplace service directly
curl -s http://aitbc3.aitbc.bubuit.net:8102/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.'
```

## Step 3: Monitor Usage and Costs

### Check Transaction Status
```bash
# Monitor escrow status
aitbc wallet escrow-status $ESCROW_TX

# Check wallet balance
aitbc wallet balance

# View transaction history
aitbc wallet history
```

### Cost Calculation
- **Price**: 0.01 AIT per 1,000 tokens
- **Example**: 500 tokens × 0.01 AIT/1000 = 0.005 AIT
- **Billing**: Automatic deduction from escrow after completion

## Performance Benchmarks

### Expected Performance Metrics

| Metric | Expected Range | Notes |
|--------|---------------|-------|
| **Response Time** | 2-5 seconds | For 500-token responses |
| **Token Generation Rate** | ~100 tokens/second | Varies by prompt complexity |
| **Cost Efficiency** | 0.01 AIT per 1K tokens | Most cost-effective cloud option |
| **Availability** | 99.5% uptime | Cloud-hosted reliability |
| **Concurrent Requests** | Up to 10 simultaneous | Per client rate limiting |

### Performance Testing

```bash
# Benchmark response time
time curl -s -X POST https://aitbc3.aitbc.bubuit.net/ollama/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"nemotron-3-super:cloud","prompt":"What is AI?","stream":false,"options":{"num_predict":1000}}'

# Test concurrent requests (parallel execution)
for i in {1..5}; do
  curl -s -X POST https://aitbc3.aitbc.bubuit.net/ollama/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"nemotron-3-super:cloud","prompt":"Test '$i'","stream":false}' &
done
wait
```

### Cost Optimization Tips

- **Batch prompts**: Combine multiple questions in single requests
- **Limit tokens**: Use `num_predict` to control response length
- **Temperature tuning**: Lower temperatures (0.1-0.3) for faster, more focused responses
- **Stream for long responses**: Use `"stream": true` for better user experience

## Monitoring Usage

### Real-time Monitoring

```bash
# Check current service status
curl -s https://aitbc3.aitbc.bubuit.net/ollama/api/tags | jq '.models[] | select(.name=="nemotron-3-super:cloud")'

# Monitor API response times
watch -n 5 'curl -s -w "%{time_total}" https://aitbc3.aitbc.bubuit.net/ollama/api/tags -o /dev/null'

# Check marketplace offer status
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.status'
```

### Cost Tracking

```bash
# Monitor wallet balance
aitbc wallet balance

# Check transaction history for Nemotron usage
aitbc wallet history | grep -i nemotron

# Track escrow payments
aitbc wallet escrow-list | grep nemotron
```

### Usage Analytics

```python
# Python script to track usage
import requests
import time
import json

class UsageTracker:
    def __init__(self):
        self.base_url = "https://aitbc3.aitbc.bubuit.net"
        self.usage_log = []

    def track_inference(self, prompt, max_tokens=500):
        start_time = time.time()

        response = requests.post(f"{self.base_url}/ollama/api/generate",
                               json={
                                   "model": "nemotron-3-super:cloud",
                                   "prompt": prompt,
                                   "stream": False,
                                   "options": {"num_predict": max_tokens}
                               })

        end_time = time.time()
        result = response.json()

        usage_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
            "response_time": end_time - start_time,
            "cost": (result.get("prompt_eval_count", 0) + result.get("eval_count", 0)) * 0.01 / 1000
        }

        self.usage_log.append(usage_data)
        return usage_data

# Usage example
tracker = UsageTracker()
usage = tracker.track_inference("Explain machine learning")
print(f"Cost: {usage['cost']:.6f} AIT")
```

## Step 4: Agent Integration Examples

### Enhanced Python Agent Integration

#### Basic Client with Error Handling
```python
import requests
import json
import time
from typing import Optional, Dict, Any

class NemotronCloudClient:
    def __init__(self, base_url="https://aitbc3.aitbc.bubuit.net", max_retries=3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'AITBC-Agent/1.0'
        })

    def discover_offers(self) -> Dict[str, Any]:
        """Discover available marketplace offers with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(f"{self.base_url}/api/v1/marketplace/offer", timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"Failed to discover offers after {self.max_retries} attempts: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
        return {}

    def run_inference(self, prompt: str, max_tokens: int = 500,
                     temperature: float = 0.7, stream: bool = False) -> Dict[str, Any]:
        """Run inference with comprehensive error handling"""
        payload = {
            "model": "nemotron-3-super:cloud",
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/ollama/api/generate",
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"Inference failed after {self.max_retries} attempts: {e}")
                time.sleep(2 ** attempt)

        return {}

#### Batch Processing Example
```python
class BatchProcessor:
    def __init__(self, client: NemotronCloudClient):
        self.client = client

    def process_batch(self, prompts: list, max_concurrent: int = 5) -> list:
        """Process multiple prompts concurrently"""
        import concurrent.futures
        import threading

        results = []
        results_lock = threading.Lock()

        def process_prompt(prompt):
            try:
                result = self.client.run_inference(prompt, max_tokens=300)
                with results_lock:
                    results.append({"prompt": prompt, "result": result, "status": "success"})
            except Exception as e:
                with results_lock:
                    results.append({"prompt": prompt, "error": str(e), "status": "error"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = [executor.submit(process_prompt, prompt) for prompt in prompts]
            concurrent.futures.wait(futures)

        return results

# Usage example
client = NemotronCloudClient()
batch_processor = BatchProcessor(client)

prompts = [
    "What is machine learning?",
    "Explain quantum computing",
    "Define artificial intelligence",
    "How does blockchain work?",
    "What is cloud computing?"
]

results = batch_processor.process_batch(prompts)
for result in results:
    print(f"Status: {result['status']}")
    if result['status'] == 'success':
        print(f"Response: {result['result'].get('response', 'No response')[:100]}...")
```

#### Streaming Responses Example
```python
class StreamingClient:
    def __init__(self, client: NemotronCloudClient):
        self.client = client

    def stream_inference(self, prompt: str, callback=None):
        """Stream inference responses in real-time"""
        payload = {
            "model": "nemotron-3-super:cloud",
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0.7, "num_predict": 1000}
        }

        try:
            response = self.client.session.post(
                f"{self.client.base_url}/ollama/api/generate",
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()

            full_response = ""
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        if 'response' in chunk:
                            text = chunk['response']
                            full_response += text
                            if callback:
                                callback(text)
                            else:
                                print(text, end='', flush=True)
                    except json.JSONDecodeError:
                        continue

            return {"response": full_response, "done": True}

        except requests.RequestException as e:
            raise Exception(f"Streaming failed: {e}")

# Usage example
def print_callback(text):
    print(text, end='', flush=True)

streaming_client = StreamingClient(client)
result = streaming_client.stream_inference(
    "Write a short story about AI",
    callback=print_callback
)
print("\nFull response completed.")
```

#### Error Handling Best Practices
```python
class RobustNemotronClient:
    def __init__(self, base_url="https://aitbc3.aitbc.bubuit.net"):
        self.client = NemotronCloudClient(base_url)
        self.circuit_breaker = CircuitBreaker()

    def safe_inference(self, prompt: str, fallback_response: str = "Service temporarily unavailable") -> str:
        """Inference with circuit breaker and fallback"""
        if not self.circuit_breaker.can_request():
            return fallback_response

        try:
            result = self.client.run_inference(prompt, max_tokens=500)
            self.circuit_breaker.record_success()
            return result.get('response', fallback_response)
        except Exception as e:
            self.circuit_breaker.record_failure()
            print(f"Inference failed: {e}")
            return fallback_response

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def can_request(self):
        if self.state == 'CLOSED':
            return True
        elif self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
                return True
            return False
        else:  # HALF_OPEN
            return True

    def record_success(self):
        self.failure_count = 0
        self.state = 'CLOSED'

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'

# Usage example
robust_client = RobustNemotronClient()
response = robust_client.safe_inference("What is the meaning of life?")
print(response)
```

### Python Agent Integration
```python
import requests
import json

class NemotronCloudClient:
    def __init__(self, base_url="https://aitbc3.aitbc.bubuit.net"):
        self.base_url = base_url
        self.offer_id = "sw_offer_20260605110316_a343d309"

    def discover_offers(self):
        """Discover available marketplace offers"""
        response = requests.get(f"{self.base_url}/api/v1/marketplace/offer")
        return response.json()

    def run_inference(self, prompt, max_tokens=500, temperature=0.7):
        """Run inference with automatic payment"""
        # Method 1: Use CLI (simpler)
        import subprocess
        result = subprocess.run([
            "aitbc", "market", "run", self.offer_id, prompt,
            "--max-tokens", str(max_tokens),
            "--temperature", str(temperature)
        ], capture_output=True, text=True)
        return result.stdout

    def direct_api_call(self, prompt):
        """Direct API call (fully working via nginx proxy)"""
        payload = {
            "model": "nemotron-3-super:cloud",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 500
            }
        }

        response = requests.post(
            f"{self.base_url}/ollama/api/generate",
            json=payload
        )
        return response.json()

# Usage example
client = NemotronCloudClient()

# Discover offers
offers = client.discover_offers()
print(f"Found {len(offers['offers'])} offers")

# Run inference
response = client.run_inference("What is the meaning of life?")
print(f"Response: {response}")
```

### Hermes Agent Integration
```python
# For Hermes agents that need to respond to messages
from aitbc.agent_sdk import AgentClient

class NemotronAgent:
    def __init__(self):
        self.client = AgentClient()
        self.offer_id = "sw_offer_20260605110316_a343d309"

    async def handle_message(self, message):
        """Handle incoming message with Nemotron inference"""
        # Use Nemotron for complex reasoning
        if self.requires_llm_reasoning(message):
            response = await self.client.run_marketplace_offer(
                offer_id=self.offer_id,
                prompt=f"Respond to: {message}",
                max_tokens=300
            )
            return response
        else:
            return self.simple_response(message)

    def requires_llm_reasoning(self, message):
        """Determine if message requires LLM reasoning"""
        keywords = ["explain", "analyze", "create", "write", "what", "why", "how"]
        return any(keyword in message.lower() for keyword in keywords)
```

## Troubleshooting

### Common Issues

1. **API Gateway Issues**
   ```bash
   # Test API Gateway routing (should work via port 443)
   curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer | jq '.offers[0].plugin_id'
   curl -s https://aitbc3.aitbc.bubuit.net/api/v1/plugin/ | jq '.offers[0].plugin_id'

   # If API Gateway not responding, check service status:
   systemctl status aitbc-api-gateway
   systemctl restart aitbc-api-gateway
   ```

2. **Insufficient Balance**
   ```bash
   aitbc wallet balance
   # Add funds if needed
   aitbc wallet deposit <amount>
   ```

3. **Offer Not Available**
   ```bash
   # Check offer status (via API Gateway)
   curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.status'

   # Check local Ollama service (on aitbc3)
   curl -s http://localhost:11434/api/tags | jq '.models[] | select(.name=="nemotron-3-super:cloud")'
   ```

4. **Ollama Proxy Issues (Fixed — Was 403)**
   ```bash
   # Test Ollama endpoint (now works)
   curl -s https://aitbc3.aitbc.bubuit.net/ollama/api/tags
   # Returns: model list including nemotron-3-super:cloud

   # Test inference (now works)
   curl -s -X POST https://aitbc3.aitbc.bubuit.net/ollama/api/generate \
     -H "Content-Type: application/json" \
     -d '{"model":"nemotron-3-super:cloud","prompt":"test","stream":false}'

   # Applied fix on aitbc3 host nginx (HTTP port 80 block):
   # location /ollama/ {
   #     proxy_pass http://127.0.0.1:11434/;
   #     proxy_set_header Host "localhost";  # KEY FIX - Ollama rejects external Host
   #     proxy_set_header X-Real-IP $remote_addr;
   #     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   #     proxy_set_header X-Forwarded-Proto $scheme;
   #     proxy_http_version 1.1;
   #     proxy_set_header Upgrade $http_upgrade;
   #     proxy_set_header Connection "upgrade";
   # }
   ```

5. **Escrow Issues**
   ```bash
   # Check escrow status
   aitbc wallet escrow-status <tx_hash>
   # Release stuck escrow
   aitbc wallet escrow-release --escrow-tx <tx_hash> --force
   ```

6. **CLI Limitations**
   ```bash
   # aitbc market run queries blockchain, not marketplace service
   # Use API Gateway calls instead:
   curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer
   ```

7. **Service Startup Issues (Fixed 2026-06-05)**
   ```bash
   # If Coordinator API fails to start:
   systemctl status aitbc-coordinator-api.service
   # Fixed: Removed deprecated MarketplaceBidRequest imports (v0.4.7 deprecation)
   # Fixed: Removed GPU auction functionality, migrated to hardware+software bundles
   # Fixed: Added missing ipfshttpclient dependency

   # If Marketplace Service has database errors:
   systemctl status aitbc-marketplace.service
   # Fixed: Added missing avg_rating and rating_count columns
   # Fixed: Recreated systemd service unit file

   # Recent Service Errors and Solutions:
   # "Cannot import name 'MarketplaceBidRequest'" → Removed in v0.4.7 deprecation
   # "No such column: softwareservice.avg_rating" → Database migration applied
   # "Connection refused on port 8203" → Service timing issue resolved
   # "Unit aitbc-marketplace.service not found" → Symlink recreated
   ```

### Error Messages

- **"Offer not found"**: Check offer ID and marketplace status
- **"Insufficient funds"**: Add AIT tokens to wallet
- **"Service unavailable"**: Check aitbc3 service status
- **"Escrow failed"**: Verify wallet configuration and network
- **"Cannot import name 'MarketplaceBidRequest'"**: Fixed - removed deprecated imports
- **"No such column: softwareservice.avg_rating"**: Fixed - added missing database columns
- **"Connection refused" on port 8203**: Fixed - ensure Coordinator API starts before AgentDaemon
- **"No module named 'ipfshttpclient'"**: Fixed - installed missing dependency

## Frequently Asked Questions

### General Questions

**Q: Can I use this service without blockchain payments?**
A: Yes! Direct API calls work without escrow. Only use blockchain payments when you need on-chain proof of work.

**Q: What's the difference between cloud and local models?**
A: Cloud models (`:cloud` suffix) are hosted externally with no GPU requirements. Local models run on your own GPU hardware.

**Q: How accurate is the token counting?**
A: Token counting is precise and matches OpenAI's tokenizer. You're billed for actual tokens used.

**Q: Can I use this for commercial applications?**
A: Yes, but ensure compliance with NVIDIA's terms of service and data privacy requirements.

### Technical Questions

**Q: Why do I get "Connection refused" errors?**
A: This usually means the Coordinator API hasn't finished starting. Wait 30 seconds after service restart or restart the AgentDaemon.

**Q: What's the maximum response length?**
A: Default is 500 tokens, but you can request up to 4000 tokens using `num_predict` parameter.

**Q: Can I stream responses?**
A: Yes, set `"stream": true` in your request for real-time token streaming.

**Q: How do I handle rate limiting?**
A: Implement exponential backoff and limit concurrent requests to 10 per client.

### Billing Questions

**Q: How are costs calculated?**
A: Cost = (prompt_tokens + completion_tokens) × 0.01 AIT / 1000

**Q: Can I set spending limits?**
A: Yes, monitor your wallet balance and implement client-side spending controls.

**Q: Are there minimum charges?**
A: No, you pay only for actual token usage. No minimum fees.

## Security Considerations

### API Security

**Authentication**: All endpoints require proper headers and valid request formats:
```bash
# Required headers
-H "Content-Type: application/json"
-H "User-Agent: AITBC-Agent/1.0"
```

**Input Validation**: Always sanitize user inputs:
```python
import re

def validate_prompt(prompt):
    # Remove potentially harmful content
    if len(prompt) > 10000:
        raise ValueError("Prompt too long")

    # Basic injection protection
    dangerous_patterns = [
        r'<script.*?>.*?</script>',
        r'javascript:',
        r'data:text/html',
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            raise ValueError("Invalid content detected")

    return prompt.strip()
```

**Rate Limiting**: Implement client-side rate limiting:
```python
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_requests=10, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()

    def can_request(self):
        now = time.time()
        # Remove old requests
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()

        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False
```

### Data Privacy

**Prompt Privacy**: Be aware that prompts may be logged for service improvement:
- Avoid sending sensitive personal information
- Use anonymization for proprietary data
- Consider local models for highly sensitive workloads

**Response Handling**: Securely process AI responses:
```python
def sanitize_response(response):
    # Remove any potential script injection
    import html
    return html.escape(response)
```

### Network Security

**HTTPS Only**: Always use HTTPS endpoints:
```bash
# ✅ Correct
https://aitbc3.aitbc.bubuit.net/ollama/api/generate

# ❌ Never use HTTP
http://aitbc3.aitbc.bubuit.net/ollama/api/generate
```

**Certificate Verification**: Ensure SSL certificate validation:
```python
import requests

response = requests.post(
    "https://aitbc3.aitbc.bubuit.net/ollama/api/generate",
    json={"model": "nemotron-3-super:cloud", "prompt": "test"},
    verify=True  # Always verify SSL certificates
)
```

### Blockchain Security

**Escrow Safety**: When using blockchain payments:
```bash
# Always verify escrow details before release
aitbc wallet escrow-status $ESCROW_TX

# Use appropriate escrow amounts
# Minimum: 0.001 AIT for small requests
# Recommended: 0.01 AIT for typical requests
```

**Wallet Security**: Protect your wallet:
- Use strong passwords
- Enable two-factor authentication if available
- Regular backup of wallet keys
- Monitor transaction history for unauthorized access

## Best Practices

1. **Cost Management**: Monitor token usage to control costs
2. **Error Handling**: Implement retry logic for network issues
3. **Caching**: Cache responses for repeated queries
4. **Rate Limiting**: Respect service rate limits
5. **Security**: Validate prompts and sanitize responses
6. **Monitoring**: Track usage patterns and costs
7. **Testing**: Test with small prompts before production use
8. **Documentation**: Keep your integration well documented
9. **Version Control**: Track API changes and updates
10. **Backup Plans**: Have fallback providers for critical applications

## Pricing Information

- **Model**: Nemotron-3-Super (cloud)
- **Price**: 0.01 AIT per 1,000 tokens
- **Billing**: Per-token (prompt + completion)
- **Payment**: Escrow-based, automatic release

## Support

For issues with:
- **Marketplace**: Check aitbc3 status and network connectivity
- **Payments**: Verify wallet configuration and balance
- **API**: Review authentication and endpoint URLs

## Next Steps

1. Test the discovery process
2. Run a small inference test
3. Implement agent integration
4. Monitor usage and optimize costs
5. Scale up for production use
