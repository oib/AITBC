# Pre-commit Hooks & Multi-node Deployment - v0.4.22

**Release**: v0.4.22
**Date**: 2026-06-15
**Status**: ✅ Complete

## Overview

AITBC v0.4.22 implemented pre-commit hooks and fixed multi-node deployment configuration.

## Pre-commit Hooks Implementation

### 1. Installed pre-commit in venv

### 2. Updated .pre-commit-config.yaml with:
- pre-commit-hooks: Basic file checks (trailing whitespace, YAML, JSON, merge conflicts, etc.)
- Ruff: Linting with auto-fix (--unsafe-fixes) and formatting
- MyPy: Type checking on the 12 clean apps only
- Bandit: Security scanning (runs on pre-push only)

### 3. Created scripts/ci/mypy-precommit.sh for MyPy hook

### 4. Fixed issues found by hooks:
- Fixed executable permissions on 20+ non-executable files
- Fixed late import in persistent_service.py
- Auto-fixed 54 UP038 isinstance pattern issues
- Added noqa comments for intentional late imports

## Multi-node Deployment Fixes

### 1. Changed service bindings from 127.0.0.1 to 0.0.0.0 (all interfaces):
- marketplace: 127.0.0.1 → 0.0.0.0 (default)
- gpu: 127.0.0.1 → 0.0.0.0 (default)
- trading: 127.0.0.1 → 0.0.0.0 (default)
- governance: 127.0.0.1 → 0.0.0.0 (default)
- wallet: 127.0.0.1 → 0.0.0.0 (default)

### 2. Added environment variable support for bind configuration:
- MARKETPLACE_BIND_HOST/PORT
- GPU_BIND_HOST/PORT
- TRADING_BIND_HOST/PORT
- GOVERNANCE_BIND_HOST/PORT
- WALLET_BIND_HOST/PORT

## Environment Variable Standardization

### 1. Standardized naming convention: `{SERVICE}_BIND_HOST` and `{SERVICE}_BIND_PORT`

### 2. Updated services:
- Hermes: HERMES_BIND_HOST/PORT (backward compatible with BIND_HOST, HERMES_PORT)
- Agent Coordinator: AGENT_COORDINATOR_BIND_HOST/PORT (backward compatible with HOST, PORT)
- FFmpeg: FFMPEG_BIND_HOST/PORT (backward compatible with FFMPEG_PORT)
- Whisper: WHISPER_BIND_HOST/PORT (backward compatible with WHISPER_PORT)
- Transcoder: TRANSCODER_BIND_HOST/PORT (backward compatible with TRANSCODER_PORT)

### 3. Additional fixes:
- Fixed logger initialization order in coordinator-api/src/app/main.py
- Added missing import sys in tests/fixtures/blockchain.py
- Added noqa comments for intentional late imports in test files

## Results

- ✅ Pre-commit hooks implemented with Ruff, MyPy, and Bandit
- ✅ Multi-node deployment bind fixes applied
- ✅ Environment variable standardization completed

---

*Last Updated: 2026-06-15*
