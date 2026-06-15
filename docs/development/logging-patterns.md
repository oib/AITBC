# Logging Patterns and Guidelines

## Overview

This document describes the logging patterns and guidelines for AITBC services. We use structured logging with the standard Python `logging` module with JSON formatters to provide consistent, parseable logs across all services.

## Structured Logging Configuration

### Setup

Logging is configured using the central `aitbc.aitbc_logging` module:

```python
from aitbc.aitbc_logging import get_logger, configure_logging, setup_logger, log_context, LogContext

logger = get_logger(__name__)
```

### Log Format

Logs are output in JSON format (when `LOG_FORMAT=json`) or compact text format (default) with the following standard fields:

- `timestamp` - ISO 8601 timestamp (UTC)
- `level` - Log level (INFO, WARNING, ERROR, CRITICAL)
- `logger` - Logger name (module name)
- `message` - Log message
- `module` - Python module name
- `function` - Function/method name
- `line` - Source line number

Additional context fields are added as key-value pairs.

### Blockchain-Specific Fields

When using `get_blockchain_logger()` or the `StructuredFormatter`, blockchain-specific extra fields are automatically included:

- `chain_id` - Blockchain chain identifier
- `supported_chains` - Comma-separated supported chains
- `height` - Block height
- `hash` - Block/hash identifier
- `proposer` - Block proposer ID
- `error` - Error description
- `request_id` - Request correlation ID
- `node_id` - Node identifier
- `service` - Service name
- `environment` - Deployment environment
- `version` - Service version

### Log Levels

- **DEBUG** - Detailed diagnostic information
- **INFO** - General informational messages (default)
- **WARNING** - Warning messages for potentially harmful situations
- **ERROR** - Error messages for error events
- **CRITICAL** - Critical messages for very severe error events

## Logging Patterns

### Basic Logging

```python
from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

logger.info("Event description", field1=value1, field2=value2)
# Output (text): [INFO] Event description [field1=value1, field2=value2]
# Output (json): {"timestamp":"...","level":"INFO","message":"Event description","field1":value1,"field2":value2,...}
```

### Request Logging

Request ID correlation is automatically added by `RequestIDMiddleware`. The request ID is available in `request.state.request_id`:

```python
# In request handlers - request ID already in logger context via middleware
logger.info("Processing request", method=request.method, path=request.url.path)

# Manual binding for cross-service calls
correlation_id = request.headers.get("X-Request-ID", "unknown")
with log_context(request_id=correlation_id, chain_id="mainnet"):
    logger.info("Forwarding to downstream service", target="blockchain-rpc")
```

### Error Logging

Always include error context when logging errors:

```python
try:
    # operation
except Exception as e:
    logger.error("Operation failed", error=str(e), operation="some_operation")
    # Or with full exception info
    logger.exception("Operation failed", operation="some_operation")
    raise
```

### Performance Logging

Performance metrics are automatically logged by `PerformanceLoggingMiddleware`. Manual performance logging:

```python
import time

start_time = time.perf_counter()
# operation
duration = time.perf_counter() - start_time
logger.info("Operation completed", duration_ms=duration * 1000, operation="some_operation")
```

### Cross-Service Correlation

Use `log_context` for propagating correlation IDs across service boundaries:

```python
from aitbc.aitbc_logging import log_context, LogContext

# Context manager approach
with log_context(request_id="req-123", chain_id="mainnet", node_id="node-1"):
    logger.info("Starting cross-service operation")
    await call_downstream_service()

# Class-based for long-lived contexts
context = LogContext(request_id="req-123", user_id="user-456")
with context:
    logger.info("Processing user request")
    # All logs within this block include request_id and user_id
```

## Middleware

### Request ID Middleware

Adds a unique request ID to each request for correlation:

- Generates or retrieves request ID from `X-Request-ID` header
- Binds request ID to logger context
- Adds request ID to response headers (`X-Request-ID`)
- Logs request start and completion

### Performance Logging Middleware

Tracks request timing:

- Logs request duration in milliseconds
- Adds `X-Process-Time` header to responses
- Logs method, path, status code, and client IP

### Error Handler Middleware

Catches unhandled exceptions and returns structured error responses:

- Logs full exception traceback
- Returns consistent error format
- Includes request ID in error response

## Guidelines

### DO

- Use structured logging with key-value pairs (`extra={...}`)
- Include relevant context in log messages
- Use appropriate log levels (INFO for production, DEBUG for debugging)
- Log errors with exception context (`logger.exception()` or `error=...`)
- Use request ID for correlation across services
- Use `extra={...}` for all contextual data

### DON'T

- Use string formatting in log messages (use key-value pairs instead)
- Log sensitive information (passwords, tokens, private keys, PII)
- Use bare `except:` clauses (always specify exception type)
- Log at DEBUG level in production unless necessary
- Log the same information multiple times
- Pass keyword arguments directly to log methods (use `extra={...}`)

## Examples

### Good

```python
logger.info(
    "User logged in",
    user_id=user.id,
    email=user.email,
    ip_address=request.client.host,
)

logger.error(
    "Failed to process transaction",
    error=str(e),
    tx_hash=tx_hash,
    chain_id=chain_id,
)

logger.info(
    "Block imported",
    extra={
        "chain_id": "mainnet",
        "height": 12345,
        "proposer": "validator-1",
        "tx_count": 42,
    }
)
```

### Bad

```python
# String formatting instead of structured
logger.info(f"User {user.email} logged in from {request.client.host}")

# Missing context
logger.error("Transaction failed")  # No error details, no tx context

# Keyword args instead of extra dict
logger.info("Block produced", chain_id="mainnet", height=100)  # TypeError!
```

## Configuration

Log level and format can be configured via environment variables:

```bash
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log format: json or text
LOG_FORMAT=json

# Log directory for file rotation (optional)
LOG_DIR=/var/log/aitbc
```

### Programmatic Configuration

```python
from aitbc.aitbc_logging import configure_logging, setup_logger

# Configure root logger (call once at startup)
configure_logging(
    level="INFO",
    structured=True,   # Enable JSON output
    service_name="my-service",
    to_file=True,      # Enable file rotation
)

# Or setup individual logger with file rotation
logger = setup_logger(
    "my-service",
    level="INFO",
    service_name="my-service",
    to_file=True,
    rotation="daily",      # or "size"
    max_files=7,           # Keep 7 days/rotations
)
```

### Environment Variables for Wrappers

All uvicorn wrapper scripts support:

```bash
LOG_LEVEL=info          # Default: info (was warning)
ACCESS_LOG=true         # Default: true, set to false to disable access logs
```

## File Rotation

When `to_file=True` and `service_name` is provided:

- Logs written to `$LOG_DIR/{service_name}/{service_name}.log`
- Daily rotation at midnight (keeps 7 days by default)
- Size-based rotation available (`rotation="size"`)
- JSON formatter used for file output regardless of `LOG_FORMAT`

```python
# Creates /var/log/aitbc/my-service/my-service.log with daily rotation
logger = setup_logger("my-service", service_name="my-service", to_file=True)
```

## Migration Guide

### From Standard Logging

1. Replace `import logging` with `from aitbc.aitbc_logging import get_logger`
2. Replace `logging.getLogger(__name__)` with `get_logger(__name__)`
3. Replace f-strings with key-value pairs via `extra={...}`
4. Update log calls to use structured format

### Before

```python
import logging

logger = logging.getLogger(__name__)
logger.info(f"Processing request {request_id}")
```

### After

```python
from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)
logger.info("Processing request", extra={"request_id": request_id})
```

### From Structlog (if applicable)

1. Replace `import structlog` with `from aitbc.aitbc_logging import get_logger`
2. Replace `structlog.get_logger()` with `get_logger(__name__)`
3. Replace `logger.bind(...)` with `log_context(...)` or `LogContext(...)`
4. Replace `logger.info("event", key=value)` with `logger.info("event", extra={"key": value})`

## Ruff Rules

The following Ruff rules are enforced for logging (via `G` and `LOG` rules):

- `G001` - logging statement uses f-string (enforce structured logging)
- `G002` - logging statement uses .format() or % formatting (enforce structured logging)
- `G` - logging-string-format (enforce structured logging)
- `LOG` - logging best practices

**Migration Status**: ✅ Complete (v0.4.22+)
- All files migrated from `import logging` to `from aitbc.aitbc_logging import get_logger`
- G001 and G002 rules now enforced across codebase
- Logging infrastructure centralized in `aitbc/aitbc_logging.py`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    aitbc.aitbc_logging                       │
├─────────────────────────────────────────────────────────────┤
│  get_logger()          → Returns standard Logger            │
│  get_blockchain_logger() → Logger with BlockchainTextFormatter
│  setup_logger()        → Logger with optional file rotation │
│  configure_logging()   → Configures root logger             │
│  log_context()         → Context manager for correlation    │
│  LogContext            → Class-based correlation context    │
├─────────────────────────────────────────────────────────────┤
│  BlockchainTextFormatter → Compact text with [key=value]    │
│  StructuredFormatter   → JSON with standard + blockchain fields
├─────────────────────────────────────────────────────────────┤
│  TimedRotatingFileHandler (daily rotation)                  │
│  RotatingFileHandler (size-based rotation)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Service Wrappers                          │
├─────────────────────────────────────────────────────────────┤
│  LOG_LEVEL=info (default)     → Via environment             │
│  ACCESS_LOG=true (default)    → Via environment             │
└─────────────────────────────────────────────────────────────┘
```
