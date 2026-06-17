# Runtime Error Fixes - v0.4.22

**Release**: v0.4.22
**Date**: 2026-06-15
**Status**: ✅ Complete

## Overview

AITBC v0.4.22 resolved critical runtime errors affecting coordinator-api, file permissions, and hermes-polling daemon.

## Issues Fixed

### 1. coordinator-api agent_performance endpoint syntax error
- Fixed duplicate `Depends()` in function signature
- Fixed parameter ordering (session before period_days)
- Resolved uvicorn startup failure with SyntaxError

### 2. api_keys.json permission denied
- Changed ownership from root:root to aitbc-internal:aitbc-services
- Changed permissions from 600 to 640
- Resolved agent-coordinator startup error

### 3. hermes-polling daemon transient connection errors
- Verified daemon recovery after initial startup
- Confirmed successful message forwarding to Hermes service
- No code changes needed - transient startup issue

## Results

- ✅ coordinator-api endpoint syntax and parameter ordering fixed
- ✅ File permissions fixed (api_keys.json ownership and permissions)
- ✅ hermes-polling daemon transient issue verified and documented
- ✅ Files changed: 2 files

---

*Last Updated: 2026-06-15*
