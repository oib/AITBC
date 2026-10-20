# Deployment Documentation

This directory contains production deployment guides and procedures for the AITBC platform.

**Note:** For initial setup and onboarding, see [Getting Started](../getting-started/).

## Production Deployment Guides

- [Single Server](single-server.md) - Single server production deployment
- [Multi Server](multi-server.md) - Multi-server deployment
- [Staging Environment](STAGING.md) - Staging environment setup and management
- [Configuration](configuration.md) - Environment configuration
- [Script environment variables](script-environment.md) - the `AITBC_*` variables the operational scripts read
- [SSL/TLS Configuration](../security/ssl-tls-configuration.md) - SSL/TLS configuration
- [Health Checks](health-checks.md) - Service health monitoring
- [Deployment Troubleshooting](deployment-troubleshooting.md) - Common deployment issues

## Additional Deployment Documentation

- [Deployment Dependencies](DEPENDENCIES.md) - System-level dependencies for deployment
- [Service Users](SERVICE_USERS.md) - Service user management and unification
- [SMART_CONTRACT_DEPLOYMENT.md](SMART_CONTRACT_DEPLOYMENT.md) - Smart contract deployment procedures
- [bc-2 Environment Set](bc2-environment-set.md) - the `bc-2` chain environment-variable set (reset planning)
- [bc-2 Consumers](bc2-consumers.md) - the `bc-2` cut-day consumer table (reset planning)
- [bc-2 Reset Runbook](bc2-reset-runbook.md) - the `bc-2` reset-day plan (planning only; nothing authorized)
- [bc-2 Drain Checklist](bc2-drain-checklist.md) - old-chain items to settle or clear before the cut (reset planning)
- [bc-2 Host Inventory](bc2-host-inventory.md) - per-host unit/timer/store-file census the runbook's C1/C2 steps act on (reset planning)
- [bc-2 Alert Window](bc2-alert-window.md) - what monitoring does through the cut: procedural silence, expected noise, post-cut green checks (reset planning)

## See Also

- [Getting Started](../getting-started/) - Initial setup and onboarding
- [Prerequisites](../getting-started/installation/prerequisites.md) - System and software requirements
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration reference
- [Security Best Practices](../security/) - Security guidelines for deployment

- [Network Policy](NETWORK_POLICY.md) - Service exposure and binding policy
