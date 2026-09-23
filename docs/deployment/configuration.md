# Deployment Configuration

This guide covers environment variables and configuration files for AITBC deployment.

## Environment Variables

Units load `/etc/aitbc/<unit>.env` — one file per systemd unit (e.g.
`aitbc-blockchain-node.env`, `aitbc-coordinator-api.env`,
`aitbc-marketplace.env`), plus shared `blockchain.env`,
`blockchain-secrets.env`, and `node.env`. The block below is a simplified
illustration — the variable names shown there (`BLOCKCHAIN_NETWORK_ID`,
`BLOCKCHAIN_GENESIS_BLOCK_HASH`, `COORDINATOR_DATABASE_URL`,
`COORDINATOR_REDIS_URL`, `COORDINATOR_JWT_SECRET`, `MARKETPLACE_REDIS_URL`,
`MARKETPLACE_API_KEY`) are **not** read by any service.

Real names in use (verified against the unit files and Settings classes):

```bash
# /etc/aitbc/blockchain.env  (shared by blockchain units)
CHAIN_ID=ait-hub.aitbc.bubuit.net
SYNC_CHAIN_ID=ait-hub.aitbc.bubuit.net
BLOCKCHAIN_MODE=follower          # or hub / proposer role vars
PROPOSER_ID=ait-hub.aitbc.bubuit.net
VALIDATOR_SET=hub,node1,node2

# /etc/aitbc/aitbc-coordinator-api.env
JWT_SECRET=<random secret>
CLIENT_API_KEYS=<comma-separated keys>
MINER_API_KEYS=<comma-separated keys>
ADMIN_API_KEYS=<comma-separated keys>
COORDINATOR_API_KEY=<key used by follower CLIs>
BLOCKCHAIN_RPC_URL=http://localhost:8202
BLOCKCHAIN_RPC_API_KEY=<key>

# /etc/aitbc/aitbc-marketplace.env
MARKETPLACE_DATABASE_URL=postgresql://user:<DB_PASSWORD>@localhost:5432/aitbc
```

## Configuration Files

> **Note:** no service reads `/etc/aitbc/config.yaml` — the YAML block below
> is illustrative, and the marketplace port shown (8105) is wrong: the
> marketplace listens on 8102 (8105 is governance). Real service ports are in
> [Service Ports Reference](../reference/SERVICE_PORTS.md), and real
> configuration lives in the per-unit env files above.

```yaml
# Illustrative only — no service reads this file
services:
  blockchain:
    port: 8202
    host: 0.0.0.0
  coordinator:
    port: 8203
    host: 0.0.0.0
  marketplace:
    port: 8102
    host: 0.0.0.0
```

> **Note:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Script environment variables

The operational scripts under `scripts/` take their fleet addresses, endpoints
and deployment targets from `AITBC_*` environment variables rather than
hardcoded hosts. See [script-environment.md](./script-environment.md).

## See Also

- [Prerequisites](../getting-started/installation/prerequisites.md) - System requirements
- [Local Setup](local-setup.md) - Local development configuration
- [SSL/TLS Setup](ssl-tls-setup.md) - SSL configuration
