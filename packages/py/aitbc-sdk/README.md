# AITBC SDK

Synchronous Python client for the AITBC coordinator API: health, wallet, registry, grants,
and signed receipts.

**This package has no job-submission API.** To submit and track jobs, call `POST /v1/jobs`
directly or use the async `ComputeConsumer` from `aitbc-agent-sdk`.

## Installation

```bash
pip install aitbc-sdk
```

## Requirements

- **Python**: 3.13.5 or later
- **Dependencies**: httpx, pydantic, aitbc-crypto

## Compatibility & Stability

### Python Version Support
- **Minimum Version**: Python 3.13.5+
- **Recommended**: Python 3.13.5 or 3.14
- **Guarantee**: All APIs maintain backward compatibility within Python 3.13.5+
- **Security**: Cryptographic operations maintain security properties across versions

### API Stability
- **Major Version**: 0.x (pre-1.0, APIs may change with notice)
- **Deprecation Policy**: Deprecated features marked with warnings for 2+ releases
- **Breaking Changes**: Announced in release notes with migration guides
- **Semantic Versioning**: Follows semver.org specifications

## Quick Start

```python
from aitbc_sdk import AITBCClient

with AITBCClient(base_url="https://aitbc.bubuit.net", api_key="your-api-key") as client:
    print(client.health().status)
    print(client.wallet.get_balance("wallet-123").balance)   # Decimal
```

## Features

- **Wallet**: balance lookups and payment submission, with `Decimal` amounts
- **Registry**: developer and provider registry lookups
- **Grants**: list grant proposals and fetch summaries
- **Receipt Verification**: fetch signed receipts and verify Ed25519 signatures locally
- **Retries**: retry policy, circuit breaker, and exponential backoff helpers

## API Reference

### Client Initialization

```python
from aitbc_sdk import AITBCClient

client = AITBCClient(
    base_url="https://aitbc.bubuit.net",
    api_key="your-api-key",   # sent as X-Api-Key; omit to send no auth header
    timeout=30.0,
    max_retries=3,
)
```

`AITBCClient` is an alias of `CoordinatorAPIClient`. The client owns an HTTP connection
pool — use it as a context manager, or call `client.close()` when done.

### Coordinator Operations

```python
response = client.health()                       # SDKResponse; does not raise
print(response.status, response.data, response.error)

summary = client.get_grant_summary("grant-123")  # GrantSummary
```

### Wallet Operations

```python
balance = client.wallet.get_balance("wallet-123")          # WalletBalance
print(balance.address, balance.balance, balance.asset)     # balance is Decimal

client.wallet.send_payment(
    wallet_id="wallet-123",
    recipient_id="wallet-456",
    amount="10.50",        # str, not float
    asset="AITBC",
)
```

### Registry Operations

```python
entry = client.registry.get_developer("0xabc...")            # RegistryEntry
entries = client.registry.list_registry(role="provider", limit=50)
grants = client.registry.list_grants()                       # list[GrantSummary]
```

### Receipt Operations

Receipts use a separate client:

```python
from aitbc_sdk import CoordinatorReceiptClient, verify_receipt

with CoordinatorReceiptClient(base_url="https://aitbc.bubuit.net", api_key="your-api-key") as rc:
    latest = rc.fetch_latest("job-123")          # None if there is no receipt yet
    history = rc.fetch_history("job-123")
    status = rc.summarize_receipts("job-123")    # ReceiptStatus

    print(status.verified_count, "of", status.total, "verified")

if latest is not None:
    print(verify_receipt(latest).verified)       # local Ed25519 check, no network call
```

### Errors

```python
from aitbc_sdk import AITBCError, AITBCConnectionError, AITBCRateLimitError
```

Both specific errors subclass `AITBCError`. They live in `aitbc_sdk.errors`; there is no
`aitbc_sdk.exceptions` module.

## Configuration

The SDK reads no environment variables — pass `base_url` and `api_key` to the constructor.
To drive them from the environment, do it in your own code:

```python
import os

from aitbc_sdk import AITBCClient

client = AITBCClient(
    base_url=os.getenv("AITBC_BASE_URL", "http://localhost:8203"),
    api_key=os.getenv("AITBC_API_KEY", ""),
)
```

## Development

Install in development mode:

```bash
git clone https://github.com/oib/AITBC.git
cd AITBC/packages/py/aitbc-sdk
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

## License

MIT License - see LICENSE file for details.

## Support

- **Documentation**: https://aitbc.bubuit.net/docs/
- **Issues**: https://github.com/oib/AITBC/issues
- **Discussions**: https://github.com/oib/AITBC/discussions
