# Secret Rotation Log

**Last Updated:** 2026-06-19
**Version:** v0.5.1

This document tracks all secret rotations performed in the AITBC infrastructure.

## Rotation Log

| Date | Secret | Old Version | New Version | Performed By | Notes |
|------|--------|-------------|-------------|--------------|-------|
| | | | | | |
| | | | | | |
| | | | | | |

## Rolling Release Rotation Procedure

### Overview

AITBC uses a rolling release deployment model without a staging environment. Secret rotations are performed in production using a zero-downtime dual-secret overlap approach.

### Rotation Scripts

The following automated scripts are available for secret rotation:

1. **JWT_SECRET Rotation**: `scripts/ops/rotate_jwt_secret.sh`
   - Usage: `sudo ./scripts/ops/rotate_jwt_secret.sh <new_secret>`
   - Services affected: coordinator-api, blockchain-node, marketplace, exchange, gpu
   - Features: Automatic rollback, health checks, logging

2. **API_KEY_HASH_SECRET Rotation**: `scripts/ops/rotate_api_key_secret.sh`
   - Usage: `sudo ./scripts/ops/rotate_api_key_secret.sh <new_secret>`
   - Services affected: coordinator-api, blockchain-node, marketplace, exchange, gpu
   - Features: Automatic rollback, health checks, logging

### Rotation Process

The scripts implement a 6-phase zero-downtime rotation:

1. **Phase 1**: Add new secret alongside old secret (dual-secret overlap)
2. **Phase 2**: Rolling restart services one by one with dual-secret support
3. **Phase 3**: Verify all services are healthy with dual-secret support
4. **Phase 4**: Replace old secret with new secret
5. **Phase 5**: Final rolling restart with new secret only
6. **Phase 6**: Final verification and cleanup

### Safety Features

- **Automatic Rollback**: Scripts generate rollback files and auto-rollback on failure
- **Health Checks**: Each service is verified after restart before proceeding
- **Backup Files**: Original secrets are backed up before rotation
- **Logging**: Detailed logs are saved to `/var/log/aitbc/secret_rotation_*.log`
- **Rolling Restart**: Services are restarted one by one to maintain availability

### Pre-Rotation Checklist

Before running a secret rotation:

- [ ] Verify all services are healthy: `systemctl status aitbc-*`
- [ ] Generate a strong new secret (minimum 32 characters, alphanumeric + special chars)
- [ ] Ensure you have root access to run the rotation script
- [ ] Schedule the rotation during low-traffic periods
- [ ] Have monitoring ready to detect any issues
- [ ] Ensure team members are aware of the rotation

### Post-Rotation Verification

After running a secret rotation:

- [ ] Verify all services are healthy: `systemctl status aitbc-*`
- [ ] Check rotation logs: `cat /var/log/aitbc/secret_rotation_*.log`
- [ ] Verify no 401 errors in service logs
- [ ] Test API endpoints with new tokens
- [ ] Update this rotation log with the rotation details
- [ ] Remove backup files after 7 days (automated by scripts)

### Emergency Rollback

If a rotation fails or causes issues:

1. The script will automatically rollback on failure
2. Manual rollback: Execute the generated rollback script in `/tmp/`
3. Check logs: `cat /var/log/aitbc/secret_rotation_*.log`
4. Restore from backup: `cp /etc/aitbc/*.env.backup_* /etc/aitbc/`
5. Restart services: `systemctl restart aitbc-*`

## Rotation Guidelines

### When to Add an Entry

Add an entry to this log whenever:
- A secret is rotated following the procedures in SECRETS.md
- A secret is compromised and requires emergency rotation
- A service is migrated to use a new secret management system
- A secret is regenerated as part of security hardening

### Required Fields

- **Date**: Date of rotation (YYYY-MM-DD format)
- **Secret**: Name of the secret (e.g., JWT_SECRET, API_KEY_HASH_SECRET, KEYSTORE_PASSWORD)
- **Old Version**: Version identifier or hash of old secret (for audit trail)
- **New Version**: Version identifier or hash of new secret (for audit trail)
- **Performed By**: Person or team that performed the rotation
- **Notes**: Any relevant details (dual-secret window used, issues encountered, etc.)

### Version Naming Convention

Use semantic versioning for secret versions:
- v1: Initial secret
- v2: First rotation
- v3: Second rotation
- etc.

For emergency rotations, use:
- v2-emergency: Emergency rotation after compromise
- v2-rollback: Rollback to previous version

### Audit Trail

This log serves as an audit trail for:
- Compliance with secret rotation policies
- Security incident investigation
- Secret lifecycle management
- Change history for security reviews

## Related Documentation

- [Secret Management](SECRETS.md) - Complete secret management guide
- [Service Users](../deployment/SERVICE_USERS.md) - Service user management
- [Production Readiness](../../scripts/check-production-readiness.py) - Production readiness checks
