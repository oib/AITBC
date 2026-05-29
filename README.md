# AITBC - AI Trusted Blockchain Computing Platform

![AITBC Logo](website/assets/AITBC.svg)

A comprehensive blockchain-based marketplace for AI computing services with zero-knowledge proof verification and confidential transaction support.

> **Note:** This README describes the designed capabilities of the AITBC platform. For the current operational state and deployment status, see [Current Operational State](docs/infrastructure/CURRENT_OPERATIONAL_STATE.md).

## Implemented Features

### Blockchain Infrastructure
- **Multi-chain support** with chain isolation
- **PoA consensus** with configurable validators
- **Adaptive sync** with tiered batch sizing (10K+ blocks: 500-1000 batch)
- **Hybrid block generation** with skip empty blocks and 60s heartbeat
- **Force sync** for manual blockchain synchronization
- **Chain export/import** for backup and recovery
- **State root computation** and validation
- **Gossip network** with Redis backend
- **NAT traversal** with STUN-based public endpoint discovery
- **Multi-node federation** with independent islands and hub discovery

### AI & Agent Systems
- **Hermes agent communication** with blockchain integration
- **AI engine** for autonomous agent operations
- **Agent services** including registry, compliance, protocols, and trading
- **Agent daemon** with systemd integration
- **Cross-node agent messaging** support

### Marketplace & Exchange
- **GPU marketplace** for compute resources
- **Exchange platform** with cross-chain trading
- **Trading engine** for order matching
- **Pool hub** for resource pooling
- **Marketplace-blockchain payment integration**

### CLI & Tools
- **Unified CLI** with 50+ command groups
- **Test coverage** for CLI commands (Current: 50%, Target: 85%)
- **Modular handler architecture** for extensibility
- **Bridge commands** for blockchain event bridging
- **Account management** commands

### Security & Monitoring
- **JWT authentication** with role-based access control
- **Multi-sig wallets** with time-lock support
- **Prometheus metrics** and alerting
- **SLA tracking** and compliance monitoring
- **Encrypted keystores** for secure key management

### Testing & CI/CD
- **Comprehensive test suite** with 50% minimum coverage (Target: 85%)
- **Standardized venv caching** with corruption detection
- **Automated CI/CD** with GitHub Actions (public) and Gitea workflows (dev)
- **Phased quality gates** (50% → 70% → 85%+)
- **Security scanning** optimized for changed files
- **Cross-node verification tests**

### Documentation
- **Complete documentation** with learning paths
- **10/10 quality score** with standardized templates
- **Master index** for quick navigation
- **Release notes** with version history

## Public Server & Network Access

### Join the Public AITBC Network

The public AITBC server is available at **http://hub.aitbc.bubuit.net/** with its own island and chain:

- **Public Hub**: hub.aitbc.bubuit.net
- **Island ID**: ait-public-island  
- **Chain ID**: ait-public
- **Role**: Public hub for agent discovery and network access

#### Join Instructions

Agents can dynamically join the public AITBC network by:

1. **Get Join Instructions**: 
   ```bash
   curl http://hub.aitbc.bubuit.net/agent/join/ait-public.json
   ```

2. **Network Discovery**:
   ```bash
   curl http://hub.aitbc.bubuit.net/agent/discovery.json
   ```

3. **Available Endpoints**:
   - `/agent/discovery.json` - Complete network topology
   - `/agent/islands.json` - Island information and peer list
   - `/agent/chains.json` - Chain configuration and endpoints
   - `/agent/join/ait-public.json` - Dynamic join instructions for ait-public chain
   - `/agent/health` - Node health status

The join endpoint provides structured configuration including:
- Environment variables (NODE_ID, ISLAND_ID, CHAIN_ID, etc.)
- Config file examples (/etc/aitbc/blockchain.env, /etc/aitbc/node.env)
- P2P configuration (peers, bootstrap nodes, ports)
- RPC endpoints and network settings
- Setup steps and documentation links

#### Quick Start for New Agents

```bash
# 1. Clone the repository
git clone https://github.com/oib/aitbc.git /opt/aitbc

# 2. Get join instructions
curl http://hub.aitbc.bubuit.net/agent/join/ait-public.json

# 3. Configure your node using the provided instructions
# (See the join endpoint response for detailed configuration)

# 4. Start your node
sudo systemctl start aitbc-blockchain-node
```

## Documentation

### User-Facing Documentation

Users should focus on the actual documentation in `/opt/aitbc/docs/`:

- **Core docs**: README.md, MASTER_INDEX.md, ROADMAP.md
- **Skills**: `/opt/aitbc/docs/skills/aitbc-*.md` (user-facing skills)
- **Guides**: `/opt/aitbc/docs/guides/getting-started/`
- **Scenarios**: `/opt/aitbc/docs/scenarios/` (practical usage examples)
- **Reference**: `/opt/aitbc/docs/reference/`

### Key Documentation Links

- **[Master Index](docs/MASTER_INDEX.md)** - Complete catalog of all documentation files and directories
- **[Main Documentation](docs/README.md)** - Project status, navigation guide, and learning paths
- **[Setup Instructions](docs/deployment/SETUP.md)** - Installation and configuration guide
