---
description: Continue AITBC CLI Enhancement Development
auto_execution_mode: 3
title: AITBC CLI Enhancement Workflow
version: 2.1
---

# Continue AITBC CLI Enhancement

This workflow helps you continue working on the AITBC CLI enhancement task with the current consolidated project structure.

## Current Status

### Completed
- ✅ Phase 0: Foundation fixes (URL standardization, package structure, credential storage)
- ✅ Phase 1: Enhanced existing CLI tools (client, miner, wallet, auth)
- ✅ Unified CLI with rich output formatting
- ✅ Secure credential management with keyring
- ✅ **NEW**: Project consolidation to `/opt/aitbc` structure
- ✅ **NEW**: Consolidated virtual environment (`/opt/aitbc/venv`)
- ✅ **NEW**: Unified CLI wrapper (`/opt/aitbc/aitbc-cli`)

### Next Steps

1. **Review Progress**: Check what's been implemented in current CLI structure
2. **Phase 2 Tasks**: Implement new CLI tools (blockchain, marketplace, simulate)
3. **Testing**: Add comprehensive tests for CLI tools
4. **Documentation**: Update CLI documentation
5. **Integration**: Ensure CLI works with current service endpoints

## Workflow Steps

### 1. Check Current Status
```bash
# Activate environment and check CLI
cd /opt/aitbc
source venv/bin/activate

# Check CLI functionality
./aitbc-cli --help
./aitbc-cli client --help
./aitbc-cli miner --help
./aitbc-cli wallet --help
./aitbc-cli auth --help

# Check current CLI structure
ls -la cli/aitbc_cli/commands/
```

### 2. Continue with Phase 2
```bash
# Create blockchain command
# File: cli/aitbc_cli/commands/blockchain.py

# Create marketplace command  
# File: cli/aitbc_cli/commands/marketplace.py

# Create simulate command
# File: cli/aitbc_cli/commands/simulate.py

# Add to main.py imports and cli.add_command()
# Update: cli/aitbc_cli/main.py
```

### 3. Implement Missing Phase 1 Features
```bash
# Add job history filtering to client command
# Add retry mechanism with exponential backoff
# Update existing CLI tools with new features
# Ensure compatibility with current service ports (8000, 8001, 8006)
```

### 4. Create Tests
```bash
# Create test files in cli/tests/
# - test_cli_basic.py
# - test_client.py
# - test_miner.py  
# - test_wallet.py
# - test_auth.py
# - test_blockchain.py
# - test_marketplace.py
# - test_simulate.py

# Run tests
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ -v
```

### 5. Update Documentation
```bash
# Update CLI README
# Update project documentation
# Create command reference docs
# Update skills that use CLI commands
```

## Quick Commands

```bash
# Install CLI in development mode
cd /opt/aitbc
source venv/bin/activate
pip install -e cli/

# Test a specific command
./aitbc-cli --output json client blocks --limit 1

# Check wallet balance
./aitbc-cli wallet balance

# Check auth status
./aitbc-cli auth status

# Test blockchain commands
./aitbc-cli chain --help
./aitbc-cli node status

# Test marketplace commands
./aitbc-cli marketplace --action list

# Run all tests
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ -v

# Run specific test
python -m pytest cli/tests/test_cli_basic.py -v
```

## Current CLI Structure

### Existing Commands
```bash
# Working commands (verify these exist)
./aitbc-cli client          # Client operations
./aitbc-cli miner           # Miner operations  
./aitbc-cli wallet          # Wallet operations
./aitbc-cli auth            # Authentication
./aitbc-cli marketplace     # Marketplace operations (basic)
```

### Commands to Implement
```bash
# Phase 2 commands to create
./aitbc-cli chain           # Blockchain operations
./aitbc-cli node            # Node operations
./aitbc-cli transaction     # Transaction operations
./aitbc-cli simulate        # Simulation operations
```

## File Locations

### Current Structure
- **CLI Source**: `/opt/aitbc/cli/aitbc_cli/`
- **Commands**: `/opt/aitbc/cli/aitbc_cli/commands/`
- **Tests**: `/opt/aitbc/cli/tests/`
- **CLI Wrapper**: `/opt/aitbc/aitbc-cli`
- **Virtual Environment**: `/opt/aitbc/venv`

### Key Files
- **Main CLI**: `/opt/aitbc/cli/aitbc_cli/main.py`
- **Client Command**: `/opt/aitbc/cli/aitbc_cli/commands/client.py`
- **Wallet Command**: `/opt/aitbc/cli/aitbc_cli/commands/wallet.py`
- **Marketplace Command**: `/opt/aitbc/cli/aitbc_cli/commands/marketplace.py`
- **Test Runner**: `/opt/aitbc/cli/tests/run_cli_tests.py`

## Service Integration

### Current Service Endpoints
```bash
# Coordinator API
curl -s http://localhost:8000/health

# Exchange API  
curl -s http://localhost:8001/api/health

# Blockchain RPC
curl -s http://localhost:8006/health

# Ollama (for GPU operations)
curl -s http://localhost:11434/api/tags
```

### CLI Service Configuration
```bash
# Check current CLI configuration
./aitbc-cli --help

# Test with different output formats
./aitbc-cli --output json wallet balance
./aitbc-cli --output table wallet balance
./aitbc-cli --output yaml wallet balance
```

## Development Workflow

### 1. Environment Setup
```bash
cd /opt/aitbc
source venv/bin/activate
pip install -e cli/
```

### 2. Command Development
```bash
# Create new command
cd cli/aitbc_cli/commands/
cp template.py new_command.py

# Edit the command
# Add to main.py
# Add tests
```

### 3. Testing
```bash
# Run specific command tests
python -m pytest cli/tests/test_new_command.py -v

# Run all CLI tests
python -m pytest cli/tests/ -v

# Test with CLI runner
cd cli/tests
python run_cli_tests.py
```

### 4. Integration Testing
```bash
# Test against actual services
./aitbc-cli wallet balance
./aitbc-cli marketplace --action list
./aitbc-cli client status <job_id>
```

## Recent Updates (v2.1)

### Project Structure Changes
- **Consolidated Path**: Updated from `/home/oib/windsurf/aitbc` to `/opt/aitbc`
- **Virtual Environment**: Consolidated to `/opt/aitbc/venv`
- **CLI Wrapper**: Uses `/opt/aitbc/aitbc-cli` for all operations
- **Test Structure**: Updated to `/opt/aitbc/cli/tests/`

### Service Integration
- **Updated Ports**: Coordinator (8000), Exchange (8001), RPC (8006)
- **Service Health**: Added service health verification
- **Cross-Node**: Added cross-node operations support
- **Current Commands**: Updated to reflect actual CLI implementation

### Testing Integration
- **CI/CD Ready**: Integration with existing test workflows
- **Test Runner**: Custom CLI test runner
- **Environment**: Proper venv activation for testing
- **Coverage**: Enhanced test coverage requirements
