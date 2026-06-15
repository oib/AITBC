# Rate Limiting

This guide covers token bucket algorithm and IP-based rate limiting.

## Token Bucket Algorithm

```python
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, rate: int, per: int):
        self.rate = rate
        self.per = per
        self.tokens = defaultdict(lambda: rate)
        self.last_update = defaultdict(time.time)

    def allow(self, identifier: str) -> bool:
        now = time.time()
        elapsed = now - self.last_update[identifier]
        self.tokens[identifier] = min(self.rate, self.tokens[identifier] + elapsed * self.rate / self.per)
        self.last_update[identifier] = now

        if self.tokens[identifier] >= 1:
            self.tokens[identifier] -= 1
            return True
        return False
```

## IP-based Rate Limiting

```python
from fastapi import Request, HTTPException

rate_limiter = RateLimiter(rate=100, per=60)

@app.post("/v1/jobs")
async def submit_job(request: Request):
    client_ip = request.client.host
    if not rate_limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    # Process request
```

## See Also

- [Authentication](authentication.md) - Brute force protection
- [Web Security](web-security.md) - CSRF protection
- [Access Control](access-control.md) - Permission checks
