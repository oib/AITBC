# Service Wrappers Guide

## Overview

Service wrappers are Python scripts that launch AITBC services with proper path configuration and environment setup. All wrappers now use the `AITBC_HOME` environment variable for path configuration instead of hardcoded `/opt/aitbc` paths.

## Standard Pattern

All service wrappers should follow this pattern:

```python
#!/usr/bin/env python3
"""<service-name> service wrapper"""

import os
import sys
from pathlib import Path

# Derive paths from environment variable with sensible default
AITBC_HOME = Path(os.environ.get("AITBC_HOME", "/opt/aitbc"))
REPO_DIR = AITBC_HOME
SERVICE_DIR = AITBC_HOME / "apps/<service-name>/src"

# Add to Python path
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))

# Import AITBC utilities
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

# Configure logging
configure_logging(
    level="INFO",
    service_name="<service-name>",
    to_file=True,
)

logger = get_logger(__name__)
logger.info("Starting <service-name> service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "<service_module>.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")

# Ensure PYTHONPATH is set for the child process
env = os.environ.copy()
env["PYTHONPATH"] = f"{str(REPO_DIR)}:{str(SERVICE_DIR)}"

os.execvpe(exec_cmd[0], exec_cmd, env)
```

## Environment Variables

### AITBC_HOME
- **Purpose**: Root directory of the AITBC repository
- **Default**: `/opt/aitbc`
- **Usage**: Override for development or alternative installations
- **Example**: `export AITBC_HOME=/home/user/aitbc`

## Service-Specific Paths

Different services may require additional paths:

### Coordinator API
```python
SDK_DIR = AITBC_HOME / "packages/py/aitbc-sdk/src"
CRYPTO_DIR = AITBC_HOME / "packages/py/aitbc-crypto/src"
sys.path.insert(0, str(SDK_DIR))
sys.path.insert(0, str(CRYPTO_DIR))
```

### Simple Services
```python
# Only REPO_DIR and SERVICE_DIR needed
SERVICE_DIR = AITBC_HOME / "apps/<service>/src"
```

## Wrapper Locations

Wrappers are located in:
- `apps/<service-name>/<service-name>-wrapper.py` - App-specific wrappers
- `scripts/services/<service-name>-wrapper.py` - Centralized service wrappers
- `scripts/monitoring/<service-name>-wrapper.py` - Monitoring service wrappers

## Systemd Integration

When using systemd, set the environment variable in the service file:

```ini
[Service]
Environment="AITBC_HOME=/opt/aitbc"
ExecStart=/opt/aitbc/apps/<service>/<service>-wrapper.py
```

## Development Setup

For local development, override the default:

```bash
export AITBC_HOME=/path/to/your/aitbc/repo
./apps/<service>/<service>-wrapper.py
```

## Migration Notes

- **Old pattern**: Hardcoded `REPO_DIR = Path("/opt/aitbc")`
- **New pattern**: `AITBC_HOME = Path(os.environ.get("AITBC_HOME", "/opt/aitbc"))`
- **Benefit**: Flexible deployment without code changes

## Troubleshooting

### Import Errors
If you see import errors:
1. Check that `AITBC_HOME` is set correctly
2. Verify the service directory structure
3. Ensure the package is installed: `pip install -e .`

### Path Issues
If paths are incorrect:
1. Check the wrapper file follows the standard pattern
2. Verify `AITBC_HOME` environment variable
3. Check systemd service file environment settings

## Maintenance

When adding new services:
1. Copy the standard wrapper pattern
2. Update service-specific paths
3. Test with `AITBC_HOME` override
4. Document any special requirements

---

*Last updated: 2026-06-18*
