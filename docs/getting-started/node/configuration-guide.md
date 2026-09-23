# Configuration Guide

AITBC uses two main configuration files located in `/etc/aitbc/`:

## /etc/aitbc/blockchain.env

Contains blockchain-specific environment variables:

- Chain ID and network configuration
- RPC and P2P binding settings
- Database and Redis connections
- Block production settings
- Gossip and sync configuration

## /etc/aitbc/node.env

Contains node-specific environment variables:

- Node ID and island ID
- Node role (genesis/follower)
- P2P port configuration
- Node-specific settings

**Note**: AITBC does NOT use `/etc/aitbc/.env`. All configuration should be in `blockchain.env` and `node.env`.

## Configuration Examples

Pre-configured example files are available in `/opt/aitbc/examples/` for quick setup:

- **Examples README** - Complete guide to all configuration examples
- **[blockchain.env.open-island](../../examples/blockchain.env.open-island)** - Pre-configured for hub.example.net open island
- **[node.env.open-island](../../examples/node.env.open-island)** - Node-specific configuration for open island
- Per-app templates live under `apps/<app>/.env.example` (e.g.
  `apps/blockchain-node/.env.example`) — there is no root or
  `examples/*.env.example` template

## Quick Setup for Open Island

```bash
cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
```

## See Also

- [Blockchain Setup](blockchain-setup.md)
- [Agent Messaging](agent-messaging.md)
