# Secret Rotation Log

**Last Updated:** 2026-06-19
**Version:** v0.5.0

This document tracks all secret rotations performed in the AITBC infrastructure.

## Rotation Log

| Date | Secret | Old Version | New Version | Performed By | Notes |
|------|--------|-------------|-------------|--------------|-------|
| 2026-06-19 | JWT_SECRET | v1 | v2 | DevOps | Initial rotation with dual-secret window |
| | | | | | |
| | | | | | |

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
