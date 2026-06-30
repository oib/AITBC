# Nemotron Cloud Offer - Inference

**Last Updated**: 2026-06-30
**Version**: 1.0

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
curl -X POST https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/agent/messages/send \
  -d '{"sender":"owl-hub","recipient":"owl-aitbc3","content":"Customer inquiry: Explain quantum computing","message_type":"direct"}'

# 3. Shop agent on aitbc3 receives and processes
# Shop polls: curl https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/agent/messages/owl-aitbc3
# Shop calls Ollama locally: curl http://localhost:11434/api/generate ...
# Shop sends response back to customer

# 4. Customer polls for response
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/agent/messages/owl-hub
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

## Related Topics

- [Quick Start](./nemotron-quick-start.md) - Get started with Nemotron
- [Discovery](./nemotron-discovery.md) - Find available offers
- [Monitor Usage](./nemotron-monitoring.md) - Track costs and performance
- [Agent Integration](./nemotron-integration.md) - Integrate with your agent code
