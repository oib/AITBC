# AITBC Enterprise Connectors API Specification

## Overview

This document describes the API specification for the AITBC Enterprise Connectors SDK, including all available methods, parameters, and response formats.

## Core API

### AITBCClient

The main client class for connecting to AITBC.

#### Constructor

```python
AITBCClient(
    config: ConnectorConfig,
    session: Optional[ClientSession] = None,
    auth_handler: Optional[AuthHandler] = None,
    rate_limiter: Optional[RateLimiter] = None,
    metrics: Optional[MetricsCollector] = None
)
```

#### Methods

##### connect()
Establish connection to AITBC.

```python
async connect() -> None
```

##### disconnect()
Close connection to AITBC.

```python
async disconnect() -> None
```

##### request()
Make authenticated request to AITBC API.

```python
async request(
    method: str,
    path: str,
    **kwargs
) -> Dict[str, Any]
```

**Parameters:**
- `method` (str): HTTP method (GET, POST, PUT, DELETE)
- `path` (str): API endpoint path
- `**kwargs`: Additional request parameters

**Returns:**
- `Dict[str, Any]`: Response data

##### get(), post(), put(), delete()
Convenience methods for HTTP requests.

```python
async get(path: str, **kwargs) -> Dict[str, Any]
async post(path: str, **kwargs) -> Dict[str, Any]
async put(path: str, **kwargs) -> Dict[str, Any]
async delete(path: str, **kwargs) -> Dict[str, Any]
```

### ConnectorConfig

Configuration class for connectors.

#### Parameters

```python
@dataclass
class ConnectorConfig:
    base_url: str
    api_key: str
    api_version: str = "v1"
    timeout: float = 30.0
    max_connections: int = 100
    max_retries: int = 3
    retry_backoff: float = 1.0
    rate_limit: Optional[int] = None
    burst_limit: Optional[int] = None
    auth_type: str = "bearer"
    auth_config: Dict[str, Any] = field(default_factory=dict)
    webhook_secret: Optional[str] = None
    webhook_endpoint: Optional[str] = None
    enable_metrics: bool = True
    log_level: str = "INFO"
    enterprise_id: Optional[str] = None
    tenant_id: Optional[str] = None
    region: Optional[str] = None
```

## Base Connector API

### BaseConnector

Abstract base class for all connectors.

#### Methods

##### initialize()
Initialize the connector.

```python
async initialize() -> None
```

##### cleanup()
Cleanup connector resources.

```python
async cleanup() -> None
```

##### execute_operation()
Execute an operation with validation.

```python
async execute_operation(
    operation: str,
    data: Dict[str, Any],
    **kwargs
) -> OperationResult
```

##### batch_execute()
Execute multiple operations concurrently.

```python
async batch_execute(
    operations: List[Dict[str, Any]],
    max_concurrent: int = 10
) -> List[OperationResult]
```

##### sync()
Synchronize data with external system.

```python
async sync(
    since: Optional[datetime] = None,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]
```

#### Properties

##### is_initialized
Check if connector is initialized.

```python
@property
def is_initialized() -> bool
```

##### last_sync
Get last sync timestamp.

```python
@property
def last_sync() -> Optional[datetime]
```

##### metrics
Get connector metrics.

```python
@property
def metrics() -> Dict[str, Any]
```

## Payment Connector API

### PaymentConnector

Abstract base class for payment processors.

#### Methods

##### create_charge()
Create a charge.

```python
async create_charge(
    amount: int,
    currency: str,
    source: str,
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Charge
```

**Parameters:**
- `amount` (int): Amount in smallest currency unit (cents)
- `currency` (str): 3-letter currency code
- `source` (str): Payment source ID
- `description` (str, optional): Charge description
- `metadata` (Dict, optional): Additional metadata

**Returns:**
- `Charge`: Created charge object

##### create_refund()
Create a refund.

```python
async create_refund(
    charge_id: str,
    amount: Optional[int] = None,
    reason: Optional[str] = None
) -> Refund
```

##### create_payment_method()
Create a payment method.

```python
async create_payment_method(
    type: str,
    card: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> PaymentMethod
```

##### create_subscription()
Create a subscription.

```python
async create_subscription(
    customer: str,
    items: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None
) -> Subscription
```

##### cancel_subscription()
Cancel a subscription.

```python
async cancel_subscription(
    subscription_id: str,
    at_period_end: bool = True
) -> Subscription
```

### Data Models

#### Charge

```python
@dataclass
class Charge:
    id: str
    amount: int
    currency: str
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    description: Optional[str]
    metadata: Dict[str, Any]
    amount_refunded: int = 0
    refunds: List[Dict[str, Any]] = None
    payment_method_id: Optional[str] = None
    payment_method_details: Optional[Dict[str, Any]] = None
```

#### Refund

```python
@dataclass
class Refund:
    id: str
    amount: int
    currency: str
    status: RefundStatus
    created_at: datetime
    updated_at: datetime
    charge_id: str
    reason: Optional[str]
    metadata: Dict[str, Any]
```

#### PaymentMethod

```python
@dataclass
class PaymentMethod:
    id: str
    type: str
    created_at: datetime
    metadata: Dict[str, Any]
    brand: Optional[str] = None
    last4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
```

#### Subscription

```python
@dataclass
class Subscription:
    id: str
    status: SubscriptionStatus
    created_at: datetime
    updated_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    customer_id: str
    metadata: Dict[str, Any]
    amount: Optional[int] = None
    currency: Optional[str] = None
    interval: Optional[str] = None
    interval_count: Optional[int] = None
    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
```

## ERP Connector API

### ERPConnector

Base class for ERP connectors.

#### Methods

##### create_entity()
Create entity in ERP.

```python
async _create_entity(
    entity_type: str,
    data: Dict[str, Any]
) -> OperationResult
```

##### update_entity()
Update entity in ERP.

```python
async _update_entity(
    entity_type: str,
    data: Dict[str, Any]
) -> OperationResult
```

##### delete_entity()
Delete entity from ERP.

```python
async _delete_entity(
    entity_type: str,
    data: Dict[str, Any]
) -> OperationResult
```

##### sync_data()
Synchronize data from ERP.

```python
async _sync_data(
    data: Dict[str, Any]
) -> OperationResult
```

##### batch_sync()
Batch synchronize data.

```python
async _batch_sync(
    data: Dict[str, Any]
) -> OperationResult
```

## Webhook API

### WebhookHandler

Handles webhook processing and verification.

#### Methods

##### setup()
Setup webhook handler.

```python
async setup(
    endpoint: str,
    secret: str = None
) -> None
```

##### cleanup()
Cleanup webhook handler.

```python
async cleanup() -> None
```

##### add_handler()
Add handler for specific event type.

```python
def add_handler(
    event_type: str,
    handler: Callable[[WebhookEvent], Awaitable[None]]
) -> None
```

##### verify()
Verify webhook signature.

```python
async verify(
    payload: bytes,
    signature: str,
    algorithm: str = "sha256"
) -> bool
```

##### handle()
Handle incoming webhook.

```python
async handle(
    payload: bytes,
    signature: str = None
) -> Dict[str, Any]
```

## Error Handling

### Exception Hierarchy

```
AITBCError
├── AuthenticationError
├── RateLimitError
├── APIError
├── ConfigurationError
├── ConnectorError
│   ├── PaymentError
│   ├── ERPError
│   ├── SyncError
│   └── WebhookError
├── ValidationError
└── TimeoutError
```

### Error Response Format

```python
{
    "success": false,
    "error": "Error message",
    "error_code": "ERROR_CODE",
    "details": {
        "field": "value",
        "additional": "info"
    }
}
```

## Rate Limiting

### Rate Limit Headers

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
Retry-After: 60
```

### Rate Limit Error

```python
RateLimitError(
    message="Rate limit exceeded",
    retry_after=60
)
```

## Metrics

### Metric Types

- **Counters**: Cumulative counts (requests, errors)
- **Gauges**: Current values (active connections)
- **Histograms**: Distributions (response times)
- **Timers**: Duration measurements

### Metrics Format

```python
{
    "timestamp": "2024-01-01T00:00:00Z",
    "source": "aitbc-enterprise-sdk",
    "metrics": [
        {
            "name": "requests_total",
            "value": 1000,
            "tags": {"method": "POST", "status": "200"}
        }
    ]
}
```

## Authentication

### Bearer Token

```python
headers = {
    "Authorization": "Bearer your-token"
}
```

### OAuth 2.0

```python
headers = {
    "Authorization": "Bearer access-token"
}
```

### HMAC Signature

```python
headers = {
    "X-API-Key": "your-key",
    "X-Timestamp": "1640995200",
    "X-Signature": "signature"
}
```

## SDK Versioning

The SDK follows semantic versioning:

- **Major**: Breaking changes
- **Minor**: New features (backward compatible)
- **Patch**: Bug fixes (backward compatible)

Example: `1.2.3`

## Response Format

### Success Response

```python
{
    "success": true,
    "data": {...},
    "metadata": {...}
}
```

### Error Response

```python
{
    "success": false,
    "error": "Error message",
    "error_code": "ERROR_CODE",
    "details": {...}
}
```

## Pagination

### Request Parameters

```python
{
    "limit": 100,
    "offset": 0,
    "starting_after": "cursor_id"
}
```

### Response Format

```python
{
    "data": [...],
    "has_more": true,
    "next_page": "cursor_id"
}
```
