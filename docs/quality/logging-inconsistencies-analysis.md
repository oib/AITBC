# Logging Inconsistencies Analysis

## Current State

The codebase uses multiple logging approaches inconsistently across different modules:

### Logging Patterns in Use

1. **Custom AITBC Logging** (`aitbc.aitbc_logging`)
   - Used by: blockchain-event-bridge, CLI (legacy)
   - Pattern: `from aitbc.aitbc_logging import get_logger`
   - Files: ~10+ files

2. **App-Specific Logging** (agent-management)
   - Used by: agent-management app
   - Pattern: `from .core.logging import setup_logging, get_logger`
   - Files: 2+ files

3. **Stdlib Logging** (`logging`)
   - Used by: training_setup, examples, scripts
   - Pattern: `import logging`
   - Files: ~10+ files

4. **Rich Logging** (`rich.logging`)
   - Used by: CLI utils
   - Pattern: `from rich.logging import RichHandler`
   - Files: 1 file

5. **Structlog** (in dependencies)
   - Listed in pyproject.toml: `structlog = ">=25.1.0"`
   - Not consistently used across codebase
   - Files: 0 active usage found

## Inconsistency Issues

### Problems
1. **No single source of truth**: Different apps use different logging approaches
2. **Configuration fragmentation**: Each logging pattern requires separate configuration
3. **Maintenance burden**: Changes to logging behavior require updates in multiple places
4. **Inconsistent log formats**: Different loggers produce different output formats
5. **Testing complexity**: Mocking different logging patterns requires different approaches

### Impact
- Difficult to enforce consistent logging standards
- Hard to aggregate logs across services
- Inconsistent log levels and formats
- Increased cognitive load for developers

## Standardization Recommendation

### Proposed Approach: Structlog with AITBC Wrapper

**Rationale:**
- `structlog` is already in dependencies (`>=25.1.0`)
- Provides structured logging with JSON output for production
- Supports multiple output formats (console, JSON, file)
- Integrates well with modern observability stacks
- Can wrap stdlib logging for backward compatibility

### Implementation Plan

#### Phase 1: Create Standardized Logging Module
Create `aitbc/aitbc_logging.py` with structlog-based implementation:

```python
"""
Standardized logging for AITBC using structlog.
Provides consistent logging across all services.
"""

import structlog
from typing import Any
import logging
import sys

def setup_logging(
    level: int = logging.INFO,
    json_output: bool = False,
    service_name: str = "aitbc"
) -> None:
    """Configure structlog for the application."""
    
    # Configure structlog processors
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
    )

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger for the given module."""
    return structlog.get_logger(name)
```

#### Phase 2: Gradual Migration

**Priority Order:**
1. **High Priority**: blockchain-node, coordinator-api (core services)
2. **Medium Priority**: agent-management, marketplace-service
3. **Low Priority**: examples, scripts, stubs

**Migration Pattern:**
```python
# Before
import logging
logger = logging.getLogger(__name__)

# After
from aitbc.aitbc_logging import get_logger
logger = get_logger(__name__)
```

#### Phase 3: Configuration Standardization

**Environment Variables:**
- `AITBC_LOG_LEVEL`: Default log level (INFO, DEBUG, WARNING, ERROR)
- `AITBC_LOG_FORMAT`: Output format (json, console)
- `AITBC_SERVICE_NAME`: Service name for log aggregation

**Example Configuration:**
```python
import os
from aitbc.aitbc_logging import setup_logging

setup_logging(
    level=getattr(logging, os.getenv("AITBC_LOG_LEVEL", "INFO")),
    json_output=os.getenv("AITBC_LOG_FORMAT", "console") == "json",
    service_name=os.getenv("AITBC_SERVICE_NAME", "aitbc"),
)
```

## Migration Status

### Current State
- ✅ structlog in dependencies
- ⏸️ Custom logging modules exist (aitbc_logging, app-specific)
- ⏸️ Inconsistent usage across codebase
- ⏸️ No standardized configuration

### Recommended Next Steps
1. Update `aitbc/aitbc_logging.py` to use structlog
2. Create migration guide for developers
3. Migrate core services (blockchain-node, coordinator-api)
4. Update CI/CD to use standardized logging
5. Remove app-specific logging modules after migration

## Benefits of Standardization

1. **Consistency**: Single logging approach across all services
2. **Observability**: Structured logs for better log aggregation
3. **Flexibility**: Easy to switch between console and JSON output
4. **Performance**: Structlog is optimized for production use
5. **Maintainability**: Single module to maintain and update

## Risk Mitigation

1. **Backward Compatibility**: Keep existing logging during migration
2. **Gradual Rollout**: Migrate one service at a time
3. **Testing**: Verify log output after each migration
4. **Rollback Plan**: Can revert to old logging if issues arise
5. **Documentation**: Clear migration guide for developers

## Success Criteria

- [ ] All services use standardized logging
- [ ] Consistent log format across codebase
- [ ] Structlog configuration documented
- [ ] Migration guide created
- [ ] CI/CD uses standardized logging
- [ ] App-specific logging modules removed
