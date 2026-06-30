# AITBC Setup - Configuration

**Last Updated**: 2026-06-30
**Version**: 1.0

## Development Mode

```bash
cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8203
```

## Runtime Directories

```
/var/lib/aitbc/
├── keystore/     # Blockchain private keys
├── data/         # Database files
├── wallets/      # Wallet files (aitbc-wallet user)
├── whisper-cache/ # Whisper model cache (aitbc-public user)
└── logs/         # Application logs

/etc/aitbc/       # Configuration files
```

## Required Secrets

The following secrets are generated automatically by `setup.sh` and stored in `/etc/aitbc/credentials/` (mode 600). They are loaded at runtime into `/run/aitbc/secrets/.env` (tmpfs, cleared on reboot) by `load-keystore-secrets.sh`.

| Secret | Environment Variable | Used By | Description |
|--------|---------------------|---------|-------------|
| `api_hash_secret` | `API_KEY_HASH_SECRET` | API Gateway | Hash secret for API key validation |
| `jwt_secret` | `JWT_SECRET` | Coordinator API | JWT token signing/verification |
| `secret_key` | `SECRET_KEY` | Coordinator API | Application secret key |
| `keystore_password` | `KEYSTORE_PASSWORD` | Wallet service | Keystore encryption password |
| `proposer_id` | `proposer_id` | Blockchain node | Node proposer identity |

### Regenerating Secrets

If secrets are missing (e.g. after a fresh clone on an existing node):

```bash
# Regenerate all secrets
sudo /opt/aitbc/scripts/deployment/setup.sh

# Or regenerate individual secrets manually
python3 -c "import secrets; print(secrets.token_hex(32))" | sudo tee /etc/aitbc/credentials/jwt_secret
chmod 600 /etc/aitbc/credentials/jwt_secret
sudo /opt/aitbc/scripts/utils/load-keystore-secrets.sh
sudo systemctl restart aitbc-coordinator-api
```

## Per-Service Environment Files (%N.env)

Each systemd service uses `EnvironmentFile=/etc/aitbc/%N.env` to load service-specific configuration. The `%N` specifier expands to the **unit name without the `.service` suffix** (e.g., `aitbc-coordinator-api.service` → `/etc/aitbc/aitbc-coordinator-api.env`).

These files are created automatically by `setup_postgresql_databases.sh` and contain `DATABASE_URL` with credentials, `JWT_SECRET`, `REDIS_URL`, and other service-specific settings.

### File Naming Convention

| Service unit | `%N` expands to | Env file path |
|---|---|---|
| `aitbc-coordinator-api.service` | `aitbc-coordinator-api` | `/etc/aitbc/aitbc-coordinator-api.env` |
| `aitbc-governance.service` | `aitbc-governance` | `/etc/aitbc/aitbc-governance.env` |
| `aitbc-blockchain-p2p.service` | `aitbc-blockchain-p2p` | `/etc/aitbc/aitbc-blockchain-p2p.env` |
| `aitbc-exchange.service` | `aitbc-exchange` | `/etc/aitbc/aitbc-exchange.env` |

> **Important:** The file name must NOT include `.service` — `%N` strips the `.service` suffix. Naming a file `aitbc-coordinator-api.service.env` will cause systemd to fail with `Failed to load environment files: No such file or directory`.

### DATABASE_URL Format

The `DATABASE_URL` must include credentials. Without them, PostgreSQL rejects the connection with `fe_sendauth: no password supplied`.

```bash
# Correct (with credentials)
DATABASE_URL=postgresql://aitbc_user:aitbc_user_password@localhost:5432/aitbc_coordinator

# Wrong (no credentials — causes fe_sendauth error)
DATABASE_URL=postgresql://localhost:5432/aitbc_coordinator
```

### Regenerating Per-Service Env Files

If env files are missing or have incorrect `DATABASE_URL`:

```bash
# Regenerate all databases, users, and env files
sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh

# Or manually create a single env file
sudo tee /etc/aitbc/aitbc-coordinator-api.env << 'EOF'
JWT_SECRET=<your-jwt-secret>
API_KEY_HASH_SECRET=<your-api-key-hash-secret>
DATABASE_URL=postgresql://aitbc_user:<password>@localhost:5432/aitbc_coordinator
REDIS_URL=redis://localhost:6379/0
EOF
sudo systemctl restart aitbc-coordinator-api
```

### [Install] Section in Service Files

Each service file must include an `[Install]` section for `systemctl enable` to work:

```ini
[Install]
WantedBy=multi-user.target
```

Without this, `systemctl enable` fails with "no installation config" and the service won't auto-start on boot.

### Upgrading from v0.4.25 or Earlier

Earlier versions did not generate `JWT_SECRET` or `SECRET_KEY`. After upgrading:

```bash
# 1. Generate the new secrets
sudo /opt/aitbc/scripts/utils/load-keystore-secrets.sh

# 2. Verify they were added to the runtime env file
grep -E "JWT_SECRET|SECRET_KEY" /run/aitbc/secrets/.env

# 3. Restart the coordinator-api
sudo systemctl restart aitbc-coordinator-api
```

## Related Topics

- [Quick Start](./setup-quick-start.md) - Installation and profiles
- [Service Selection](./setup-service-selection.md) - Role-based service configuration
- [Subscription System](./setup-subscription.md) - Lease-based block synchronization
- [Security](./setup-security.md) - Service user security
- [Reference](./setup-reference.md) - Common commands, troubleshooting, and links
