# AITBC - Advanced Intelligence Training Blockchain Consortium

## Project Structure

This project has been organized for better maintainability. Here's the directory structure:

### 📁 Essential Root Files
- [`LICENSE`](LICENSE) - Project license
- [`aitbc-cli`](aitbc-cli) - Main CLI symlink
- [`README.md`](README.md) - This file

### 📁 Core Directories
- [`aitbc/`](aitbc/) - Core AITBC Python package
- [`cli/`](cli/) - Command-line interface implementation
- [`contracts/`](contracts/) - Smart contracts
- [`scripts/`](scripts/) - Automation and deployment scripts
- [`services/`](services/) - Microservices
- [`tests/`](tests/) - Test suites

### 📁 Configuration
- [`project-config/`](project-config/) - Project configuration files
  - [`pyproject.toml`](pyproject.toml) - Python project configuration
  - [`requirements.txt`](requirements.txt) - Python dependencies
  - [`poetry.lock`](poetry.lock) - Dependency lock file
  - [`.gitignore`](.gitignore) - Git ignore rules
  - [`.deployment_progress`](.deployment_progress) - Deployment tracking

### 📁 Documentation
- [`docs/`](docs/) - Comprehensive documentation
  - [`README.md`](docs/README.md) - Main project documentation
  - [`SETUP.md`](docs/SETUP.md) - Setup instructions
  - [`PYTHON_VERSION_STATUS.md`](docs/PYTHON_VERSION_STATUS.md) - Python compatibility
  - [`AITBC1_TEST_COMMANDS.md`](docs/AITBC1_TEST_COMMANDS.md) - Testing commands
  - [`AITBC1_UPDATED_COMMANDS.md`](docs/AITBC1_UPDATED_COMMANDS.md) - Updated commands
  - [`README_DOCUMENTATION.md`](docs/README_DOCUMENTATION.md) - Detailed documentation

### 📁 Development
- [`dev/`](dev/) - Development tools and examples
- [`.windsurf/`](.windsurf/) - IDE configuration
- [`packages/`](packages/) - Package distributions
- [`extensions/`](extensions/) - Browser extensions
- [`plugins/`](plugins/) - System plugins

### 📁 Infrastructure
- [`infra/`](infra/) - Infrastructure as code
- [`systemd/`](systemd/) - System service configurations
- [`monitoring/`](monitoring/) - Monitoring setup

### 📁 Applications
- [`apps/`](apps/) - Application components
- [`services/`](services/) - Service implementations
- [`website/`](website/) - Web interface

### 📁 AI & GPU
- [`gpu_acceleration/`](gpu_acceleration/) - GPU optimization
- [`ai-ml/`](ai-ml/) - AI/ML components

### 📁 Security & Backup
- [`security/`](security/) - Security reports and fixes
- [`backup-config/`](backup-config/) - Backup configurations
- [`backups/`](backups/) - Data backups

### 📁 Cache & Logs
- [`venv/`](venv/) - Python virtual environment
- [`logs/`](logs/) - Application logs
- `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` - Tool caches

## Quick Start

```bash
# Setup environment
cd /opt/aitbc
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run CLI
./aitbc-cli --help

# Run training
./scripts/training/master_training_launcher.sh

# Cross-node communication training
./scripts/training/openclaw_cross_node_comm.sh
```

## Recent Achievements

See [Completed Deployments](docs/beginner/02_project/5_done.md) for detailed project completion history.

### ait-mainnet Migration & Cross-Node Tests (April 22, 2026)
- **All Nodes Migrated to ait-mainnet**: Successfully migrated all blockchain nodes from ait-devnet to ait-mainnet
  - aitbc: CHAIN_ID=ait-mainnet (already configured)
  - aitbc1: CHAIN_ID=ait-mainnet (changed from ait-devnet)
  - gitea-runner: CHAIN_ID=ait-mainnet (changed from ait-devnet)
- **Cross-Node Blockchain Tests**: Created comprehensive test suite for multi-node blockchain features
  - Test file: `/opt/aitbc/tests/verification/test_cross_node_blockchain.py`
  - Tests: Chain ID Consistency, Block Synchronization, Block Range Query, RPC Connectivity
  - All 4 tests passing across 3 nodes (aitbc, aitbc1, gitea-runner)
- **SQLite Database Corruption Fix**: Resolved database corruption on aitbc1 caused by Btrfs CoW behavior
  - Applied `chattr +C` to `/var/lib/aitbc/data` to disable CoW
  - Cleared corrupted database files and restarted service
- **Network Connectivity Fixes**: Corrected RPC URLs for all nodes
  - aitbc1: 10.1.223.40:8006 (corrected from 10.0.3.107:8006)
  - gitea-runner: 10.1.223.93:8006
- **Test File Updates**: Updated all verification tests to use ait-mainnet chain_id
  - test_tx_import.py, test_simple_import.py, test_minimal.py, test_block_import.py, test_block_import_complete.py

### Multi-Node Blockchain Synchronization (April 10, 2026)
- **Gossip Backend Configuration**: Fixed both nodes to use broadcast backend with Redis
  - aitbc: `gossip_backend=broadcast`, `gossip_broadcast_url=redis://localhost:6379`
  - aitbc1: `gossip_backend=broadcast`, `gossip_broadcast_url=redis://10.1.223.40:6379`
- **PoA Consensus Enhancements**: Fixed busy-loop issue in poa.py when mempool is empty
  - Added `propose_only_if_mempool_not_empty=true` configuration
  - Modified `_propose_block` to return boolean indicating if a block was proposed
- **Transaction Synchronization**: Fixed transaction parsing in sync.py
  - Updated `_append_block` to use correct field names (from/to instead of sender/recipient)
- **RPC Endpoint Enhancements**: Fixed blocks-range endpoint to include parent_hash and proposer fields
- **Block Synchronization Verification**: Both nodes in sync at height 27201
- **Git Conflict Resolution**: Fixed gitea pull conflicts on aitbc1 by stashing local changes

### OpenClaw Agent Communication (April 10, 2026)
- **Successfully sent agent message** from aitbc1 to aitbc
- **Wallet used**: temp-agent with password "temp123"
- **Transaction hash**: 0xdcf365542237eb8e40d0aa1cdb3fec2e77dbcb2475c30457682cf385e974b7b8
- **Agent daemon**: Running on aitbc configured to reply with "pong" on "ping"
- **Agent daemon service**: Deployed with systemd integration

### Multi-Node Blockchain Network
- **Genesis Node (aitbc1)**: Height 27201+, operational at 10.1.223.40:8006
- **Follower Node (aitbc)**: Height 27201+, operational at 10.1.223.93:8006
- **Synchronization**: Nodes synchronized via gossip with Redis backend
- **RPC Services**: Running on both nodes

### Documentation Updates (April 10, 2026)
- **Blockchain Synchronization**: `docs/blockchain/blockchain_synchronization_issues_and_fixes.md`
- **OpenClaw Cross-Node Communication**: `docs/openclaw/guides/openclaw_cross_node_communication.md`
- **Cross-Node Training**: `docs/openclaw/training/cross_node_communication_training.md`
- **Agent Daemon Service**: `services/agent_daemon.py` with systemd integration

## Development

See `docs/SETUP.md` for detailed setup instructions.

## Documentation

### Recent Documentation Updates
- [Cross-Node Communication Guide](docs/openclaw/guides/openclaw_cross_node_communication.md) - Implementation guide for multi-node agent messaging
- [Blockchain Synchronization Issues](docs/blockchain/blockchain_synchronization_issues_and_fixes.md) - Detailed documentation of sync fixes and workarounds
- [Cross-Node Training Module](docs/openclaw/training/cross_node_communication_training.md) - Training workflow for agent communication
- [OpenClaw Documentation](docs/openclaw/README.md) - Complete OpenClaw integration documentation

### Core Documentation
- [Main Documentation](docs/README.md) - Comprehensive project documentation
- [Setup Instructions](docs/SETUP.md) - Installation and configuration guide
- [Python Compatibility](docs/PYTHON_VERSION_STATUS.md) - Python version requirements

## Security

See `security/SECURITY_VULNERABILITY_REPORT.md` for security status.

## License

See `LICENSE` for licensing information.
