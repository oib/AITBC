# Client Documentation - AITBC

Use AITBC for AI/ML Workloads: Access secure, private, and verifiable AI/ML computation on the decentralized network

> ✅ **Now Available: CLI Wrapper Tool**
> 
> Submit jobs, check status, and verify receipts with our new bash CLI wrapper. Supporting 13+ Ollama models with real-time blockchain verification!

## Key Features

- **Privacy First** - Your data and models remain confidential with zero-knowledge proofs and secure enclaves
- **Verifiable Results** - Every computation is cryptographically verified on the blockchain for trust and transparency
- **Fast & Efficient** - Access thousands of GPUs worldwide with sub-second response times

## Getting Started

Start using AITBC in minutes with our simple client SDK or web interface.

### Quick Start Options

- **CLI Wrapper Tool**: ✅ NEW - Unified bash script for job management
- **Web Interface**: No installation required
- **Python SDK**: For AI/ML developers
- **JavaScript SDK**: For web applications
- **REST API**: For any platform

### CLI Wrapper Tool (Recommended)

#### Submit an Inference Job

Use the bash CLI wrapper for easy job submission:

```bash
# Submit job with CLI wrapper
./scripts/aitbc-cli.sh submit inference \
  --prompt "What is machine learning?" \
  --model llama3.2:latest

# Check job status
./scripts/aitbc-cli.sh status <job_id>

# View receipt with payment details
./scripts/aitbc-cli.sh receipts --job-id <job_id>
```

> **Available Models:** llama3.2, mistral, deepseek-r1:14b, gemma3, qwen2.5-coder, and 8+ more via Ollama integration. Processing time: 11-25 seconds. Rate: 0.02 AITBC per GPU second.

### Web Interface (Fastest)

1. **Visit the Marketplace**
   - Go to [aitbc.bubuit.net/marketplace](https://gitea.bubuit.net/oib/aitbc)

2. **Connect Your Wallet**
   - Connect MetaMask or create a new AITBC wallet

3. **Submit Your Job**
   - Upload your data or model, select parameters, and submit

4. **Get Results**
   - Receive verified results with cryptographic proof

## Popular Use Cases

### AI Inference ✅ LIVE
Run inference on pre-trained models including LLama, Mistral, DeepSeek, and custom models via Ollama

- Text generation (13+ models)
- Code generation (DeepSeek, Qwen)
- Translation (Qwen2.5-translator)
- Real-time processing (11-25s)

### Model Training
Train and fine-tune models on your data with privacy guarantees

- Fine-tuning LLMs
- Custom model training
- Federated learning
- Transfer learning

### Data Analysis
Process large datasets with confidential computing

- Statistical analysis
- Pattern recognition
- Predictive modeling
- Data visualization

### Secure Computation
Run sensitive computations with end-to-end encryption

- Financial modeling
- Healthcare analytics
- Legal document processing
- Proprietary algorithms

## SDK Examples

### Python SDK

```python
# Install the SDK
pip install aitbc

# Initialize client
from aitbc import AITBCClient

client = AITBCClient(api_key="your-api-key")

# Run inference
result = client.inference(
    model="gpt-4",
    prompt="Explain quantum computing",
    max_tokens=500,
    temperature=0.7
)

print(result.text)

# Verify the receipt
is_valid = client.verify_receipt(result.receipt_id)
print(f"Verified: {is_valid}")
```

### JavaScript SDK

```javascript
// Install the SDK
npm install @aitbc/client

// Initialize client
import { AITBCClient } from '@aitbc/client';

const client = new AITBCClient({
    apiKey: 'your-api-key',
    network: 'mainnet'
});

// Run inference
const result = await client.inference({
    model: 'stable-diffusion',
    prompt: 'A futuristic city',
    steps: 50,
    cfg_scale: 7.5
});

// Download the image
await client.downloadImage(result.imageId, './output.png');

// Verify computation
const verified = await client.verify(result.receiptId);
console.log('Computation verified:', verified);
```

### REST API

```bash
# Submit a job
curl -X POST https://aitbc.bubuit.net/api/v1/jobs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "inference",
    "model": "gpt-4",
    "input": {
      "prompt": "Hello, AITBC!",
      "max_tokens": 100
    },
    "privacy": {
      "confidential": true,
      "zk_proof": true
    }
  }'

# Check job status
curl -X GET https://aitbc.bubuit.net/api/v1/jobs/JOB_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Pricing

Flexible pricing options for every use case

### Pay-per-use
- **$0.01/1K tokens**
- No minimum commitment
- Pay only for what you use
- All models available
- Basic support

### Professional
- **$99/month**
- $500 included credits
- Priority processing
- Advanced models
- Email support
- API access

### Enterprise
- **Custom**
- Unlimited usage
- Dedicated resources
- Custom models
- 24/7 support
- SLA guarantee

## Privacy & Security

> **Your data is never stored or exposed** - All computations are performed in secure enclaves with zero-knowledge proof verification.

### Privacy Features

- **End-to-end encryption** - Your data is encrypted before leaving your device
- **Zero-knowledge proofs** - Prove computation without revealing inputs
- **Secure enclaves** - Computations run in isolated, verified environments
- **No data retention** - Providers cannot access or store your data
- **Audit trails** - Full transparency on blockchain

### Compliance

- GDPR compliant
- SOC 2 Type II certified
- HIPAA eligible
- ISO 27001 certified

## Best Practices

### Optimizing Performance

- Use appropriate model sizes for your task
- Batch requests when possible
- Enable caching for repeated queries
- Choose the right privacy level for your needs
- Monitor your usage and costs

### Security Tips

- Keep your API keys secure
- Use environment variables for credentials
- Enable two-factor authentication
- Regularly rotate your keys
- Use VPN for additional privacy

### Cost Optimization

- Start with smaller models for testing
- Use streaming for long responses
- Set appropriate limits and timeouts
- Monitor token usage
- Consider subscription plans for regular use

## Support & Resources

### Getting Help

- **Documentation**: [Full API reference](full-documentation.html)
- **Community**: [Join our Discord](https://discord.gg/aitbc)
- **Email**: [aitbc@bubuit.net](mailto:aitbc@bubuit.net)
- **Status**: [System status](https://status.aitbc.bubuit.net)

### Tutorials

- [Getting Started with AI Inference](#)
- [Building a Chat Application](#)
- [Image Generation Guide](#)
- [Privacy-Preserving ML](#)
- [API Integration Best Practices](#)

### Examples

- [GitHub Repository](#)
- [Code Examples](#)
- [Sample Applications](#)
- [SDK Documentation](#)

## Frequently Asked Questions

> **Question not answered?** Contact us at [aitbc@bubuit.net](mailto:aitbc@bubuit.net)

### General

- **How do I get started?** - Sign up for an account, connect your wallet, and submit your first job through the web interface or API.
- **What models are available?** - We support GPT-3.5/4, Claude, Llama, Stable Diffusion, and many custom models.
- **Can I use my own model?** - Yes, you can upload and run private models with full confidentiality.

### Privacy

- **Is my data private?** - Absolutely. Your data is encrypted and never exposed to providers.
- **How do ZK proofs work?** - They prove computation was done correctly without revealing inputs.
- **Can you see my prompts?** - No, prompts are encrypted and processed in secure enclaves.

### Technical

- **What's the response time?** - Most jobs complete in 1-5 seconds depending on complexity.
- **Do you support streaming?** - Yes, streaming is available for real-time applications.
- **Can I run batch jobs?** - Yes, batch processing is supported for large workloads.

### Billing

- **How am I billed?** - Pay-per-use or monthly subscription options available.
- **Can I set spending limits?** - Yes, you can set daily/monthly limits in your dashboard.
- **Do you offer refunds?** - Yes, we offer refunds for service issues within 30 days.

---

© 2025 AITBC. All rights reserved.
