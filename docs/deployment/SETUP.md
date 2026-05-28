# AITBC Setup Guide

**Last Updated:** 2026-05-28

> **Important:** This document describes the setup process. For the current operational state and deployment status, see [Current Operational State](../infrastructure/CURRENT_OPERATIONAL_STATE.md). For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Quick Setup (New Host)

The main setup script lives at `scripts/setup.sh`.

Run this single command on any new host to install AITBC:

```bash
sudo bash <(curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/setup.sh)
```

Or clone and run manually:

### For Internal Users (Gitea)

```bash
sudo git clone https://gitea.bubuit.net:3000/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
sudo chmod +x scripts/setup.sh
sudo ./scripts/setup.sh
```

### For External/Public Users (GitHub)

```bash
sudo git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
sudo chmod +x scripts/setup.sh
sudo ./scripts/setup.sh
```

## What `scripts/setup.sh` Does

1. **Prerequisites Check**
   - Verifies Python 3.13.5+, pip3, git, systemd
   - Checks for root privileges

2. **Repository Setup**
   - Clones AITBC repository to `/opt/aitbc`
   - Handles multiple repository URLs for reliability

3. **Virtual Environments**
   - Creates Python venvs for each service
   - Installs dependencies from `requirements.txt` when available
   - Falls back to core dependencies if requirements missing

4. **Runtime Directories**
   - Creates standard Linux directories:
     - `/var/lib/aitbc/keystore/` - Blockchain keys
     - `/var/lib/aitbc/data/` - Database files  
     - `/var/lib/aitbc/logs/` - Application logs
     - `/etc/aitbc/` - Configuration files
   - Sets proper permissions and ownership

5. **PostgreSQL Databases**
   - Installs PostgreSQL if not present
   - Creates databases: aitbc_coordinator, aitbc_exchange, aitbc_wallet, aitbc_marketplace, aitbc_governance, aitbc_trading, aitbc_gpu, aitbc_ai, aitbc_mempool
   - Creates dedicated users for each database
   - Grants necessary privileges
   - Uses centralized script: `/opt/aitbc/infra/scripts/setup_postgresql_databases.sh`

6. **Systemd Services**
   - Installs service files to `/etc/systemd/system/`
   - Enables auto-start on boot
   - Provides fallback manual startup

7. **Service Management**
   - Creates `/opt/aitbc/start-services.sh` for manual control
   - Uses `/opt/aitbc/scripts/monitoring/health_check.sh` for monitoring
   - Sets up logging to `/var/log/aitbc-*.log`

## Runtime Directories

AITBC uses standard Linux system directories for runtime data:

```
/var/lib/aitbc/
├── keystore/     # Blockchain private keys (700 permissions)
├── data/         # Database files (.db, .sqlite)
└── logs/         # Application logs

/etc/aitbc/       # Configuration files
/var/log/aitbc/   # System logging
```

### Security Notes
- **Keystore**: Restricted to root/aitbc user only
- **Data**: Writable by services, readable by admin
- **Logs**: Rotated automatically by logrotate

## Service Endpoints

For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Health Endpoint |
|---------|------|----------------|
| Wallet API | 8015 | `http://localhost:8015/health` |
| Exchange API | 8001 | `http://localhost:8001/health` |
| Coordinator API | 8011 | `http://localhost:8011/health` |
| Blockchain RPC | 8006 | `http://localhost:8006/health` |
| Marketplace | 8102 | `http://localhost:8102/health` |

**Note:** Port configurations are defined in service wrapper scripts and application main.py files. See [Service Ports Reference](../reference/SERVICE_PORTS.md) for complete details and source references.

## Management Commands

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh

# Restart all services
/opt/aitbc/start-services.sh

# View logs (new standard locations)
tail -f /var/lib/aitbc/logs/aitbc-wallet.log
tail -f /var/lib/aitbc/logs/aitbc-coordinator.log
tail -f /var/lib/aitbc/logs/aitbc-exchange.log

# Check keystore
ls -la /var/lib/aitbc/keystore/

# Systemd control
systemctl status aitbc-wallet
systemctl restart aitbc-coordinator-api
systemctl stop aitbc-exchange-api
```

## Troubleshooting

### Services Not Starting
1. Check logs: `tail -f /var/lib/aitbc/logs/aitbc-*.log`
2. Verify ports: `netstat -tlnp | grep ':800'`
3. Check processes: `ps aux | grep python`
4. Verify runtime directories: `ls -la /var/lib/aitbc/`

### Missing Dependencies
The setup script handles missing `requirements.txt` files by installing core dependencies:
- fastapi
- uvicorn
- pydantic
- httpx
- python-dotenv

### Port Conflicts
Services use these default ports. If conflicts exist:
1. Kill conflicting processes: `kill <pid>`
2. Modify service files to use different ports
3. Restart services

## Development Mode

For development with manual control:

```bash
cd /opt/aitbc/apps/wallet
source .venv/bin/activate
python simple_daemon.py

cd /opt/aitbc/apps/exchange
source .venv/bin/activate
python simple_exchange_api.py

cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Configuration Files

AITBC uses two main configuration files located in `/etc/aitbc/`:

### /etc/aitbc/blockchain.env
Contains blockchain-specific environment variables:
- Chain ID and network configuration
- RPC and P2P binding settings
- Database and Redis connections
- Block production settings
- Gossip and sync configuration

### /etc/aitbc/node.env
Contains node-specific environment variables:
- Node ID and island ID
- Node role (genesis/follower)
- P2P port configuration
- Node-specific settings

**Note**: AITBC does NOT use `/etc/aitbc/.env`. All configuration should be in `blockchain.env` and `node.env`.

### Configuration Examples

Pre-configured example files are available in `/opt/aitbc/examples/` for quick setup:

- **[Examples README](../../examples/README.md)** - Complete guide to all configuration examples
- **[blockchain.env.open-island](../../examples/blockchain.env.open-island)** - Pre-configured for hub.aitbc.bubuit.net open island
- **[node.env.open-island](../../examples/node.env.open-island)** - Node-specific configuration for open island
- **[blockchain.env.example](../../examples/blockchain.env.example)** - General blockchain configuration template
- **[node.env.example](../../examples/node.env.example)** - General node configuration template

**Quick Setup for Open Island:**
```bash
sudo cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
sudo cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
```

## Production Considerations

For production deployment:
1. Configure `/etc/aitbc/blockchain.env` with proper environment variables
2. Configure `/etc/aitbc/node.env` with node-specific settings
3. Set up reverse proxy (nginx)
4. Configure SSL certificates manually outside `scripts/setup.sh`
5. Set up log rotation
6. Configure monitoring and alerts
7. Use proper database setup (PostgreSQL/Redis)

## Hermes Skills Integration

AITBC includes documentation skills for Hermes agents. These skills enable automated operations and can be imported by Hermes agents to perform tasks:

- **[Documentation Skills](../skills/)** - Complete skill library for Hermes agents:
  - [aitbc-basic-operations.md](../skills/aitbc-basic-operations.md) - Basic CLI operations, wallet management, blockchain status
  - [aitbc-marketplace.md](../skills/aitbc-marketplace.md) - Marketplace operations, GPU provider registration, trading
  - [aitbc-node-coordination.md](../skills/aitbc-node-coordination.md) - Multi-node coordination, git synchronization, blockchain sync
  - [aitbc-wallet-management.md](../skills/aitbc-wallet-management.md) - Wallet creation, import/export, balance checks, deletion
  - [aitbc-ai-operations.md](../skills/aitbc-ai-operations.md) - AI job submission, monitoring, resource allocation, GPU testing
  - [aitbc-blockchain-troubleshooting.md](../skills/aitbc-blockchain-troubleshooting.md) - Blockchain troubleshooting, sync issues, P2P problems
  - [aitbc-multi-node-operations.md](../skills/aitbc-multi-node-operations.md) - Multi-node operations, git sync, service restart, blockchain sync
  - [aitbc-cli.md](../skills/aitbc-cli.md) - CLI tool reference for training agents and workflow operations

These skills are located in `docs/skills/` and follow the YAML frontmatter format required by Hermes for skill loading.

## Open Island Testing

AITBC provides an open test island for software testing and agent coordination:

- **[Open Island Joining Guide](../hermes/guides/open-island-joining-guide.md)** - Complete guide for joining the hub.aitbc.bubuit.net open island:
  - Quick start setup for new nodes
  - P2P and RPC connectivity to the hub
  - hermes agent registration and cross-node communication
  - Blockchain synchronization with the open island
  - Troubleshooting and security guidelines

- **[hermes Agent Guide for Open Island](../hermes/guides/hermes-open-island-guide.md)** - hermes-specific instructions for agents joining the open island:
  - hermes agent initialization and configuration
  - Agent wallet creation and registration
  - Cross-node communication patterns
  - hermes workflow integration
  - Testing procedures and best practices

The open island allows any agent to test AITBC software functionality without authentication requirements.

## AITBC Software Capabilities (Scenarios)

AITBC provides comprehensive scenario documentation that demonstrates the full range of software capabilities and use cases. These scenarios help hermes agents and developers understand what AITBC is built for and how to use it effectively.

- **[Scenarios Documentation](../scenarios/)** - Complete library of AITBC software scenarios:
  - [Scenarios README](../scenarios/README.md) - Overview of all available scenarios and how to use them
  - [Validation Guide](../scenarios/VALIDATION.md) - Standardized testing procedures for scenario validation
  - [Validation Guide (Detailed)](../scenarios/VALIDATION_GUIDE.md) - Comprehensive validation with multi-node testing
  - [Troubleshooting Guide](../scenarios/TROUBLESHOOTING_GUIDE.md) - Common issues and solutions for scenario execution

**Core Capabilities Covered:**
- **Blockchain Operations** (scenarios 01-05): Wallet basics, transactions, genesis deployment, messaging, island creation
- **Trading & Marketplace** (scenarios 06-10): Basic trading, AI job submission, marketplace bidding, GPU listing, plugin development
- **Database & Infrastructure** (scenarios 11-13): IPFS storage, database operations, mining setup
- **Staking & Governance** (scenarios 14-18): Staking basics, blockchain monitoring, agent registration, governance voting, analytics
- **Security & Cross-Chain** (scenarios 19-20): Security setup, cross-chain transfers
- **Advanced Agents** (scenarios 21-40): Compute provider, AI training, data oracle, swarm coordinator, marketplace arbitrage, staking validator, cross-chain trader, monitoring agent, plugin marketplace, database service, federation bridge, AI power advertiser, multi-chain validator, compliance agent, edge compute, autonomous compute provider, distributed AI training, cross-chain market maker, federated learning coordinator, enterprise AI agent
- **Advanced Features** (scenarios 41-47): Bounty system, portfolio management, knowledge graph market, dispute resolution, zero-knowledge proofs, multi-chain island architecture, cross-chain atomic swap

These scenarios are located in `docs/scenarios/` and provide practical examples of AITBC's capabilities for both automated agent operations and human understanding of the system's purpose.
