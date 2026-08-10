# Python SDK Examples

Examples for `aitbc-sdk`, the Python client in `packages/py/aitbc-sdk`.

## Scope: what this SDK does and does not cover

`aitbc-sdk` is a **synchronous** client covering health, grants, wallet, registry, and
signed receipts. It is deliberately narrow.

**It has no job-submission API.** There is no `submit_job`, no `get_job`, and no `jobs`
attribute on any client in this package. To submit and track jobs, use one of:

- the HTTP endpoints directly — see [curl-examples.md](./curl-examples.md), which covers
  `POST /v1/jobs` and job status
- `aitbc_agent.ComputeConsumer` from `packages/py/aitbc-agent-sdk`, which is async — see
  [Job submission via the agent SDK](#job-submission-via-the-agent-sdk) below

## Installation

```bash
pip install aitbc-sdk
```

Requires Python 3.13.5+.

## Basic Setup

```python
from aitbc_sdk import AITBCClient

client = AITBCClient(
    base_url="http://localhost:8203",
    api_key="<YOUR_API_KEY>",   # sent as the X-Api-Key header; omit for unauthenticated calls
    timeout=30.0,
    max_retries=3,
)
```

`AITBCClient` is an alias of `CoordinatorAPIClient`; `CoordinatorClient` is a third name for
the same class. All three are interchangeable.

The client owns an HTTP connection pool, so close it when you are done. It is a context
manager, which is the easiest way:

```python
from aitbc_sdk import AITBCClient

with AITBCClient(base_url="http://localhost:8203", api_key="<YOUR_API_KEY>") as client:
    response = client.health()
    print(response.status, response.data)

# or explicitly
client = AITBCClient(base_url="http://localhost:8203")
try:
    ...
finally:
    client.close()
```

## Health Check

`health()` never raises — it reports transport failures as a status instead.

```python
response = client.health()      # SDKResponse

if response.status == 200:
    print("coordinator healthy:", response.data)
else:
    print("coordinator unreachable:", response.error)
```

`SDKResponse` has `status: int`, `data: dict`, and `error: str | None`.

## Wallet Operations

> **These endpoints are served by the wallet daemon (`apps/wallet`), not coordinator-api.**
> Point the client at the daemon's base URL to use `.wallet` — a coordinator-api base URL
> has no `/v1/wallets` routes at all. See [Which service to point at](#which-service-to-point-at).

```python
balance = client.wallet.get_balance("wallet-123")   # GET /v1/wallets/{wallet_id}/balance

print(balance.wallet_id)
print(balance.address)
print(balance.balance)      # Decimal, not float
print(balance.asset)        # "" — the daemon reports chain_id, not an asset
```

Balances are `Decimal`. Keep them that way — do not convert to `float` for arithmetic on
money.

```python
result = client.wallet.send_payment(       # POST /v1/wallets/{wallet_id}/send
    wallet_id="wallet-123",
    recipient="wallet-456",
    amount=1000,                           # integer base units, not a decimal string
    password="<WALLET_PASSWORD>",          # unlocks the stored key; required
    fee=36,
    chain_id="ait-mainnet",                # optional; daemon default if omitted
)
print(result["tx_hash"], result["status"])
```

`amount` and `fee` are integer base units. There is no `asset` parameter — the daemon picks
the chain via `chain_id`.

This endpoint is admin-guarded, so the `api_key` you construct the client with must be the
daemon's `WALLET_API_KEY`.

## Which service to point at

`AITBCClient` bundles two groups of endpoints that are served by **different** services, and
a single `base_url` reaches only one of them:

| Attribute | Served by | Base URL to use |
|---|---|---|
| `.wallet` | wallet daemon (`apps/wallet`) | the wallet daemon |
| `.registry`, `get_grant_summary()`, `health()` | coordinator-api | `http://localhost:8203` |

Construct one client per service if you need both.

## Registry Operations

```python
entry = client.registry.get_developer("0xabc...")    # GET /v1/developers/{address}

print(entry.id, entry.name, entry.wallet_address)
print(entry.metadata)                                # dict

entries = client.registry.list_registry(             # GET /v1/registry
    role="provider",
    limit=50,
    cursor=None,
)
for entry in entries:
    print(entry.id, entry.name)
```

`list_registry` returns an empty list if the response is not a list — it does not raise.

## Grants

```python
grants = client.registry.list_grants()               # GET /v1/grants

for grant in grants:
    print(grant.grant_id, grant.title, grant.status)
    print(grant.requested_amount, grant.approved_amount)   # both Decimal

summary = client.get_grant_summary("grant-123")      # GET /v1/grants/{id}/summary
print(summary.title, summary.status)
```

Unlike `list_registry`, `list_grants` raises `AITBCError` if the response is not a list.

## Signed Receipts

Receipts are the SDK's most complete area. `CoordinatorReceiptClient` is separate from
`AITBCClient` and takes its own connection settings.

```python
from aitbc_sdk import CoordinatorReceiptClient

receipts = CoordinatorReceiptClient(
    base_url="http://localhost:8203",
    api_key="<YOUR_API_KEY>",
    timeout=10.0,
    max_retries=3,
    backoff_seconds=0.5,
)
```

It is also a context manager, and should be closed for the same reason.

### Fetch receipts

```python
with CoordinatorReceiptClient(base_url="http://localhost:8203", api_key="<YOUR_API_KEY>") as rc:
    # Latest receipt; returns None on 404 rather than raising
    latest = rc.fetch_latest("job-123")          # GET /v1/jobs/{job_id}/receipt
    if latest is None:
        print("no receipt yet")

    # Every receipt for a job, following pagination
    history = rc.fetch_history("job-123")        # GET /v1/jobs/{job_id}/receipts

    # Same, but streamed rather than accumulated
    for receipt in rc.iter_receipts("job-123", page_size=100):
        print(receipt["receipt_id"])
```

### Page through receipts manually

```python
cursor = None
while True:
    page = rc.fetch_receipts_page(job_id="job-123", cursor=cursor, limit=100)
    for receipt in page.items:
        print(receipt["receipt_id"])
    if not page.next_cursor:
        break
    cursor = page.next_cursor
```

`ReceiptPage` has `items: list[dict]`, `next_cursor: str | None`, and `raw: dict`.

### Verify receipt signatures

Verification is local — it checks Ed25519 signatures and needs no network call.

```python
from aitbc_sdk import verify_receipt, verify_receipts

verification = verify_receipt(receipt)       # ReceiptVerification

if verification.verified:
    print("receipt is valid")
else:
    print("invalid:", verification.failure_reasons())
    # e.g. ["miner_signature_invalid:key-1", "coordinator_attestation_invalid:key-2"]

print(verification.miner_signature.key_id, verification.miner_signature.valid)
for attestation in verification.coordinator_attestations:
    print(attestation.key_id, attestation.valid, attestation.algorithm, attestation.reason)

# Verify a batch
verifications = verify_receipts(history)
```

`verified` is true only when the miner signature is valid **and** every coordinator
attestation is valid. A malformed or unsigned receipt marks that one receipt invalid rather
than raising, so a bad receipt does not take down a whole batch.

### Summarize verification across a job

```python
status = rc.summarize_receipts("job-123", page_size=100)     # ReceiptStatus

print(status.total, status.verified_count)
print(status.all_verified)          # True only if total > 0 and all verified
print(status.has_failures)
print(status.failure_reasons)       # {"miner_signature_invalid:key-1": 2, ...}

for failure in status.failures:
    print(failure.receipt_id, failure.reasons)

if status.latest_verified is not None:
    print("most recent verified receipt:", status.latest_verified.receipt)
```

## Error Handling

Exceptions live in `aitbc_sdk.errors` and are re-exported from the package root. There is no
`aitbc_sdk.exceptions` module.

```python
from aitbc_sdk import AITBCError, AITBCConnectionError, AITBCRateLimitError

try:
    balance = client.wallet.get_balance("wallet-123")
except AITBCRateLimitError as exc:
    print("rate limited:", exc)
except AITBCConnectionError as exc:
    print("could not reach coordinator:", exc)
except AITBCError as exc:
    print("SDK error:", exc)
```

Both `AITBCConnectionError` and `AITBCRateLimitError` subclass `AITBCError`, so catching
`AITBCError` alone catches everything this SDK raises. Order the handlers most-specific
first, as above.

Note that `health()` is the exception to this: it returns a non-200 `SDKResponse` instead of
raising.

## Retries and Circuit Breaking

The clients already retry internally via `max_retries`. These helpers are for wrapping your
own calls.

```python
from aitbc_sdk import SDKRetryPolicy, SDKCircuitBreaker, with_backoff

policy = SDKRetryPolicy(max_retries=3, enable_logging=False)
result = policy.execute(client.health)

# async variant
result = await policy.execute_async(some_async_callable)

breaker = SDKCircuitBreaker(threshold=5, timeout=60)
result = breaker.call(client.health)
print(breaker.is_open(), breaker.get_state())

# one-shot retry with exponential backoff
result = with_backoff(
    lambda: client.wallet.get_balance("wallet-123"),
    max_retries=3,
    backoff_seconds=0.5,
    exceptions=(AITBCConnectionError,),
)
```

`RetryConfig(max_retries=3, enable_logging=False)` is a plain dataclass for carrying these
settings around.

## Configuration from the Environment

```python
import os

from aitbc_sdk import AITBCClient

client = AITBCClient(
    base_url=os.getenv("AITBC_BASE_URL", "http://localhost:8203"),
    api_key=os.getenv("AITBC_API_KEY", ""),
)
```

`api_key` defaults to `""`, in which case no `X-Api-Key` header is sent at all.

## Job submission via the agent SDK

Job submission lives in `aitbc-agent-sdk` (`packages/py/aitbc-agent-sdk`), which is a
separate package and is **async**.

```bash
pip install aitbc-agent-sdk
```

```python
import asyncio

from aitbc_agent import ComputeConsumer


async def main() -> None:
    consumer = ComputeConsumer.create(
        name="my-consumer",
        agent_type="consumer",
        capabilities={"compute_type": "inference"},
    )

    job_id = await consumer.submit_job(        # POST /v1/jobs
        job_type="llm_inference",
        input_data={"model": "llama2", "prompt": "Hello, world!"},
        requirements={"gpu_memory": 8},
        max_price=0.15,
    )
    print("job id:", job_id)

    status = await consumer.get_job_status(job_id)    # GET /v1/jobs/{job_id}
    print("status:", status)

    print(consumer.get_spending_summary())


asyncio.run(main())
```

`ComputeConsumer.create()` does not take a coordinator URL and falls back to the `Agent`
default, `http://localhost:8107`. To point it elsewhere, construct it directly:

```python
from aitbc_agent import AgentCapabilities, AgentIdentity, ComputeConsumer

consumer = ComputeConsumer(
    identity=identity,              # AgentIdentity
    capabilities=capabilities,      # AgentCapabilities
    coordinator_url="http://localhost:8203",
)
```

`submit_job` returns a locally-generated placeholder id if the coordinator does not answer
with `201`, so check `get_job_status` rather than assuming the id is server-assigned.

## Related

- [cURL Examples](./curl-examples.md) — the HTTP endpoints, including job submission
- [API Reference](../README.md)
