# Howto: Agent Guide to Using Nemotron-3-Super Cloud Offer

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

**Current Status** (as of 2026-06-05):
- ✅ Marketplace discovery via API Gateway
- ✅ Agent messaging via Coordinator API (routed through API Gateway at `/v1/coordinator`)
- ✅ Ollama inference — fully operational (nginx proxy fixed)
- ✅ **All core services operational after comprehensive fixes**
- ✅ Coordinator API: Running on port 8203 with Hermes endpoints
- ✅ AgentDaemon: Successfully polling every 10 seconds
- ✅ Marketplace Service: Database schema updated and healthy

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

## Step 4: Agent Integration Examples

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
   # Check for import errors - fixed deprecated MarketplaceBidRequest imports
   
   # If AgentDaemon has connection errors:
   systemctl status aitbc-agent-daemon.service
   # Check if Coordinator API is ready before AgentDaemon starts
   
   # If Marketplace Service has database errors:
   systemctl status aitbc-marketplace.service
   # Check for missing database columns - fixed avg_rating schema
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

## Best Practices

1. **Cost Management**: Monitor token usage to control costs
2. **Error Handling**: Implement retry logic for network issues
3. **Caching**: Cache responses for repeated queries
4. **Rate Limiting**: Respect service rate limits
5. **Security**: Validate prompts and sanitize responses

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
