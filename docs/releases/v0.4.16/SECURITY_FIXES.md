# Security Fixes - v0.4.16

**Release**: v0.4.16
**Date**: June 12, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.16 applies critical security fixes that were previously documented but not actually applied to the codebase.

## 1. Removed Hardcoded Secrets

- `cli/handlers/resource.py`: Replaced hardcoded `"aitbc-miner-token-secure"` with `os.getenv("MINER_API_KEY")`
- `apps/wallet/aitbc-wallet.service`: Removed hardcoded `WALLET_IMPORT_PASSWORD` from systemd unit; now sourced from `/etc/aitbc/blockchain-secrets.env`

## 2. Encrypted Wallet Private Keys at Rest

- `apps/wallet/simple_daemon.py`: All wallet creation paths now encrypt private keys using `WALLET_IMPORT_PASSWORD` via `aitbc.crypto.encrypt_private_key()`
- Added `_encrypt_if_password()` helper that encrypts when password is available, falls back to plaintext with warning
- Created `scripts/migrate_encrypt_wallets.py` to encrypt existing keystores in-place

## 3. Replaced Unsafe Pickle with JSON

- `apps/coordinator-api/src/app/services/secure_pickle.py`: Replaced `pickle.loads/dumps` with `json.loads/dumps`
- `apps/coordinator-api/src/app/services/fhe_service.py`: Mock FHE provider now serializes numpy arrays as JSON (numpy-safe via `tolist()`)
- Eliminates RCE vulnerability from untrusted data deserialization

## 4. Locked Down Wildcard CORS

- `apps/blockchain-node/src/aitbc_chain/config.py`: Added `cors_origins` setting sourced from `CORS_ORIGINS` env var
- `apps/blockchain-node/src/aitbc_chain/app.py`: Changed `allow_origins=["*"]` to `settings.cors_origins`, `allow_headers=["*"]` to `["Content-Type", "Authorization", "X-API-Key"]`

## 5. Added CI Workflow for Security Scanning

- `.github/workflows/ci.yml` (new): Runs `ruff`, `black`, `mypy`, `pytest --cov`, `bandit`, and `semgrep` on PRs and main branch
- All jobs start with `continue-on-error: true` for 2-week grace period

## 6. Fixed Python Version Inconsistency

- `apps/agent-coordinator/pyproject.toml`: Fixed `python_version = "3.9"` → `"3.13"`, corrected `pydantic_pydantic_plugin` → `pydantic.mypy`

## 7. Removed TLS Bypass and Unsafe Subprocess

- `cli/utils/secure_audit.py`: Changed `verify=False` to `verify=True` in audit log integrity checks
- `scripts/utils/setup_production.py`: Removed `shell=True` from subprocess calls
- `scripts/testing/qa-cycle.py`: Removed `shell=True` from subprocess calls
- `scripts/testing/scalability_validation.py`: Replaced shell pipelines with native Python (`/proc/stat`, `/proc/meminfo`, `shutil.disk_usage`)
- `scripts/training/stage5_expert_automation.sh`: Removed `shell=True` from embedded Python subprocess

---

*Last Updated: 2026-06-12*
