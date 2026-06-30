# AITBC Governance v0.4.12 Documentation

**Implementation Date:** June 7, 2026
**Status:** Complete
**Version:** v0.4.12

## Overview

AITBC v0.4.12 introduces comprehensive governance capabilities for the AITBC network, enabling decentralized decision-making through token-weighted voting, staking, and delegation mechanisms.

## Documentation Index

- [Architecture](01-ARCHITECTURE.md) - System architecture and components
- [Database Schema](02-DATABASE_SCHEMA.md) - Tables, indexes, and migrations
- [Smart Contracts](03-SMART_CONTRACTS.md) - AITBCGovernanceToken and AITBCVoting contracts
- [API Endpoints](04-API_ENDPOINTS.md) - REST API documentation
- [CLI Commands](05-CLI_COMMANDS.md) - Command-line interface reference
- [Database Migrations](06-MIGRATIONS.md) - Alembic migration guide
- [Testing](07-TESTING.md) - Testing procedures and results
- [Configuration](08-CONFIGURATION.md) - Environment variables and settings
- [Deployment](09-DEPLOYMENT.md) - Deployment and service management
- [Security](10-SECURITY.md) - Security considerations
- [Troubleshooting](11-TROUBLESHOOTING.md) - Common issues and solutions

## Quick Start

### Service Status
```bash
sudo systemctl status aitbc-governance
curl http://localhost:8105/health
```

### CLI Commands
```bash
aitbc governance --help
aitbc governance stake --address 0x123... --amount 1000 --lock-days 30
aitbc governance voting-power <address>
```

### Database Migrations
```bash
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic upgrade head
```

### Smart Contract Tests
```bash
cd /opt/aitbc/contracts/governance
forge test
```

## References

- Service README: `/opt/aitbc/apps/governance/README.md`
- Release Notes: `/opt/aitbc/docs/releases/README.md` - Current release documentation
- Smart Contracts: `/opt/aitbc/contracts/governance/src/`
- Tests: `/opt/aitbc/contracts/governance/test/`
