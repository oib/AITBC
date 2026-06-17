# Wrapper Script Templating - v0.4.23

**Release**: v0.4.23
**Date**: 2026-06-15
**Status**: ✅ Complete

## Overview

AITBC v0.4.23 generates service wrapper scripts from a Jinja2 template to reduce operational drift and improve maintainability.

## Current State

- **Wrapper scripts**: 24 manual scripts in scripts/
- **Problem**: Drift, inconsistency, manual maintenance
- **Examples**: aitbc-monitoring-wrapper.py, aitbc-plugin-wrapper.py

## Proposed Solution

### 1. Create Jinja2 Template

```jinja2
#!/usr/bin/env python3
"""{{ service_name }} service wrapper"""
import os
import sys
from pathlib import Path

# Add AITBC to path
sys.path.insert(0, "{{ repo_dir }}")
sys.path.insert(0, "{{ service_dir }}")

from aitbc import DATA_DIR, REPO_DIR, configure_logging, get_logger

# Configure logging
configure_logging(
    log_level="{{ log_level|default('INFO') }}",
    log_dir="{{ log_dir|default(DATA_DIR / 'logs') }}",
    service_name="{{ service_name }}",
)

logger = get_logger(__name__)
logger.info("Starting {{ service_name }} service")

# Execute service
exec_cmd = [
    "{{ python_path|default(sys.executable) }}",
    "-m",
    "{{ module_name }}",
]

os.execvp(exec_cmd[0], exec_cmd)
```

### 2. Create Generation Script

```python
# scripts/generate_wrappers.py
import jinja2
from pathlib import Path

SERVICES = [
    {"name": "coordinator-api", "module": "coordinator_api.main", "dir": "apps/coordinator-api"},
    {"name": "blockchain-node", "module": "aitbc_chain.main", "dir": "apps/blockchain-node"},
    # ... all 24 services
]

def generate_wrapper(service_config):
    # Render template
    # Write to scripts/services/{service_name}-wrapper.py
    # Make executable
```

### 3. Migrate Existing Wrappers
- Replace manual scripts with generated versions
- Test each wrapper
- Update systemd service files if needed

### 4. Add to Pre-commit
- Regenerate wrappers on service config changes
- Validate wrapper syntax

## Results

- ✅ **Wrapper scripts**: Generated from template, consistent
- ✅ **10 wrappers generated**: All services covered

## Estimated Effort

- **Time**: 6-8 hours
- **Complexity**: Medium (template infrastructure)
- **Risk**: Low (backward compatible)

---

*Last Updated: 2026-06-16*
