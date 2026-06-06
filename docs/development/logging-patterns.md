# Logging Patterns and Guidelines

## Overview

This document describes the logging patterns and guidelines for AITBC services. We use structured logging with `structlog` to provide consistent, parseable logs across all services.

## Structured Logging Configuration

### Setup

Logging is configured using `structlog` in `app_logging.py`:

```python
from aitbc import get_logger

logger = get_logger(__name__)
```

### Log Format

Logs are output in JSON format with the following fields:
- `timestamp` - ISO 8601 timestamp
- `logger` - Logger name (module name)
- `level` - Log level (INFO, WARNING, ERROR, etc.)
- `event` - Event description
- Additional context fields as key-value pairs

### Log Levels

- **DEBUG** - Detailed diagnostic information
- **INFO** - General informational messages
- **WARNING** - Warning messages for potentially harmful situations
- **ERROR** - Error messages for error events
- **CRITICAL** - Critical messages for very severe error events

## Logging Patterns

### Basic Logging

```python
logger.info("Event description", field1=value1, field2=value2)
```

### Request Logging

Request ID correlation is automatically added by `RequestIDMiddleware`. The request ID is available in `request.state.request_id`:

```python
logger = logger.bind(request_id=request.state.request_id)
logger.info("Processing request", method=request.method, path=request.url.path)
```

### Error Logging

Always include error context when logging errors:

```python
try:
    # operation
except Exception as e:
    logger.error("Operation failed", error=str(e), operation="some_operation")
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

## Middleware

### Request ID Middleware

Adds a unique request ID to each request for correlation:

- Generates or retrieves request ID from `X-Request-ID` header
- Binds request ID to logger context
- Adds request ID to response headers
- Logs request start and completion

### Performance Logging Middleware

Tracks request timing:

- Logs request duration in milliseconds
- Adds `X-Process-Time` header to responses
- Logs method, path, and status code

## Guidelines

### DO

- Use structured logging with key-value pairs
- Include relevant context in log messages
- Use appropriate log levels
- Log errors with exception context
- Use request ID for correlation

### DON'T

- Use string formatting in log messages (use key-value pairs instead)
- Log sensitive information (passwords, tokens, etc.)
- Use bare `except:` clauses
- Log at DEBUG level in production unless necessary
- Log the same information multiple times

## Examples

### Good

```python
logger.info(
    "User logged in",
    user_id=user.id,
    email=user.email,
    ip_address=request.client.host,
)
```

### Bad

```python
logging.info(f"User {user.email} logged in from {request.client.host}")
```

## Migration Guide

To migrate from standard logging to structured logging:

1. Replace `import logging` with `from aitbc import get_logger`
2. Replace `logging.getLogger(__name__)` with `get_logger(__name__)`
3. Replace f-strings with key-value pairs
4. Update log calls to use structured format

### Before

```python
import logging

logger = logging.getLogger(__name__)
logger.info(f"Processing request {request_id}")
```

### After

```python
from aitbc import get_logger

logger = get_logger(__name__)
logger.info("Processing request", request_id=request_id)
```

## Configuration

Log level can be configured via environment variable or settings:

```python
from .app_logging import configure_logging

configure_logging(level="INFO")  # or "DEBUG", "WARNING", "ERROR"
```

## Ruff Rules

The following ruff rules are enforced for logging:
- `G` - logging-string-format (enforce structured logging)
- `LOG` - logging best practices

Some rules are temporarily ignored during migration:
- `G001` - logging-string-format
- `G002` - logging-string-format

These will be enforced after migration is complete.
