---
title: API Authentication
description: Understanding and implementing API authentication
---

# API Authentication

AITBC has three authentication surfaces, depending on which service you call:

1. **`X-Api-Key` service keys** — admin-guarded and follower-facing routes on
   coordinator-api, the wallet daemon, exchange, and miner/settlement routers.
   Keys are provisioned per-service through environment variables
   (`MINER_API_KEYS`, `COORDINATOR_API_KEY`, `EXCHANGE_API_KEY`, the wallet
   daemon key) — there is no self-service key portal and no `aitbc api-keys`
   command. See `docs/ops/follower-api-key.md` for how operator keys are
   issued and rotated.
2. **Coordinator session JWT** — `aitbc auth login` performs a wallet-signed
   nonce challenge and stores a coordinator JWT, which the CLI then sends for
   session endpoints. `aitbc auth status` shows the stored credential and
   `aitbc auth logout` deletes it.
3. **Transaction signatures** — mutating chain routes (`/rpc/staking/*`,
   bridge confirm, escrow release) verify the wallet/staker/confirmer
   signature inside the signed payload itself rather than an HTTP credential.

## Using an API Key

### HTTP Header

```http
X-Api-Key: your_api_key_here
```

### Environment Variable

Keys are configured on the **server** side via the service's environment
(e.g. `MINER_API_KEYS=key-one,key-two`). Clients pass the key per request,
per SDK constructor, or through the CLI's client-side env var:

```bash
export AITBC_API_KEY="your_api_key_here"   # picked up by `aitbc` commands
```

### SDK Configuration

```python
from aitbc_sdk import AITBCClient

client = AITBCClient(base_url="http://localhost:8203", api_key="your_api_key")
# sends X-Api-Key on every request
```

## Security Best Practices

- Never commit API keys to version control; keys live in per-service env
  files outside the repository.
- Rotate keys regularly (a fleet-wide rotation is scheduled for release v1).
- Use different keys for different environments.

## Rate Limits

Rate limiting is enforced per-route by `@rate_limit` decorators (see
`aitbc/rate_limiting.py`) — typically a few dozen requests per minute on
mutation endpoints — and by the API gateway when it fronts a service. There
are no per-plan request tiers.

## Error Handling

```python
from aitbc.exceptions import AuthenticationError

try:
    developers = client.registry.list_developers()
except AuthenticationError:
    print("Invalid API key")
```

## Key Management

There is no CLI command to list, revoke, or regenerate keys — keys are
plain env values. To rotate one:

1. Update the service's env file (e.g. `MINER_API_KEYS` on the coordinator).
2. `systemctl restart` the affected unit.
3. Distribute the new value to the clients that hold it.

To check which credential the CLI is holding for the coordinator session:

```bash
aitbc auth status
```
