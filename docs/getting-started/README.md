# Getting Started with AITBC

Welcome to the AITBC getting started guide. This directory contains comprehensive documentation for installing, configuring, and using the AITBC platform.

## Quick Start

For the fastest setup, see [SETUP.md](SETUP.md) for a 5-minute quick start guide.

## User Journey Paths

Choose the path that matches your use case:

### New User Path

If you're new to AITBC and want to get started quickly:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Quick Start](installation/quick-start.md) - One-command installation
3. [CLI Guide](overview/cli-guide.md) - Learn the CLI commands
4. [Introduction](overview/introduction.md) - Understand what AITBC is

### Node Operator Path

If you're setting up a follower node on the island:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Quick Start](installation/quick-start.md) - Install AITBC
3. [Blockchain Setup](node/blockchain-setup.md) - Configure blockchain node
4. [Hermes Messaging](node/hermes-messaging.md) - Set up PING/PONG messaging
5. [Coin Requests](node/coin-requests.md) - Request free coins from hub
6. [Configuration Guide](node/configuration-guide.md) - Configure your node

### Miner Path

If you want to earn tokens by providing GPU compute:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements (GPU needed)
2. [Quick Start](installation/quick-start.md) - Install AITBC
3. [Miner Quick Start](mining/miner-quick-start.md) - Register GPU and start earning
4. [Coin Requests](node/coin-requests.md) - Request coins for transactions

### Developer Path

If you're developing with AITBC:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Installation](installation/installation.md) - Monorepo installation
3. [CLI Guide](overview/cli-guide.md) - Learn CLI commands
4. [Introduction](overview/introduction.md) - Understand platform architecture
5. [Enhanced Services](overview/enhanced-services.md) - Enhanced services guide

### Open Island Path

If you want to join the hub.aitbc.bubuit.net open island:

1. [Prerequisites](installation/prerequisites.md) - Check system requirements
2. [Quick Start](installation/quick-start.md) - Install AITBC
3. [Open Island Testing](open-island.md) - Join the open island
4. [Blockchain Setup](node/blockchain-setup.md) - Configure for hub connectivity
5. [Hermes Messaging](node/hermes-messaging.md) - Set up agent communication

## Directory Structure

```
getting-started/
├── README.md (this file)
├── SETUP.md (quick reference)
├── open-island.md (open island testing)
├── installation/ (installation guides)
│   ├── prerequisites.md
│   ├── quick-start.md
│   ├── installation.md
│   └── requirements-management.md
├── node/ (node onboarding)
│   ├── blockchain-setup.md
│   ├── hermes-messaging.md
│   ├── coin-requests.md
│   └── configuration-guide.md
├── mining/ (GPU mining)
│   └── miner-quick-start.md
├── reference/ (reference docs)
│   ├── service-endpoints.md
│   ├── management-commands.md
│   ├── troubleshooting.md
│   ├── security-notes.md
│   └── production-deployment.md
└── overview/ (platform overview)
    ├── introduction.md
    ├── cli-guide.md
    └── enhanced-services.md
```

## Additional Resources

- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration
- [Deployment Guides](../deployment/) - Production deployment
- [Scenarios Documentation](../scenarios/) - Comprehensive capability examples
- [Main Documentation Index](../README.md) - All documentation

## Getting Help

If you encounter issues:
1. Check [Troubleshooting](reference/troubleshooting.md)
2. Review [Service Endpoints](reference/service-endpoints.md)
3. Consult [Management Commands](reference/management-commands.md)
