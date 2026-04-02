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
pip install -r project-config/requirements.txt

# Run CLI
./aitbc-cli --help

# Run training
./scripts/training/master_training_launcher.sh
```

## Development

See `documentation/SETUP.md` for detailed setup instructions.

## Security

See `security/SECURITY_VULNERABILITY_REPORT.md` for security status.

## License

See `LICENSE` for licensing information.
