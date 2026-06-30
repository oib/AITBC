# Nemotron Cloud Offer - Discovery

**Last Updated**: 2026-06-30
**Version**: 1.0

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

## Offer Details

The Nemotron-3-Super cloud offer provides:
- **Model**: NVIDIA Nemotron 3 Super
- **Hosting**: Cloud-based (no GPU required on your end)
- **Pricing**: 0.01 AIT per 1,000 tokens
- **Access**: Via Ollama cloud proxy through aitbc3
- **Status**: Active and operational

## Related Topics

- [Quick Start](./nemotron-quick-start.md) - Get started with Nemotron
- [Run Inference](./nemotron-inference.md) - Execute inference with payment
- [Monitor Usage](./nemotron-monitoring.md) - Track costs and performance
