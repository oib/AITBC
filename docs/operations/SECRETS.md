# AITBC Secret Management Runbook

**Version**: v0.5.0
**Last Updated**: 2026-06-19
**Status**: Fixes applied — all critical/high/medium/low issues resolved

---

## Overview

This document catalogs all secrets and sensitive configuration in the AITBC monorepo, identifies leakage risks, and provides a migration plan toward secure secret management.

---

## Secret Audit Findings

### 1. CRITICAL: Plaintext Passwords in Systemd Service Files

| File | Issue | Risk | Status |
|------|-------|------|--------|
| `apps/blockchain-node/aitbc-blockchain-p2p.service:14` | `Environment=MEMPOOL_DB_URL=...aitbc_mempool_password...` | Password visible in `systemctl show`, process list, and Git history | **✅ Fixed** |
| `apps/governance/aitbc-governance.service:17` | `Environment="DB_PASS=aitbc_governance_pass"` | Password visible in `systemctl show`, process list, and Git history | **✅ Fixed** |

**Fix applied**: Removed `Environment=` lines with secrets. Added `EnvironmentFile=/etc/aitbc/%N.env` with comment explaining secrets must be created at deploy time. Non-secret config (DB_TYPE, DB_HOST, etc.) kept as `Environment=`.

---

### 2. HIGH: Hardcoded Default Passwords in Python Source

| File | Issue | Risk | Status |
|------|-------|------|--------|
| `aitbc/training_setup/cli.py:124` | `default="training123"` | Weak default password in CLI tool | **✅ Fixed** |
| `aitbc/training_setup/blockchain.py:111` | `password: str = "training123"` | Default password for genesis wallet creation | **✅ Fixed** |
| `aitbc/training_setup/environment.py:150` | `password: str = "training123"` | Default password for training wallet setup | **✅ Fixed** |
| `apps/agent-coordinator/src/app/routers/auth.py:36` | `"admin": ... or "admin123"` | Fallback to hardcoded `admin123` | **✅ Fixed** |
| `apps/agent-coordinator/src/app/routers/auth.py:37` | `"operator": ... or "operator123"` | Fallback to hardcoded `operator123` | **✅ Fixed** |
| `apps/agent-coordinator/src/app/routers/auth.py:38` | `"user": ... or "user123"` | Fallback to hardcoded `user123` | **✅ Fixed** |

**Fix applied**:
- `training_setup/cli.py`: Removed default, added `prompt=True, hide_input=True` for interactive password entry
- `training_setup/blockchain.py` & `environment.py`: Removed default `="training123"`, now raises `ValueError` if password is None
- `agent-coordinator/auth.py`: Removed all hardcoded fallbacks. Now requires `ADMIN_PASSWORD` env var; returns 500 if not configured. `OPERATOR_PASSWORD` and `USER_PASSWORD` also read from env without fallbacks.

---

### 3. MEDIUM: Default Passwords in Database Connection Strings

| File | Issue | Risk | Status |
|------|-------|------|--------|
| `apps/ai-engine/examples/src/aitbc_ai/storage.py:11` | Default password `password` in connection string | Default used if env var not set | **✅ Fixed** |
| `apps/coordinator-api/migrations/003_data_migration.py:197` | Default password `aitbc` in migration script | Default used if --database-url not provided | **✅ Fixed** |

**Fix applied**:
- `storage.py`: Removed default connection string. Now raises `ValueError("AI_SERVICE_DATABASE_URL environment variable must be set")` if missing.
- `003_data_migration.py`: Changed `--database-url` from `default=` to `required=True`.

---

### 4. LOW: Scripts Printing Secrets to stdout

| File | Issue | Risk | Status |
|------|-------|------|--------|
| `apps/blockchain-node/scripts/create_genesis_wallet.py:91-92` | `print(f"Private key: ...")` `print(f"Password: ...")` | Secrets logged to stdout/stderr, captured by systemd journal or CI logs | **✅ Fixed** |

**Fix applied**: Removed `print()` statements for private key and password. Script now only prints the address, public key, file paths, and a security warning. Secrets are already written to files (keystore_path and password_path with mode 0600).

**Additional fix**: Also removed secret printing from `apps/blockchain-node/scripts/unified_genesis.py` (lines 269-270, 319) which was printing private key and password values.

---

### 5. GOOD PRACTICES (Maintain)

| Practice | Where | Status |
|----------|-------|--------|
| Secrets via `EnvironmentFile=/run/aitbc/secrets/.env` | `aitbc-blockchain-node.service`, `aitbc-coordinator-api.service` | ✅ Good |
| Only `.env.example` files committed | Entire repo | ✅ Good |
| `dev/validator_keys.json` template + generation script | `dev/validator_keys.json.template`, `dev/generate_validator_keys.py` | ✅ Good |
| No real `.env` files in Git | Entire repo | ✅ Good |
| Pydantic secret validation in config | `aitbc/config/hierarchical_config.py` | ✅ Good |

---

## Secret Inventory by Category

### Database Credentials

| Service | Current Location | Secret Present? |
|---------|-----------------|-----------------|
| Blockchain P2P | `aitbc-blockchain-p2p.service:14` | ❌ Plaintext in service file |
| Governance | `aitbc-governance.service:17` | ❌ Plaintext in service file |
| AI Engine (example) | `apps/ai-engine/examples/src/aitbc_ai/storage.py:11` | ❌ Default in code |
| Coordinator migrations | `003_data_migration.py:197` | ❌ Default in code |

### JWT / API Keys

| Service | Current Location | Secret Present? |
|---------|-----------------|-----------------|
| Agent Coordinator auth | `apps/agent-coordinator/src/app/routers/auth.py:36` | ❌ Fallback defaults |
| Coordinator API | `EnvironmentFile=/run/aitbc/secrets/.env` | ✅ Good (in secrets file) |
| Edge API | `EnvironmentFile=/etc/aitbc/secrets/jwt_secret` | ✅ Good (in secrets file) |

### Validator / Blockchain Keys

| Service | Current Location | Secret Present? |
|---------|-----------------|-----------------|
| Dev validator keys | `dev/validator_keys.json.template` | ✅ Good (template + generator) |
| Genesis wallet | `scripts/create_genesis_wallet.py` | ⚠️ Printed to stdout |

---

## Migration Plan

### Phase 1: Remove Plaintext Secrets from Service Files (P0)

**Files to fix:**
1. `apps/blockchain-node/aitbc-blockchain-p2p.service`
2. `apps/governance/aitbc-governance.service`

**Steps:**
```bash
# 1. Create secret env files on target systems (NOT in Git)
sudo mkdir -p /etc/aitbc/secrets
sudo chmod 700 /etc/aitbc/secrets

# 2. Move secrets into per-service env files
echo "MEMPOOL_DB_URL=postgresql+psycopg://aitbc_mempool:REAL_PASSWORD@localhost:5432/aitbc_mempool" | sudo tee /etc/aitbc/aitbc-blockchain-p2p.env
echo "DB_PASS=REAL_PASSWORD" | sudo tee /etc/aitbc/aitbc-governance.env
sudo chmod 600 /etc/aitbc/aitbc-blockchain-p2p.env /etc/aitbc/aitbc-governance.env

# 3. Update service files to use EnvironmentFile=/etc/aitbc/%N.env
# 4. Remove Environment= lines containing secrets
# 5. Reload systemd
```

**Verification:**
```bash
# Confirm no secrets in service files
grep -rn "password\|_pass\|secret" --include="*.service" apps/ scripts/
# Should return zero results (except for benign patterns like "password_path")
```

---

### Phase 2: Remove Hardcoded Defaults from Python Code (P1)

**Files to fix:**
1. `aitbc/training_setup/cli.py:124` — remove `default="training123"`
2. `aitbc/training_setup/blockchain.py:111` — remove default password
3. `aitbc/training_setup/environment.py:150` — remove default password
4. `apps/agent-coordinator/src/app/routers/auth.py:36-38` — remove fallback defaults

**Pattern for each:**
```python
# BEFORE (INSECURE)
password: str = "training123"

# AFTER (SECURE)
import os
password = os.getenv("TRAINING_WALLET_PASSWORD")
if not password:
    raise ValueError("TRAINING_WALLET_PASSWORD must be set")
```

For agent-coordinator auth:
```python
# BEFORE (INSECURE)
"admin": os.getenv("TEST_ADMIN_PASSWORD") or os.getenv("DEMO_ADMIN_PASSWORD") or "admin123",

# AFTER (SECURE)
password = os.getenv("ADMIN_PASSWORD")
if not password:
    raise HTTPException(status_code=500, detail="ADMIN_PASSWORD not configured")
```

---

### Phase 3: Remove Default Passwords from Database URLs (P1)

**Files to fix:**
1. `apps/ai-engine/examples/src/aitbc_ai/storage.py:11`
2. `apps/coordinator-api/migrations/003_data_migration.py:197`

**Pattern:**
```python
# BEFORE (INSECURE)
DATABASE_URL = os.getenv("AI_SERVICE_DATABASE_URL", "postgresql+asyncpg://aitbc_ai:password@localhost:5432/aitbc_ai")

# AFTER (SECURE)
DATABASE_URL = os.getenv("AI_SERVICE_DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("AI_SERVICE_DATABASE_URL must be set")
```

---

### Phase 4: Scripts Should Write to Files, Not stdout (P2)

**Files to fix:**
1. `apps/blockchain-node/scripts/create_genesis_wallet.py:91-92`
2. `apps/blockchain-node/scripts/keystore.py:105-134`

**Pattern:**
```python
# BEFORE (INSECURE)
print(f"Private key: {private_key_bytes.hex()}")
print(f"Password: {password}")

# AFTER (SECURE)
import stat
secret_file = Path("/run/aitbc/secrets/genesis_wallet.key")
secret_file.write_text(private_key_bytes.hex())
secret_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
print(f"Private key written to: {secret_file}")
```

---

### Phase 5: Standardize on `/etc/aitbc/%N.env` Pattern (P2)

**Goal**: All services use `EnvironmentFile=/etc/aitbc/%N.env` for secrets.

**Current status:**
- ✅ `aitbc-blockchain-node.service` uses `/run/aitbc/secrets/.env` (good but not standard)
- ✅ `aitbc-coordinator-api.service` uses `/run/aitbc/secrets/.env` (good but not standard)
- ✅ `aitbc-edge.service` uses `/etc/aitbc/secrets/jwt_secret` (good)
- 🔴 Most services use `/etc/aitbc/blockchain.env` and `/etc/aitbc/node.env` (shared, not per-service)

**Migration:**
```bash
# Create per-service env files
for service in aitbc-coordinator-api aitbc-blockchain-node aitbc-agent-coordinator aitbc-marketplace; do
    sudo touch /etc/aitbc/${service}.env
    sudo chmod 600 /etc/aitbc/${service}.env
done

# Update service files to use:
# EnvironmentFile=/etc/aitbc/%N.env
# Remove EnvironmentFile=/etc/aitbc/blockchain.env (shared)
```

---

## Secret Rotation Policy (v0.5.0+)

### Principles
1. **No secret lives forever**: All secrets must be rotatable without downtime.
2. **No plaintext in Git**: Secrets must never be committed.
3. **No shared secrets**: Each service gets its own credentials.
4. **Audit trail**: All secret access is logged.
5. **Zero downtime**: Use dual-secret overlap window for in-memory secrets.

### Rotation Schedule

| Secret Type | Rotation Frequency | Method |
|-------------|-------------------|--------|
| Database passwords | 90 days | Update `/etc/aitbc/%N.env`, restart service |
| JWT signing keys | 90 days | Update `/run/aitbc/secrets/.env`, dual-secret window |
| API keys | 60 days | Revoke old, generate new, update config |
| Validator keys | On compromise or 365 days | Manual process, requires chain coordination |
| TLS certificates | Before expiry | Automated via cert-manager or cron |

### Detailed Rotation Procedures

#### JWT_SECRET Rotation

**Impact**: Affects coordinator-api authentication tokens.

**Prerequisites:**
- Access to `/run/aitbc/secrets/.env` or `/etc/aitbc/coordinator-api.env`
- Service restart capability
- Token expiration time knowledge (default: 24-48 hours)

**Procedure:**
```bash
# 1. Generate new JWT secret
NEW_JWT_SECRET=$(openssl rand -hex 32)
echo "New JWT_SECRET: $NEW_JWT_SECRET"

# 2. Backup current secret
cp /run/aitbc/secrets/.env /run/aitbc/secrets/.env.backup

# 3. Add new secret with different variable name (dual-secret window)
echo "JWT_SECRET_NEW=$NEW_JWT_SECRET" >> /run/aitbc/secrets/.env

# 4. Reload service configuration
systemctl reload aitbc-coordinator-api

# 5. Wait for old tokens to expire (24-48 hours)
echo "Wait for old tokens to expire (24-48 hours)"

# 6. Replace old secret with new secret
sed -i 's/^JWT_SECRET=.*/JWT_SECRET='"$NEW_JWT_SECRET"'/' /run/aitbc/secrets/.env
sed -i '/^JWT_SECRET_NEW=/d' /run/aitbc/secrets/.env

# 7. Reload service again
systemctl reload aitbc-coordinator-api

# 8. Verify service is healthy
curl http://localhost:8203/health

# 9. Remove backup
rm /run/aitbc/secrets/.env.backup
```

**Rollback:**
```bash
# If issues occur, restore backup
cp /run/aitbc/secrets/.env.backup /run/aitbc/secrets/.env
systemctl reload aitbc-coordinator-api
```

#### API_KEY_HASH_SECRET Rotation

**Impact**: Affects API key authentication and hashing.

**Prerequisites:**
- Access to `/run/aitbc/secrets/.env` or `/etc/aitbc/coordinator-api.env`
- Service restart capability
- Knowledge of API key expiration times

**Procedure:**
```bash
# 1. Generate new API key hash secret
NEW_API_KEY_SECRET=$(openssl rand -hex 32)
echo "New API_KEY_HASH_SECRET: $NEW_API_KEY_SECRET"

# 2. Backup current secret
cp /run/aitbc/secrets/.env /run/aitbc/secrets/.env.backup

# 3. Add new secret with different variable name (dual-secret window)
echo "API_KEY_HASH_SECRET_NEW=$NEW_API_KEY_SECRET" >> /run/aitbc/secrets/.env

# 4. Reload service configuration
systemctl reload aitbc-coordinator-api

# 5. Regenerate API keys for all clients
# (This should be done via API endpoint or admin interface)

# 6. Wait for old API keys to expire (based on your policy)
echo "Wait for old API keys to expire"

# 7. Replace old secret with new secret
sed -i 's/^API_KEY_HASH_SECRET=.*/API_KEY_HASH_SECRET='"$NEW_API_KEY_SECRET"'/' /run/aitbc/secrets/.env
sed -i '/^API_KEY_HASH_SECRET_NEW=/d' /run/aitbc/secrets/.env

# 8. Reload service again
systemctl reload aitbc-coordinator-api

# 9. Verify service is healthy
curl http://localhost:8203/health

# 10. Remove backup
rm /run/aitbc/secrets/.env.backup
```

**Rollback:**
```bash
# If issues occur, restore backup
cp /run/aitbc/secrets/.env.backup /run/aitbc/secrets/.env
systemctl reload aitbc-coordinator-api
```

#### KEYSTORE_PASSWORD Rotation

**Impact**: Affects blockchain node keystore access for block signing.

**Prerequisites:**
- Access to keystore password file (typically `/run/aitbc/secrets/keystore_password` or `/etc/aitbc/%N.env`)
- Access to keystore files
- Blockchain node restart capability
- Backup of keystore files

**Procedure:**
```bash
# 1. Generate new keystore password
NEW_KEYSTORE_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
echo "New KEYSTORE_PASSWORD: $NEW_KEYSTORE_PASSWORD"

# 2. Backup current keystore files
BACKUP_DIR="/var/backups/aitbc/keystore_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r /var/lib/aitbc/blockchain/keystore/* "$BACKUP_DIR/"

# 3. Update keystore password file
echo "$NEW_KEYSTORE_PASSWORD" > /run/aitbc/secrets/keystore_password
chmod 600 /run/aitbc/secrets/keystore_password

# 4. For each keystore file, re-encrypt with new password
# (This requires running the re-encryption script)
python /opt/aitbc/apps/blockchain-node/scripts/reencrypt_keystore.py \
    --keystore-dir /var/lib/aitbc/blockchain/keystore \
    --old-password "$OLD_KEYSTORE_PASSWORD" \
    --new-password "$NEW_KEYSTORE_PASSWORD"

# 5. Restart blockchain node
systemctl restart aitbc-blockchain-node

# 6. Verify node is healthy
curl http://localhost:8202/health

# 7. Wait for node to sync and validate blocks
# Monitor logs: journalctl -u aitbc-blockchain-node -f

# 8. After validation, remove old backup
rm -rf "$BACKUP_DIR"
```

**Rollback:**
```bash
# If issues occur, restore keystore files
systemctl stop aitbc-blockchain-node
cp -r "$BACKUP_DIR"/* /var/lib/aitbc/blockchain/keystore/
systemctl start aitbc-blockchain-node
```

### Zero-Downtime Rotation Best Practices

1. **Dual-Secret Window**: Use temporary variable names (e.g., `JWT_SECRET_NEW`) to allow both old and new secrets to work during rotation
2. **Grace Period**: Wait for old secrets to expire before removing them (typically 24-48 hours for JWT tokens)
3. **Backup Always**: Always backup secrets before rotation
4. **Test in Staging**: Test rotation procedures in staging environment first
5. **Monitor Closely**: Watch logs for authentication errors during rotation
6. **Rollback Ready**: Have rollback procedure documented and tested
7. **Document Changes**: Update rotation log with date and new secret versions

### Rotation Tracking

Document all rotations in `docs/operations/SECRET_ROTATION_LOG.md`:
```markdown
| Date | Secret | Old Version | New Version | Performed By | Notes |
|------|--------|-------------|-------------|--------------|-------|
| 2026-06-19 | JWT_SECRET | v1 | v2 | DevOps | Dual-secret window used |
```

### Rotation Procedure
1. Generate new secret
2. Update `/etc/aitbc/%N.env` on target host
3. `sudo systemctl daemon-reload`
4. `sudo systemctl restart <service>`
5. Verify service health
6. Revoke old secret (for API keys, database passwords)

---

## Production Readiness Checklist

Before deploying to production, verify:

- [ ] Zero `Environment=` directives containing secrets in `.service` files
- [ ] Zero `EnvironmentFile=` directives pointing to committed files
- [ ] All secrets in `/etc/aitbc/` or `/run/aitbc/secrets/` with mode `0600`
- [ ] No hardcoded default passwords in Python code
- [ ] No default passwords in database connection strings
- [ ] Scripts write secrets to files, not stdout
- [ ] `.env` files in `.gitignore`
- [ ] `detect-secrets` CI hook passes
- [ ] `bandit` security scanner passes (B105: hardcoded_password_string)

---

## Tools

### Security Scanning
```bash
# Run bandit for hardcoded passwords
bandit -r aitbc/ apps/ cli/ -f json -o bandit-report.json

# Run detect-secrets for committed secrets
detect-secrets scan --baseline .secrets.baseline

# Check for plaintext in service files
grep -rn "password\|_pass\|secret_key\|api_key" --include="*.service" apps/ scripts/
```

### Verification Script
```bash
#!/usr/bin/env bash
# scripts/check-production-readiness.sh

errors=0

# Check service files for secrets
echo "Checking service files for plaintext secrets..."
if grep -rn "password\|_pass\|secret" --include="*.service" apps/ scripts/ 2>/dev/null | grep -q "Environment="; then
    echo "  FAIL: Secrets found in service files"
    errors=$((errors + 1))
else
    echo "  PASS: No plaintext secrets in service files"
fi

# Check Python code for hardcoded defaults
echo "Checking Python code for hardcoded passwords..."
if grep -rn '="training123"\|="admin123"\|="password"' --include="*.py" aitbc/ apps/ cli/ 2>/dev/null | grep -q "="; then
    echo "  FAIL: Hardcoded default passwords found"
    errors=$((errors + 1))
else
    echo "  PASS: No hardcoded default passwords"
fi

# Check .gitignore for .env
echo "Checking .gitignore for .env files..."
if ! grep -q "\.env" .gitignore 2>/dev/null; then
    echo "  FAIL: .env not in .gitignore"
    errors=$((errors + 1))
else
    echo "  PASS: .env files ignored"
fi

if [ $errors -gt 0 ]; then
    echo ""
    echo "$errors check(s) failed. Fix before production deployment."
    exit 1
fi

echo ""
echo "All secret checks passed."
```

---

## Appendix: Secret Locations Map

```
/etc/aitbc/
├── %N.env                          # Per-service secrets (mode 0600)
├── secrets/
│   └── jwt_secret                  # JWT signing key (mode 0600)
├── blockchain.env                  # Shared blockchain config (no secrets)
└── node.env                        # Shared node config (no secrets)

/run/aitbc/secrets/
└── .env                            # Runtime secrets (tmpfs, mode 0600)

/var/lib/aitbc/
└── keystore/                       # Blockchain keys (mode 0700)

apps/*/                             # Source code (NO secrets committed)
scripts/                            # Scripts (NO secrets in code)
```

---

*This is a living document. Update as secrets are migrated and new services are added.*
