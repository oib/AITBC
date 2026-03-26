# AITBC CLI Local Package Installation

This directory contains the locally built AITBC CLI package for installation without PyPI access.

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

## Package Files

- `dist/aitbc_cli-0.1.0-py3-none-any.whl` - Wheel package (recommended)
- `dist/aitbc_cli-0.1.0.tar.gz` - Source distribution
- `install_local_package.sh` - Automated installation script
- `setup.py` - Package setup configuration
- `requirements.txt` - Package dependencies

## Requirements

- **Python 3.13+** (strict requirement)
- 10MB+ free disk space
- Internet connection for dependency installation (first time only)

## Usage

After installation:

```bash
# Activate the CLI environment (if using script)
source ./activate_aitbc_cli.sh

# Or activate virtual environment manually
source venv/bin/activate

# Check CLI version
aitbc --version

# Show help
aitbc --help

# Example commands
aitbc wallet balance
aitbc blockchain sync-status
aitbc marketplace gpu list
```

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

### Module Not Found
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Check installation
pip list | grep aitbc-cli

# Reinstall if needed
pip install --force-reinstall dist/aitbc_cli-0.1.0-py3-none-any.whl
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

### Local PyPI Server (Optional)

```bash
# Install local PyPI server
pip install pypiserver

# Create package directory
mkdir -p ~/local_pypi/packages
cp dist/*.whl ~/local_pypi/packages/

# Start server
pypiserver ~/local_pypi/packages -p 8080

# Install from local PyPI
pip install --index-url http://localhost:8080/simple/ aitbc-cli
```

## Development

### Building from Source

```bash
# Clone repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc/cli

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install build tools
pip install build

# Build package
python -m build --wheel

# Install locally
pip install dist/aitbc_cli-0.1.0-py3-none-any.whl
```

### Testing Installation

```bash
# Test basic functionality
aitbc --version
aitbc --help

# Test with mock data
aitbc wallet balance
aitbc blockchain sync-status
aitbc marketplace gpu list
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

## Support

- **Documentation**: See CLI help with `aitbc --help`
- **Issues**: Report to AITBC development team
- **Dependencies**: All requirements in `requirements.txt`

## Package Information

- **Name**: aitbc-cli
- **Version**: 0.1.0
- **Python Required**: 3.13+
- **Dependencies**: 12 core packages
- **Size**: ~130KB (wheel)
- **Entry Point**: `aitbc=aitbc_cli.main:main`

## Features Included

- 40+ CLI commands
- Rich terminal output
- Multiple output formats (table, JSON, YAML)
- Secure credential management
- Shell completion support
- Comprehensive error handling
- Mock data for testing
