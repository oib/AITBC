# AITBC - Installation Guide

**Last Updated**: 2026-06-30
**Version**: 1.0

## System Requirements

- **Python**: 3.13.5+ (exact version required)
- **Node.js**: 24.14.0+ (exact version required)
- **Git**: Latest version
- **Docker**: Not supported (do not use)

### Root Cause Analysis
The system requirements are based on actual project configuration:
- **Python 3.13.5+**: Defined in `pyproject.toml` as `requires-python = ">=3.13.5"`
- **Node.js 24.14.0+**: Defined in `config/.nvmrc` as `24.14.0`
- **No Docker Support**: Docker is not used in this project

## Quick Installation

```bash
# Clone the repository
git clone https://github.com/oib/AITBC.git
cd AITBC

# Install CLI tool (requires virtual environment)
cd cli
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Verify installation
aitbc version
aitbc --help

# OPTIONAL: Add convenient alias for easy access
echo 'alias aitbc="source /opt/aitbc/cli/venv/bin/activate && aitbc"' >> ~/.bashrc
source ~/.bashrc
# Now you can use 'aitbc' from anywhere!
```

## Development Setup

```bash
# Clone the repository
git clone https://github.com/oib/AITBC.git
cd AITBC

# Install CLI tool (requires virtual environment)
cd cli
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Verify correct Python version
python3 --version  # Should be 3.13.5+

# Verify correct Node.js version
node --version      # Should be 24.14.0+

# Run tests
pytest

# Install pre-commit hooks
pre-commit install

# OPTIONAL: Add convenient alias for easy access
echo 'alias aitbc="source /opt/aitbc/cli/venv/bin/activate && aitbc"' >> ~/.bashrc
source ~/.bashrc
```

## Version Compliance

- **Python**: Must be exactly 3.13.5 or higher
- **Node.js**: Must be exactly 24.14.0 or higher
- **Docker**: Not supported - do not attempt to use
- **Package Manager**: Use pip for Python, npm for Node.js packages

## Related Topics

- [Project Overview](./project-overview.md) - General project information
- [Usage Examples](./usage-examples.md) - Code examples and workflows
