# Getting Started with AITBC

Welcome to the AITBC getting started guide. This directory contains the fastest paths to install, configure, and use the AITBC platform.

## Three ways to participate

An AITBC node is configured by two independent axes:

| Role | Axis | What it does | Typical profile |
|------|------|--------------|-----------------|
| **Hub** | `BLOCKCHAIN_MODE=hub` | Produces and broadcasts blocks, runs the coordinator, exchange, and public discovery endpoints. | `hub` |
| **Shop** | `MARKET_ROLE=shop` | Provides GPU, edge, marketplace, and mining services; sells compute to the network. | `provider-gpu` (with GPU) or `server-no-gpu` (without GPU) |
| **Client** | `MARKET_ROLE=customer` | Consumes compute: submits jobs, queries results, and syncs as a follower. Also called the **customer node**. | `customer-no-gpu` |

A single node can combine roles. For example, a hub can also be a shop, and a follower can be a client or a shop. See [Service Selection](setup-service-selection.md) for the full service matrix.

## Role-based paths

### Client (consume compute)

If you want to submit AI jobs and use the network:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Quick Start](installation/quick-start.md) - One-command installation
3. [Open Island Testing](open-island.md) - Join the `hub.aitbc.bubuit.net` open island
4. [Node Quick Start](node-quickstart.md) - Configure a follower/customer node
5. [CLI Guide](overview/cli-guide.md) - Learn the CLI commands
6. [Unit System](unit-system.md) - Learn about AIT and compute-seconds

### Shop (provide GPU compute)

If you want to earn tokens by providing GPU compute:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements (GPU needed)
2. [Quick Start](installation/quick-start.md) - Install AITBC
3. [Service Selection](setup-service-selection.md) - Choose `MARKET_ROLE=shop`
4. [Miner Quick Start](mining/miner-quick-start.md) - Register GPU and start earning
5. [Coin Requests](node/coin-requests.md) - Request coins for transactions

### Hub (run a public or private island)

If you are operating a central island with all services:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Quick Start](installation/quick-start.md) - Install AITBC
3. [Service Selection](setup-service-selection.md) - Choose `BLOCKCHAIN_MODE=hub`
4. [Blockchain Setup](node/blockchain-setup.md) - Configure the blockchain node
5. [Configuration Guide](node/configuration-guide.md) - Configure your node
6. [Setup Reference](setup-reference.md) - Common commands and troubleshooting

### Developer

If you are developing with AITBC:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Installation](installation/installation.md) - Monorepo installation
3. [Introduction](overview/introduction.md) - Understand platform architecture
4. [CLI Guide](overview/cli-guide.md) - Learn CLI commands
5. [Unit System](unit-system.md) - Learn about AIT and compute-seconds

## Directory Structure

```
getting-started/
├── README.md (this file)
├── SETUP.md (quick reference)
├── open-island.md (open island testing)
├── ait-value-model.md
├── unit-system.md
├── installation/ (installation guides)
│   ├── prerequisites.md
│   ├── quick-start.md
│   ├── installation.md
│   └── requirements-management.md
├── node/ (node onboarding)
│   ├── blockchain-setup.md
│   ├── agent-messaging.md
│   ├── coin-requests.md
│   └── configuration-guide.md
├── mining/ (GPU mining)
│   └── miner-quick-start.md
├── overview/ (platform overview)
│   ├── introduction.md
│   ├── cli-guide.md
│   └── enhanced-services.md
└── reference/ (reference docs)
    ├── service-endpoints.md
    ├── management-commands.md
    ├── troubleshooting.md
    ├── security-notes.md
    └── production-deployment.md
```

## Additional Resources

- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration
- [Deployment Guides](../deployment/) - Production deployment
- [Scenarios Documentation](../scenarios/) - Comprehensive capability examples
- [Main Documentation Index](../README.md) - All documentation
- [Apps Documentation](../apps/) - Per-service documentation

## Getting Help

If you encounter issues:

1. Check [Troubleshooting](reference/troubleshooting.md)
2. Review [Service Endpoints](reference/service-endpoints.md)
3. Consult [Management Commands](reference/management-commands.md)
