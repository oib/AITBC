# SDK Reference

The AITBC SDK (`packages/py/aitbc-sdk`) provides lightweight clients for
coordinator-api, wallet, and registry operations.

## Installation

```bash
pip install /opt/aitbc/packages/py/aitbc-sdk
```

## Quick start

```python
from aitbc_sdk import AITBCClient

client = AITBCClient(
    coordinator_url="http://localhost:8000",
    api_key="your-api-key",
)

# Registry
profile = client.registry.get_developer("0x...")

# Grants
grants = client.registry.list_grants()

# Wallet
balance = client.wallet.get_balance("wallet-id")
```

## Error handling

SDK calls raise `aitbc_sdk.errors.AITBCError` on failures. Use `retry.with_backoff`
for automatic retries:

```python
from aitbc_sdk.retry import with_backoff

result = with_backoff(lambda: client.wallet.get_balance("wallet-id"))
```

## Types

Shared request/response types live in `aitbc.types.sdk`:

- `SDKRequest` / `SDKResponse`
- `WalletBalance`
- `RegistryEntry`
- `GrantSummary`

## White-label core

For headless integrations use `aitbc-core` (`packages/aitbc-core`):

```python
from aitbc_core.manifest.brand import BrandManifest
from aitbc_core.plugins.manifest import PluginHookRegistry
```
