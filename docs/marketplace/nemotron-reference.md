# Nemotron Cloud Offer - Reference

**Last Updated**: 2026-06-30
**Version**: 1.0

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

## Related Topics

- [Quick Start](./nemotron-quick-start.md) - Get started with Nemotron
- [Discovery](./nemotron-discovery.md) - Find available offers
- [Inference](./nemotron-inference.md) - Execute inference with payment
- [Monitoring](./nemotron-monitoring.md) - Track costs and performance
- [Integration](./nemotron-integration.md) - Integrate with your agent code
