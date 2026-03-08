# AITBC CLI Quick Install Guide

## ✅ Status: WORKING PACKAGE

The local package has been successfully built and tested! All command registration issues have been resolved.

## Quick Installation

### Method 1: Automated Installation (Recommended)

```bash
# Run the installation script
./install_local_package.sh
```

### Method 2: Manual Installation

```bash
# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install from wheel file
pip install dist/aitbc_cli-0.1.0-py3-none-any.whl

# Verify installation
aitbc --version
```

### Method 3: Direct Installation

```bash
# Install directly from current directory
pip install .

# Or from wheel file
pip install dist/aitbc_cli-0.1.0-py3-none-any.whl
```

## ✅ Verification

```bash
# Test CLI
aitbc --help
aitbc --version
aitbc wallet --help
```

## Available Commands (22 total)

- **admin** - System administration commands
- **agent** - Advanced AI agent workflow and execution management
- **agent-comm** - Cross-chain agent communication commands
- **analytics** - Chain analytics and monitoring commands
- **auth** - Manage API keys and authentication
- **blockchain** - Query blockchain information and status
- **chain** - Multi-chain management commands
- **client** - Submit and manage jobs
- **config** - Manage CLI configuration
- **deploy** - Production deployment and scaling commands
- **exchange** - Bitcoin exchange operations
- **genesis** - Genesis block generation and management commands
- **governance** - Governance proposals and voting
- **marketplace** - GPU marketplace operations
- **miner** - Register as miner and process jobs
- **monitor** - Monitoring, metrics, and alerting commands
- **multimodal** - Multi-modal agent processing and cross-modal operations
- **node** - Node management commands
- **optimize** - Autonomous optimization and predictive operations
- **plugin** - Manage CLI plugins
- **simulate** - Run simulations and manage test users
- **swarm** - Swarm intelligence and collective optimization
- **version** - Show version information
- **wallet** - Manage your AITBC wallets and transactions

## Package Files

- ✅ `dist/aitbc_cli-0.1.0-py3-none-any.whl` - Working wheel package (130KB)
- ✅ `dist/aitbc_cli-0.1.0.tar.gz` - Source distribution (112KB)
- ✅ `install_local_package.sh` - Automated installation script
- ✅ `setup.py` - Package setup configuration
- ✅ `requirements.txt` - Package dependencies

## Requirements

- **Python 3.13+** (strict requirement)
- 10MB+ free disk space
- Internet connection for dependency installation (first time only)

## Configuration

```bash
# Set API key
export CLIENT_API_KEY=your_api_key_here

# Or save permanently
aitbc config set api_key your_api_key_here

# Set coordinator URL
aitbc config set coordinator_url http://localhost:8000

# Show configuration
aitbc config show
```

## Package Distribution

### For Other Systems

1. **Copy the package files**:
   ```bash
   # Copy wheel file to target system
   scp dist/aitbc_cli-0.1.0-py3-none-any.whl user@target:/tmp/
   ```

2. **Install on target system**:
   ```bash
   # On target system
   cd /tmp
   python3.13 -m venv aitbc_env
   source aitbc_env/bin/activate
   pip install aitbc_cli-0.1.0-py3-none-any.whl
   ```

## Test Results

✅ All tests passed:
- Package structure: ✓
- Dependencies: ✓
- CLI import: ✓
- CLI help: ✓
- Basic commands: ✓

## Troubleshooting

### Python Version Issues
```bash
# Check Python version
python3 --version

# Install Python 3.13 (Ubuntu/Debian)
sudo apt update
sudo apt install python3.13 python3.13-venv
```

### Permission Issues
```bash
# Use user installation
pip install --user dist/aitbc_cli-0.1.0-py3-none-any.whl

# Or use virtual environment (recommended)
python3.13 -m venv venv
source venv/bin/activate
pip install dist/aitbc_cli-0.1.0-py3-none-any.whl
```

## Uninstallation

```bash
# Uninstall package
pip uninstall aitbc-cli

# Remove virtual environment
rm -rf venv

# Remove configuration (optional)
rm -rf ~/.aitbc/
```

## 🎉 Success!

The AITBC CLI package is now fully functional and ready for distribution.
