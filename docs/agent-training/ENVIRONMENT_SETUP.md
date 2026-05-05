# Training Environment Setup Guide

This guide explains how to set up the AITBC training environment using the Python-based setup system, which replaces the previous shell script approach.

## Overview

The Python-based training environment setup provides:
- **Testability:** Can be unit tested and integrated tested
- **Maintainability:** Python code is easier to debug and maintain
- **Integration:** Uses existing AITBC patterns and utilities
- **Type Safety:** Better error handling with exceptions
- **IDE Support:** Autocomplete and type hints
- **CI/CD Integration:** Easier to integrate with pytest-based CI
- **Schema-Driven Execution:** JSON-based stage definitions for reproducible training
- **Deterministic Wallet Naming:** Predictable wallet names for consistent testing
- **Transaction Hash Validation:** Automatic extraction and validation of transaction hashes

## Installation

The training setup module is located in `aitbc/training_setup/`. To use it, you need to either install the AITBC package or add the directory to your Python path.

**Option 1: Install the package (recommended):**
```bash
cd /opt/aitbc
pip install -e .
```

**Option 2: Add to Python path:**
```bash
export PYTHONPATH="/opt/aitbc:$PYTHONPATH"
```

**Option 3: Use directly with path:**
```bash
cd /opt/aitbc
python3 -c "import sys; sys.path.insert(0, '.'); from aitbc.training_setup import TrainingEnvironment"
```

## Quick Start

### Using the CLI

```bash
# Setup complete training environment
python -m aitbc.training_setup.cli setup

# Check prerequisites
python -m aitbc.training_setup.cli check

# Verify environment
python -m aitbc.training_setup.cli verify

# Fund a specific wallet
python -m aitbc.training_setup.cli fund-wallet my-wallet --password my-password

# Run a training stage from JSON schema
python -m aitbc.training_setup.cli run-stage /path/to/stage.json
```

### Using Python API

```python
from aitbc.training_setup import TrainingEnvironment

# Create environment
env = TrainingEnvironment(
    aitbc_dir="/opt/aitbc",
    log_dir="/var/log/aitbc/training-setup",
    faucet_amount=1000,
    genesis_allocation=10000,
)

# Setup full environment
results = env.setup_full_environment()
print(results)

# Fund a specific wallet
env.fund_training_wallet("training-wallet", "password123")

# Configure messaging
env.configure_messaging_auth("training-wallet", "password123")

# Verify environment
verification = env.verify_environment()
print(verification)

# Run a stage from JSON schema
result = env.run_stage_from_json("/path/to/stage.json")
print(result)

# Get deterministic wallet name
wallet_name = env.get_wallet_name(1)  # training-w1
print(f"Wallet name: {wallet_name}")
```

### Using Pytest Fixtures

For testing and CI/CD integration, use the pytest fixtures:

```python
import pytest
from aitbc.training_setup import TrainingEnvironment

def test_training_setup(training_env_mock):
    """Test with mocked environment"""
    result = training_env_mock.fund_training_wallet("test-wallet")
    assert result["status"] == "completed"

@pytest.mark.integration
def test_real_setup(training_env):
    """Test with real environment"""
    result = training_env.check_prerequisites()
    assert result is True
```

## Schema-Driven Stage Execution

The training setup supports schema-driven stage execution using JSON definitions. This approach provides:

- **Reproducibility:** Each stage runs the same way with the same commands
- **Validation:** Expected conditions are automatically validated
- **Transaction Tracking:** Transaction hashes are extracted and logged
- **Test Integration:** Stages can be run as pytest tests

### Stage JSON Schema

```json
{
  "stage": 1,
  "title": "Foundation – Wallets & Accounts",
  "prerequisites": [
    "AITBC node running",
    "Genesis wallet funded"
  ],
  "commands": [
    {
      "cmd": "wallet create",
      "args": ["training-w1", "--password", "abc123"],
      "exit_code": 0
    },
    {
      "cmd": "wallet list",
      "args": [],
      "re": "training-w1"
    },
    {
      "cmd": "wallet send",
      "args": ["--password", "", "genesis", "training-w1", "100"],
      "exit_code": 0
    }
  ],
  "expected": {
    "wallet_exists": {
      "type": "value",
      "value": true
    },
    "balance": {
      "type": "value",
      "value": {"symbol": "AIT", "amount": 100}
    }
  }
}
```

### Running Stages

**CLI:**
```bash
python -m aitbc.training_setup.cli run-stage /path/to/stage.json
```

**Python API:**
```python
from aitbc.training_setup import TrainingEnvironment

env = TrainingEnvironment()
result = env.run_stage_from_json("/path/to/stage.json")
print(result)
```

### Deterministic Wallet Naming

The training environment uses deterministic wallet naming for consistency:

```python
# Get wallet names by index
env = TrainingEnvironment(wallet_prefix="training-w")
wallet1 = env.get_wallet_name(1)  # training-w1
wallet2 = env.get_wallet_name(2)  # training-w2
wallet3 = env.get_wallet_name(3)  # training-w3
```

This ensures predictable wallet names across different training sessions and environments.

### Transaction Hash Validation

The stage runner automatically extracts transaction hashes from command output:

```python
result = env.run_stage_from_json("/path/to/stage.json")
for cmd_result in result['commands']:
    if cmd_result.get('tx_hash'):
        print(f"Transaction: {cmd_result['tx_hash']}")
```

## Components

### TrainingEnvironment Class

The main class that manages training environment setup.

**Methods:**
- `check_prerequisites()` - Verify AITBC CLI and node are available
- `create_genesis_allocation()` - Create genesis wallet and initialize blockchain
- `setup_faucet_wallet()` - Setup and fund faucet wallet
- `fund_training_wallet(wallet_name, password)` - Fund a specific wallet
- `generate_auth_token()` - Generate authentication token
- `configure_messaging_auth(wallet_name, password)` - Configure messaging
- `test_messaging_connectivity()` - Test messaging service
- `verify_environment()` - Verify all components are configured
- `setup_full_environment()` - Run complete setup process

### Exceptions

Custom exceptions for error handling:
- `TrainingSetupError` - Base exception for setup errors
- `FundingError` - Account funding failures
- `MessagingError` - Messaging configuration failures
- `FaucetError` - Faucet setup failures
- `PrerequisitesError` - Prerequisites not met

### Pytest Fixtures

Available in `tests/conftest.py`:
- `training_env` - Session-scoped real environment fixture
- `training_env_mock` - Function-scoped mocked environment fixture
- `mock_faucet_response` - Mock faucet API response
- `training_stage_data` - Sample training stage data

## Configuration

### Environment Variables

The setup system respects standard AITBC environment variables:
- `AITBC_DIR` - AITBC installation directory (default: `/opt/aitbc`)
- `DATA_DIR` - Data directory
- `LOG_DIR` - Log directory

### Custom Parameters

```python
env = TrainingEnvironment(
    aitbc_dir="/custom/path",           # AITBC directory
    log_dir="/custom/logs",              # Log directory
    faucet_amount=1000,                 # Tokens per faucet request
    genesis_allocation=10000,           # Genesis allocation amount
)
```

## Logging

Logs are written to `/var/log/aitbc/training-setup/training_setup.log` by default.

Log levels:
- `INFO` - Normal operations
- `WARNING` - Non-critical issues
- `ERROR` - Failures that prevent setup completion

## Migration from Shell Scripts

The shell scripts in `/opt/aitbc/scripts/training/` are maintained for backward compatibility but are deprecated.

**Migration Guide:**

| Shell Script | Python Equivalent |
|--------------|-------------------|
| `setup_training_env.sh` | `TrainingEnvironment().setup_full_environment()` |
| `fund_accounts.sh` | `TrainingEnvironment().fund_training_wallet()` |
| `configure_messaging.sh` | `TrainingEnvironment().configure_messaging_auth()` |
| `setup_faucet.sh` | Manual setup or use existing faucet service |

## Testing

### Unit Tests

```bash
pytest tests/training/test_training_setup.py -v
```

### Integration Tests

```bash
pytest tests/training/test_training_setup.py -v -m integration
```

### With Mocked Environment

```bash
pytest tests/training/test_training_setup.py -v -k "mock"
```

## Troubleshooting

### Prerequisites Not Met

**Error:** `TrainingSetupError: AITBC CLI not found`

**Solution:** Ensure AITBC is installed at the specified directory:
```bash
ls /opt/aitbc/aitbc-cli
```

### Funding Failures

**Error:** `FundingError: Failed to fund wallet`

**Solution:** Check that:
- Genesis wallet exists and is funded (pre-funded with 999,999,890 AIT)
- AITBC node is running
- Network connectivity is available

**Note:** Locally created wallets aren't automatically funded on-chain. The setup system uses the pre-funded genesis wallet as the funding source.

### Messaging Failures

**Error:** Messaging configuration warnings

**Solution:** Messaging configuration is optional. If it fails, the setup continues with a warning. Core blockchain operations don't require messaging. Check logs in `/var/log/aitbc/training-setup/training_setup.log` for details.

### Genesis Initialization Errors

**Error:** CLI errors when using `--force` flag for genesis initialization

**Solution:** Genesis block already exists, so initialization is automatically skipped. The setup system checks genesis wallet status instead of attempting initialization.

## Best Practices

1. **Use Mocked Environment for Tests:** Use `training_env_mock` fixture for unit tests
2. **Check Prerequisites First:** Always call `check_prerequisites()` before setup
3. **Verify After Setup:** Call `verify_environment()` to confirm setup success
4. **Handle Exceptions:** Use try/except blocks with specific exception types
5. **Use Session Fixture:** Use `training_env` for expensive setup operations
6. **Log Review:** Check logs in `/var/log/aitbc/training-setup/` for debugging

## Examples

### Complete Setup Script

```python
#!/usr/bin/env python3
from aitbc.training_setup import TrainingEnvironment, TrainingSetupError

def main():
    try:
        env = TrainingEnvironment()
        
        # Check prerequisites
        env.check_prerequisites()
        
        # Setup full environment
        results = env.setup_full_environment()
        
        # Verify setup
        verification = env.verify_environment()
        
        print("Setup completed successfully")
        print(f"Results: {results}")
        print(f"Verification: {verification}")
        
    except TrainingSetupError as e:
        print(f"Setup failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
```

### Selective Setup

```python
from aitbc.training_setup import TrainingEnvironment

env = TrainingEnvironment()

# Only setup funding
env.create_genesis_allocation()
env.setup_faucet_wallet()
env.fund_training_wallet("training-wallet")

# Only setup messaging
env.configure_messaging_auth("training-wallet")
env.test_messaging_connectivity()
```

### Test Fixture Usage

```python
import pytest

def test_wallet_funding(training_env_mock):
    """Test wallet funding with mocked environment"""
    result = training_env_mock.fund_training_wallet("test-wallet")
    assert result["status"] == "completed"
    assert result["amount"] == 1000

def test_messaging_setup(training_env_mock):
    """Test messaging configuration"""
    result = training_env_mock.configure_messaging_auth("test-wallet")
    assert result["status"] == "completed"
    assert "token_file" in result
```

## Related Documentation

- [Training Schema](training_schema.json) - JSON schema for training data
- [Stage 1 Foundation](stage1_foundation.json) - Stage 1 training configuration
- [Operations Audit](OPERATIONS_AUDIT.md) - Operations coverage analysis
- [Test Suite README](../../../tests/README.md) - Testing infrastructure

## Support

For issues or questions:
1. Check logs in `/var/log/aitbc/training-setup/`
2. Run with verbose logging
3. Review test examples in `tests/training/`
4. Check AITBC documentation in `/opt/aitbc/docs/`
