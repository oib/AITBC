# Nemotron Cloud Offer - Monitoring

**Last Updated**: 2026-06-30
**Version**: 1.0

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

## Related Topics

- [Quick Start](./nemotron-quick-start.md) - Get started with Nemotron
- [Discovery](./nemotron-discovery.md) - Find available offers
- [Inference](./nemotron-inference.md) - Execute inference with payment
- [Agent Integration](./nemotron-integration.md) - Integrate with your agent code
