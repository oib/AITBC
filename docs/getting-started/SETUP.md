# AITBC Setup Guide

**Last Updated:** 2026-05-30

Quick reference guide for AITBC setup and onboarding.

## 5-Minute Quick Start

```bash
# One-command installation
bash <(curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh)

# Or manual installation
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Essential Links

### Installation
- [Prerequisites](installation/prerequisites.md) - System and software requirements
- [Quick Start](installation/quick-start.md) - One-command installation
- [Installation](installation/installation.md) - Monorepo installation
- [Requirements Management](installation/requirements-management.md) - Dependency profiles

### Node Onboarding
- [Blockchain Setup](node/blockchain-setup.md) - Configure blockchain node
- [Hermes Messaging](node/hermes-messaging.md) - PING/PONG messaging
- [Coin Requests](node/coin-requests.md) - Request free coins from hub
- [Configuration Guide](node/configuration-guide.md) - Configuration files

### Mining
- [Miner Quick Start](mining/miner-quick-start.md) - Register GPU and earn tokens

### Platform Overview
- [Introduction](overview/introduction.md) - What is AITBC
- [CLI Guide](overview/cli-guide.md) - CLI setup and usage
- [Enhanced Services](overview/enhanced-services.md) - Enhanced services guide

### Reference
- [Service Endpoints](reference/service-endpoints.md) - Port configuration
- [Management Commands](reference/management-commands.md) - Service control
- [Troubleshooting](reference/troubleshooting.md) - Common issues
- [Security Notes](reference/security-notes.md) - Security best practices
- [Production Deployment](reference/production-deployment.md) - Production checklist

### Open Island
- [Open Island Testing](open-island.md) - Join hub.aitbc.bubuit.net

## Common Commands

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh

# Restart all services
/opt/aitbc/start-services.sh

# View logs
tail -f /var/lib/aitbc/logs/aitbc-*.log

# Systemd control
systemctl status aitbc-blockchain-node
systemctl restart aitbc-coordinator-api
```

## Development Mode

```bash
cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Runtime Directories

```
/var/lib/aitbc/
├── keystore/     # Blockchain private keys
├── data/         # Database files
└── logs/         # Application logs

/etc/aitbc/       # Configuration files
```

## Scenarios

For comprehensive AITBC capabilities and use cases, see [Scenarios Documentation](../scenarios/).

## See Also

- [README](../README.md) - Main documentation index
- [Deployment](../deployment/) - Production deployment guides
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration
