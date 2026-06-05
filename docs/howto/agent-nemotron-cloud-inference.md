# Howto: Agent Guide to Using Nemotron-3-Super Cloud Offer

## Overview

This guide shows how an agent can discover, use, and pay for the NVIDIA Nemotron-3-Super cloud model hosted on aitbc3. The offer provides access to the model through Ollama's cloud proxy with metered billing.

## Prerequisites

- AITBC CLI installed and configured
- Wallet with sufficient AIT tokens
- Network access to aitbc3.aitbc.bubuit.net

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
# Get all offers
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer | jq '.offers[]'

# Get specific offer details
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.'
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

### Method A: CLI (Recommended)
```bash
# Run inference with automatic escrow payment
aitbc market run sw_offer_20260605110316_a343d309 "Explain quantum computing in simple terms"

# With custom parameters
aitbc market run sw_offer_20260605110316_a343d309 "Write a Python function for fibonacci" \
  --max-tokens 500 \
  --temperature 0.7
```

### Method B: Direct API (Advanced)
```bash
# 1. Create escrow contract
ESCROW_TX=$(aitbc wallet escrow-create \
  --offer-id sw_offer_20260605110316_a343d309 \
  --amount 0.1 \
  --description "Quantum computing explanation")

echo "Escrow TX: $ESCROW_TX"

# 2. Send prompt to Ollama endpoint
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
        """Direct API call (requires manual escrow management)"""
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

1. **Insufficient Balance**
   ```bash
   aitbc wallet balance
   # Add funds if needed
   aitbc wallet deposit <amount>
   ```

2. **Offer Not Available**
   ```bash
   # Check offer status
   curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.status'
   ```

3. **Network Issues**
   ```bash
   # Test connectivity
   curl -s https://aitbc3.aitbc.bubuit.net/ollama/api/tags
   ```

4. **Escrow Issues**
   ```bash
   # Check escrow status
   aitbc wallet escrow-status <tx_hash>
   # Release stuck escrow
   aitbc wallet escrow-release --escrow-tx <tx_hash> --force
   ```

### Error Messages

- **"Offer not found"**: Check offer ID and marketplace status
- **"Insufficient funds"**: Add AIT tokens to wallet
- **"Service unavailable"**: Check aitbc3 service status
- **"Escrow failed"**: Verify wallet configuration and network

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
