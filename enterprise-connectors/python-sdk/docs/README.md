# AITBC Enterprise Connectors SDK

Python SDK for integrating AITBC with enterprise systems including payment processors, ERP systems, and other business applications.

## Quick Start

### Installation

```bash
pip install aitbc-enterprise
```

### Basic Usage

```python
import asyncio
from aitbc_enterprise import AITBCClient, ConnectorConfig
from aitbc_enterprise.payments import StripeConnector

async def main():
    # Configure AITBC client
    config = ConnectorConfig(
        base_url="https://api.aitbc.io",
        api_key="your-api-key",
        enterprise_id="enterprise-123"
    )
    
    # Create client and connector
    async with AITBCClient(config) as client:
        stripe = StripeConnector(
            client=client,
            config=config,
            stripe_api_key="sk_test_your-stripe-key"
        )
        
        await stripe.initialize()
        
        # Create a charge
        charge = await stripe.create_charge(
            amount=2000,  # $20.00
            currency="usd",
            source="pm_card_visa",
            description="AITBC service"
        )
        
        print(f"Charge created: {charge.id}")
        
        await stripe.cleanup()

asyncio.run(main())
```

## Features

- **Async/Await Support**: Full async implementation for high performance
- **Enterprise Ready**: Built-in rate limiting, metrics, and error handling
- **Extensible**: Plugin architecture for custom connectors
- **Secure**: HSM-backed key management and audit logging
- **Compliant**: GDPR, SOC 2, and PCI DSS compliant

## Supported Systems

### Payment Processors
- ✅ Stripe
- ⏳ PayPal (Coming soon)
- ⏳ Square (Coming soon)

### ERP Systems
- ⏳ SAP (IDOC/BAPI)
- ⏳ Oracle (REST/SOAP)
- ⏳ NetSuite (SuiteTalk)

## Architecture

The SDK uses a modular architecture with dependency injection:

```
AITBCClient
├── Core Components
│   ├── AuthHandler (Bearer, OAuth2, HMAC, etc.)
│   ├── RateLimiter (Token bucket, Sliding window)
│   ├── MetricsCollector (Performance tracking)
│   └── WebhookHandler (Event processing)
├── BaseConnector
│   ├── Validation
│   ├── Error Handling
│   ├── Batch Operations
│   └── Event Handlers
└── Specific Connectors
    ├── PaymentConnector
    └── ERPConnector
```

## Configuration

### Basic Configuration

```python
config = ConnectorConfig(
    base_url="https://api.aitbc.io",
    api_key="your-api-key",
    timeout=30.0,
    max_retries=3
)
```

### Enterprise Features

```python
config = ConnectorConfig(
    base_url="https://api.aitbc.io",
    api_key="your-api-key",
    enterprise_id="enterprise-123",
    tenant_id="tenant-456",
    region="us-east-1",
    rate_limit=100,  # requests per second
    enable_metrics=True,
    webhook_secret="whsec_your-secret"
)
```

### Authentication

The SDK supports multiple authentication methods:

```python
# Bearer token (default)
config = ConnectorConfig(
    auth_type="bearer",
    api_key="your-token"
)

# OAuth 2.0
config = ConnectorConfig(
    auth_type="oauth2",
    auth_config={
        "client_id": "your-client-id",
        "client_secret": "your-secret",
        "token_url": "https://oauth.example.com/token"
    }
)

# HMAC signature
config = ConnectorConfig(
    auth_type="hmac",
    api_key="your-key",
    auth_config={
        "secret": "your-secret",
        "algorithm": "sha256"
    }
)
```

## Error Handling

The SDK provides comprehensive error handling:

```python
from aitbc_enterprise.exceptions import (
    AITBCError,
    AuthenticationError,
    RateLimitError,
    PaymentError,
    ValidationError
)

try:
    charge = await stripe.create_charge(...)
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except PaymentError as e:
    print(f"Payment failed: {e}")
except AITBCError as e:
    print(f"AITBC error: {e}")
```

## Webhooks

Handle webhooks with built-in verification:

```python
from aitbc_enterprise.webhooks import StripeWebhookHandler

# Create webhook handler
webhook_handler = StripeWebhookHandler(
    secret="whsec_your-webhook-secret"
)

# Add custom handler
async def handle_charge(event):
    print(f"Charge: {event.data}")

webhook_handler.add_handler("charge.succeeded", handle_charge)

# Process webhook
result = await webhook_handler.handle(payload, signature)
```

## Batch Operations

Process multiple operations efficiently:

```python
# Batch charges
operations = [
    {
        "operation": "create_charge",
        "data": {"amount": 1000, "currency": "usd", "source": "pm_123"}
    },
    {
        "operation": "create_charge",
        "data": {"amount": 2000, "currency": "usd", "source": "pm_456"}
    }
]

results = await stripe.batch_execute(operations)
successful = sum(1 for r in results if r.success)
```

## Metrics and Monitoring

Enable metrics collection:

```python
config = ConnectorConfig(
    enable_metrics=True,
    metrics_endpoint="https://your-metrics.example.com"
)

# Metrics are automatically collected
# Access metrics summary
print(stripe.metrics)
```

## Testing

Use the test mode for development:

```python
# Use test API keys
config = ConnectorConfig(
    base_url="https://api-test.aitbc.io",
    api_key="test-key"
)

stripe = StripeConnector(
    client=client,
    config=config,
    stripe_api_key="sk_test_key"  # Stripe test key
)
```

## Examples

See the `examples/` directory for complete examples:

- `stripe_example.py` - Payment processing
- `webhook_example.py` - Webhook handling
- `enterprise_example.py` - Enterprise features

## Support

- **Documentation**: https://docs.aitbc.io/enterprise-sdk
- **Issues**: https://github.com/aitbc/enterprise-sdk/issues
- **Support**: enterprise@aitbc.io
- **Security**: security@aitbc.io

## License

Copyright © 2024 AITBC. All rights reserved.
