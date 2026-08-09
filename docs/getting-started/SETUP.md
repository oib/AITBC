# AITBC Setup Guide

**Last Updated:** 2026-06-30
**Version:** 2.0 (Split into topic-focused files)

Quick reference guide for AITBC setup and onboarding.

> **🟢 Service Status**: All core services are operational as of June 7, 2026. See [Service Status](../infrastructure/SYSTEMD_SERVICES.md#current-service-status) for details.

> **⚠️ v0.4.26 Update**: JWT authentication is now required. `setup.sh` automatically generates `JWT_SECRET` and `SECRET_KEY`. If upgrading from an earlier version, run `/opt/aitbc/scripts/utils/load-keystore-secrets.sh` after updating the credential files.

## Documentation Structure

This guide has been split into topic-focused files for easier navigation:

### Core Topics

- **[Quick Start](./setup-quick-start.md)** - 5-minute quick start, install profiles, and node profiles
- **[Service Selection](./setup-service-selection.md)** - Role-based service selection and backup service
- **[Subscription System](./setup-subscription.md)** - Lease-based subscription system and sync modes
- **[Configuration](./setup-configuration.md)** - Runtime directories, secrets, and per-service environment files
- **[Security](./setup-security.md)** - Service user security configuration
- **[Reference](./setup-reference.md)** - Essential links, common commands, and troubleshooting

## Quick Navigation

**For New Users:**
1. Start with [Quick Start](./setup-quick-start.md)
2. Review [Service Selection](./setup-service-selection.md) for your node type
3. Configure [Subscription System](./setup-subscription.md) if joining as follower

**For Configuration:**
1. Check [Configuration](./setup-configuration.md) for runtime directories
2. Review [Security](./setup-security.md) for service user setup
3. See [Reference](./setup-reference.md) for common commands

**For Troubleshooting:**
- See [Reference](./setup-reference.md#troubleshooting) for common issues and solutions

## Follower Node Quick Setup

For a follower node joining an open island (e.g. `hub.aitbc.bubuit.net`):

```bash
sudo /opt/aitbc/scripts/deployment/setup.sh \
  --open-island https://hub.aitbc.bubuit.net \
  --node-id <unique-node-id>
```

Use the hub **base URL** (`https://...`) without a trailing `/rpc` path — the sync code appends `/rpc/head` at runtime. To re-run setup on an existing install, add `--force`.

`setup.sh` now:
- Sets `DEFAULT_PEER_RPC_URL` to the hub for follower profiles.
- Creates missing `/etc/aitbc/<unit>.env` files required by `EnvironmentFile=/etc/aitbc/%N.env`.
- Installs the `filelock` package if the selected profile omits it.

See [setup-reference.md](./setup-reference.md) for troubleshooting.

---

**Note**: This file has been split into topic-focused files for easier navigation. See the [Documentation Structure](#documentation-structure) section above for links to the individual topic files.
