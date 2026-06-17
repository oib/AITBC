# Security Hardening - v0.4.23

**Release**: v0.4.23
**Date**: 2026-06-15
**Status**: ✅ Complete

## Overview

AITBC v0.4.23 removes hardcoded security values and makes them configurable via environment variables.

## Current Issues

### 1. Hardcoded Ports in Wrapper Scripts
- health-check.sh: hardcoded ports
- Multiple wrapper scripts: hardcoded ports
- **Solution**: Use aitbc.constants

### 2. CORS Origins in Coordinator-API
- Current: localhost only
- **Solution**: Make configurable per environment via AITBC_CORS_ORIGINS

### 3. Rate Limit Configs as Strings
- Current: String-based configuration
- **Solution**: Use structured config with validation

## Implementation Tasks

### 1. Audit Hardcoded Values
- Search for port numbers in scripts/
- Search for localhost references
- Document all findings

### 2. Create Constants Module

```python
# aitbc/constants.py (extend existing)
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8080"]
PRODUCTION_CORS_ORIGINS = ["https://aitbc.io"]
```

### 3. Update Configuration
- Add CORS_ORIGINS to hierarchical config
- Add environment variable support
- Add validation

### 4. Update Scripts
- Replace hardcoded ports with constants
- Replace localhost with configurable values
- Test in different environments

## Results

- ✅ **Security**: Hardcoded values removed, configurable
- ✅ **10 wrapper scripts**: Ports configurable via env vars

## Estimated Effort

- **Time**: 4-6 hours
- **Complexity**: Low (straightforward replacements)
- **Risk**: Low (configuration changes)

---

*Last Updated: 2026-06-16*
