# Nemotron Cloud Offer - Inference

**Last Updated**: 2026-06-30
**Version**: 1.0

## Step 2: Run Inference with Payment

### Method A: Direct API (Cross-Node — **Fully Working**)

```bash
# 1. Create escrow contract for the job
JOB_ID=job-quantum-demo
aitbc market escrow create \
  --job-id $JOB_ID \
  --buyer <buyer-wallet-address> \
  --provider <provider-wallet-address>

echo "Escrow created for job: $JOB_ID"

# 2. Send prompt to Ollama endpoint (fully operational)
RESPONSE=$(curl -s -X POST https://shop.example.net/ollama/api/generate \
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

# 3. Release the escrowed payment to the provider
aitbc market escrow release --job-id $JOB_ID
```

### Method B: Agent Messaging Workflow (**Fully Working**)

This approach works well when you want the shop agent to handle the inference and respond via the messaging system.

```bash
# 1. Discover offer (working)
curl -s https://shop.example.net/api/v1/marketplace/offer | jq '.offers[0].plugin_id'

# 2. Send message to shop agent (Agent Coordinator, port 8107; via nginx /agent/)
curl -X POST https://shop.example.net/agent/api/v1/agent/messages/send \
  -H "Content-Type: application/json" \
  -d '{"sender":"owl-hub","recipient":"owl-node2","content":"Customer inquiry: Explain quantum computing","message_type":"direct"}'

# 3. Shop agent on the shop node receives and processes
# Shop polls: curl https://shop.example.net/agent/api/v1/agent/messages/owl-node2
# Shop calls Ollama locally: curl http://localhost:11434/api/generate ...
# Shop sends response back to customer

# 4. Customer polls for response
curl -s https://shop.example.net/agent/api/v1/agent/messages/owl-hub
```

### Method C: CLI (Limited Functionality)

```bash
# Note: aitbc market run queries blockchain transactions, not marketplace service
# This won't find the cloud offer unless it's also registered on-chain
aitbc market run --offer-id-or-plugin-id sw_offer_20260605110316_a343d309 --prompt "Explain quantum computing"

# Alternative: Use marketplace service directly
curl -s http://shop.example.net:8102/v1/marketplace/offer/ollama-nemotron-3-super-cloud | jq '.'
```

## Step 3: Monitor Usage and Costs

### Check Transaction Status

```bash
# Monitor escrow status
aitbc market escrow status --job-id $JOB_ID

# Check wallet balance
aitbc wallet balance

# View transaction history
aitbc wallet transactions --limit 20
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
