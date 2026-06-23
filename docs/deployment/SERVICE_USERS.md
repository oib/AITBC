# Service User Management

**Last Updated:** 2026-06-19
**Version:** v0.5.0

## Overview

AITBC services should run as non-root users for security. This document describes the unified user management approach for all AITBC services.

## Current User Distribution

Before unification, services use multiple different users:

| User | Services | Purpose |
|------|----------|---------|
| `root` | miner, agent-daemon, blockchain-sync, agent-management, blockchain-explorer | High-privilege services (needs GPU access, system resources) |
| `aitbc-internal` | coordinator-api, agent-coordinator, governance, marketplace, exchange, bridge-monitor, agent, multimodal, modality-optimization, learning, trading | Internal services |
| `aitbc-blockchain` | blockchain-node, blockchain-p2p, blockchain-rpc | Blockchain-specific services |
| `aitbc-gpu` | gpu | GPU service |
| `aitbc-wallet` | wallet | Wallet service |
| `aitbc-public` | edge, whisper, ffmpeg, blockchain-event-bridge, api-gateway, ai | Public-facing services |

## Unified User Approach

### Recommendation: Use `aitbc` User

For v0.5.0, we recommend standardizing on a single `aitbc` user for most services, with exceptions for services that require specific capabilities:

**Standard User: `aitbc`**
- Most services should run as `aitbc`
- Member of `aitbc` group
- Member of `aitbc-services` group
- Member of `video` and `render` groups (for GPU access)

**Exceptional Users:**
- `aitbc-blockchain` - Keep for blockchain-specific services (may need separate permissions)
- Services requiring `root` - Should be refactored to avoid root requirement

## Deployment Scripts

### 1. Create Unified User

```bash
sudo ./scripts/deployment/create_aitbc_user.sh
```

This script:
- Creates `aitbc` group (system group)
- Creates `aitbc` user (system user, no login shell)
- Adds user to supplementary groups (aitbc-services, video, render)
- Sets up proper directory permissions
- Creates required directories with correct ownership

### 2. Update Service Files

```bash
sudo ./scripts/deployment/unify_service_users.sh
```

This script:
- Finds all `.service` files in `/opt/aitbc/apps`
- Updates `User=` directive to `aitbc`
- Updates `Group=` directive to `aitbc`
- Skips services already using `aitbc`
- Reports summary of changes

### 3. Apply Changes

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Restart all AITBC services
sudo systemctl restart aitbc-*

# Verify services are running
sudo systemctl status aitbc-*
```

## User Permissions

### Directory Permissions

| Directory | Owner | Group | Permissions | Purpose |
|-----------|-------|-------|-------------|---------|
| `/var/lib/aitbc` | aitbc | aitbc | 755 | Application data |
| `/var/log/aitbc` | aitbc | aitbc | 755 | Application logs |
| `/run/aitbc` | aitbc | aitbc | 755 | Runtime data |
| `/etc/aitbc` | root | aitbc | 750 | Configuration (secrets) |

### Group Memberships

- `aitbc` - Primary group for aitbc user
- `aitbc-services` - Shared group for all AITBC services
- `video` - GPU access (for AI/GPU services)
- `render` - GPU access (for AI/GPU services)

## Service-Specific Considerations

### GPU Services

Services that need GPU access (miner, gpu, ai-engine) require:
- Membership in `video` group
- Membership in `render` group
- Access to `/dev/dri/*` devices

### Blockchain Services

Blockchain services may need:
- Network access for P2P communication
- File system access for blockchain data
- Potentially separate user for isolation

### Root-Required Services

Services currently running as root should be refactored:
- `miner` - Should run as `aitbc` with GPU group membership
- `agent-daemon` - Should run as `aitbc`
- `blockchain-sync` - Should run as `aitbc-blockchain`
- `agent-management` - Should run as `aitbc`
- `blockchain-explorer` - Should run as `aitbc`

## Verification

After user unification, verify:

```bash
# Check user exists
id aitbc

# Check group memberships
groups aitbc

# Check service user assignments
systemctl show aitbc-coordinator-api --property=User
systemctl show aitbc-blockchain-node --property=User

# Check service status
systemctl status aitbc-*

# Check logs for permission errors
journalctl -u aitbc-coordinator-api -n 50
```

## Log Rotation

### Log Rotation Configuration

AITBC services use systemd journal for logging by default, which is rotated by systemd-journald. For services that write to log files, logrotate is configured.

**Installation:**
```bash
# Install logrotate configuration
sudo cp /opt/aitbc/scripts/deployment/aitbc-logrotate.conf /etc/logrotate.d/aitbc

# Test logrotate configuration
sudo logrotate -d /etc/logrotate.d/aitbc

# Force logrotate to run immediately
sudo logrotate -f /etc/logrotate.d/aitbc
```

**Logrotate Configuration:**
- Main logs: Daily rotation, 14 days retention
- Audit logs: Daily rotation, 30 days retention
- Monitoring logs: Daily rotation, 7 days retention
- Compressed after rotation (delaycompress)
- Created with 0640 permissions (aitbc:aitbc)

**Systemd Journal Configuration:**
Configure journald retention in `/etc/systemd/journald.conf`:
```ini
[Journal]
SystemMaxUse=1G
SystemMaxFiles=100
MaxRetentionSec=1month
```

**LogsDirectory Directive:**
Some services use `LogsDirectory=aitbc` in systemd service files to ensure log directory creation with proper permissions:
- Directory: `/var/log/aitbc`
- Owner: aitbc:aitbc
- Permissions: 0755

**Verification:**
```bash
# Check logrotate configuration
cat /etc/logrotate.d/aitbc

# Check log directory permissions
ls -la /var/log/aitbc

# Check systemd journal size
journalctl --disk-usage

# Check logrotate status
sudo logrotate -d /etc/logrotate.d/aitbc
```

## Rollback

If issues occur after user unification:

```bash
# Restore previous service files from git
git checkout apps/*/*.service

# Reload systemd
sudo systemctl daemon-reload

# Restart services
sudo systemctl restart aitbc-*
```

## Security Considerations

### Benefits of Non-Root Users

- **Privilege Isolation** - Compromised service cannot affect system
- **Audit Trail** - Clear attribution of actions
- **Principle of Least Privilege** - Services only have needed permissions
- **Compliance** - Meets security best practices

### Risks of Root Users

- **System Compromise** - Compromised root service can affect entire system
- **Audit Issues** - Harder to track which service performed actions
- **Compliance Violations** - Many security standards prohibit root services

## Migration Strategy

### Phase 1: Create Unified User
- Run `create_aitbc_user.sh`
- Verify user and group creation
- Set up directory permissions

### Phase 2: Update Service Files
- Run `unify_service_users.sh`
- Review changes
- Commit updated service files

### Phase 3: Test in Staging
- Deploy to staging environment
- Restart services
- Verify all services start correctly
- Check logs for permission errors

### Phase 4: Deploy to Production
- Deploy during maintenance window
- Monitor service startup
- Have rollback plan ready

## Troubleshooting

### Permission Denied Errors

If services fail to start with permission errors:

```bash
# Check file ownership
ls -la /var/lib/aitbc
ls -la /var/log/aitbc
ls -la /etc/aitbc

# Fix ownership
sudo chown -R aitbc:aitbc /var/lib/aitbc
sudo chown -R aitbc:aitbc /var/log/aitbc
sudo chown root:aitbc /etc/aitbc
sudo chmod 750 /etc/aitbc
```

### GPU Access Issues

If GPU services fail to access GPU:

```bash
# Check group membership
groups aitbc

# Add to video/render groups
sudo usermod -aG video,render aitbc

# Verify device access
ls -la /dev/dri/*
```

### Service Won't Start

If service won't start after user change:

```bash
# Check service logs
journalctl -u <service-name> -n 100

# Check user can access required files
sudo -u aitbc ls -la /var/lib/aitbc
sudo -u aitbc ls -la /var/log/aitbc

# Test service startup manually
sudo -u aitbc /opt/aitbc/venv/bin/python -m <service-module>
```

## See Also

- [Systemd Hardening](../deployment/STAGING.md#systemd-hardening)
- [Secret Management](../operations/SECRETS.md)
- [Service Configuration](configuration.md)
