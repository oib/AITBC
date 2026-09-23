# AITBC Setup - Security

**Last Updated**: 2026-06-30
**Version**: 1.0

## Service User Security

AITBC services run as the `aitbc` system user (created by `setup.sh`). Additional specialized service users are created for future security isolation but are not currently used by the service files.

### Service Users

| User | Purpose | Currently Used By |
|------|---------|----------|
| **aitbc** | Primary service user (all services run as this) | All 32+ systemd services |
| **aitbc-public** | Reserved for public exposure services | Not yet assigned |
| **aitbc-internal** | Reserved for internal services | Not yet assigned |
| **aitbc-blockchain** | Reserved for blockchain services | Not yet assigned |
| **aitbc-gpu** | Reserved for GPU service (needs video group) | Not yet assigned |
| **aitbc-wallet** | Reserved for wallet service (keystore access) | Not yet assigned |

### Security Benefits

- **Principle of least privilege**: Services run with minimal required permissions
- **Exposure-based grouping**: Clear security boundaries (public vs internal vs specialized)
- **Compromise containment**: Limited to exposure category
- **Reduced user count**: 1 active user for all services (specialized users ready for future isolation)

### User Configuration

All service users:

- Shell: `/bin/false` (no shell access)
- Group: `aitbc-services` (common group)
- Home directory: Created but not used

**Special Groups:**

- `aitbc-gpu`: Added to `video` group for GPU access
- `aitbc-public`: Added to `video` and `audio` groups for whisper

### Service Isolation Status

**Current state:** every app unit under `apps/*/` runs as `User=aitbc`
(verified across the fleet — only `aitbc-hermes-agent` uses a dedicated
`aitbc-hermes` user). The 11/26 isolation count below is a stale snapshot
from before the fleet-wide `User=aitbc` rollout.

For detailed service isolation configuration, see Service Isolation Documentation.

## Related Topics

- [Quick Start](./setup-quick-start.md) - Installation and profiles
- [Service Selection](./setup-service-selection.md) - Role-based service configuration
- [Subscription System](./setup-subscription.md) - Lease-based block synchronization
- [Configuration](./setup-configuration.md) - Runtime directories, secrets, and environment files
- [Reference](./setup-reference.md) - Common commands, troubleshooting, and links
