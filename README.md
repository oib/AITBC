# AITBC - Advanced Intelligence Training Blockchain Consortium

## Project Structure

This project has been organized for better maintainability. Here's the directory structure:

### 📁 Essential Root Files
- `LICENSE` - Project license
- `aitbc-cli` - Main CLI symlink
- `README.md` - This file

### 📁 Core Directories
- `aitbc/` - Core AITBC Python package
- `cli/` - Command-line interface implementation
- `contracts/` - Smart contracts
- `scripts/` - Automation and deployment scripts
- `services/` - Microservices
- `tests/` - Test suites

### 📁 Configuration
- `project-config/` - Project configuration files
  - `pyproject.toml` - Python project configuration
  - `requirements.txt` - Python dependencies
  - `poetry.lock` - Dependency lock file
  - `.gitignore` - Git ignore rules
  - `.deployment_progress` - Deployment tracking

### 📁 Documentation
- `docs/` - Comprehensive documentation
  - `README.md` - Main project documentation
  - `SETUP.md` - Setup instructions
  - `PYTHON_VERSION_STATUS.md` - Python compatibility
  - `AITBC1_TEST_COMMANDS.md` - Testing commands
  - `AITBC1_UPDATED_COMMANDS.md` - Updated commands
  - `README_DOCUMENTATION.md` - Detailed documentation

### 📁 Development
- `dev/` - Development tools and examples
- `.windsurf/` - IDE configuration
- `packages/` - Package distributions
- `extensions/` - Browser extensions
- `plugins/` - System plugins

### 📁 Infrastructure
- `infra/` - Infrastructure as code
- `systemd/` - System service configurations
- `monitoring/` - Monitoring setup

### 📁 Applications
- `apps/` - Application components
- `services/` - Service implementations
- `website/` - Web interface

### 📁 AI & GPU
- `gpu_acceleration/` - GPU optimization
- `ai-ml/` - AI/ML components

### 📁 Security & Backup
- `security/` - Security reports and fixes
- `backup-config/` - Backup configurations
- `backups/` - Data backups

### 📁 Cache & Logs
- `venv/` - Python virtual environment
- `logs/` - Application logs
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

### Cross-Node Agent Communication (April 2026)
- **Successfully implemented** autonomous agent messaging between blockchain nodes
- **Ping-pong test completed**: Agents on `aitbc` and `aitbc1` successfully exchanged messages
- **Transaction-based messaging**: Agents communicate via blockchain transaction payloads
- **Autonomous agent daemon**: Listens for messages and replies automatically
- **Block confirmed**: Cross-node communication verified in Block 26952

### Multi-Node Blockchain Network
- **Genesis Node (aitbc1)**: Height 26952+, operational at 10.1.223.40:8006
- **Follower Node (aitbc)**: Height 26952+, operational at 10.1.223.93:8006
- **Synchronization**: Nodes synchronized with manual sync workaround
- **RPC Services**: Running on both nodes

### Blockchain Synchronization Fixes
- **Rate limiting disabled**: Removed 1-second import rate limit on `/rpc/importBlock`
- **Issue documented**: `/rpc/blocks-range` endpoint missing transaction data
- **Workaround implemented**: Direct database queries for transaction retrieval
- **Manual sync procedure**: Database copy method for rapid synchronization

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
