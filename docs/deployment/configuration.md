# Deployment Configuration

This guide covers environment variables and configuration files for AITBC deployment.

## Environment Variables

```bash
# /etc/aitbc/blockchain.env
BLOCKCHAIN_NETWORK_ID=1
BLOCKCHAIN_GENESIS_BLOCK_HASH=0x...
BLOCKCHAIN_CONSENSUS_ALGORITHM=proof_of_stake
BLOCKCHAIN_VALIDATOR_PRIVATE_KEY=0x...

# /etc/aitbc/coordinator.env
COORDINATOR_API_KEY=your-api-key
COORDINATOR_DATABASE_URL=postgresql://user:pass@localhost:5432/aitbc
COORDINATOR_REDIS_URL=redis://localhost:6379
COORDINATOR_JWT_SECRET=your-jwt-secret

# /etc/aitbc/marketplace.env
MARKETPLACE_DATABASE_URL=postgresql://user:pass@localhost:5432/aitbc
MARKETPLACE_REDIS_URL=redis://localhost:6379
MARKETPLACE_API_KEY=your-api-key
```

## Configuration Files

```yaml
# /etc/aitbc/config.yaml
services:
  blockchain:
    port: 8202
    host: 0.0.0.0
    database:
      host: localhost
      port: 5432
      name: aitbc

  coordinator:
    port: 8203
    host: 0.0.0.0
    database:
      host: localhost
      port: 5432
      name: aitbc
    cache:
      host: localhost
      port: 6379

  marketplace:
    port: 8105
    host: 0.0.0.0
    database:
      host: localhost
      port: 5432
      name: aitbc
```

> **Note:** For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## See Also

- [Prerequisites](prerequisites.md) - System requirements
- [Local Setup](local-setup.md) - Local development configuration
- [SSL/TLS Setup](ssl-tls-setup.md) - SSL configuration
