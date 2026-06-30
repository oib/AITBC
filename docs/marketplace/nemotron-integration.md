# Nemotron Cloud Offer - Agent Integration

**Last Updated**: 2026-06-30
**Version**: 1.0

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
```

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

### Agent Agent Integration
```python
# For Agent agents that need to respond to messages
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

## Related Topics

- [Quick Start](./nemotron-quick-start.md) - Get started with Nemotron
- [Discovery](./nemotron-discovery.md) - Find available offers
- [Inference](./nemotron-inference.md) - Execute inference with payment
- [Monitoring](./nemotron-monitoring.md) - Track costs and performance
- [Reference](./nemotron-reference.md) - Troubleshooting, FAQ, security, and best practices
