# AITBC Training Environment Setup Skill

## Overview

Specializes in setting up and managing the AITBC training environment using the Python-based setup system. Handles environment prerequisites, wallet funding, messaging configuration, and schema-driven stage execution.

## Installation

If you're running the CLI from inside a virtualenv / container, the `aitbc` package needs to be on `sys.path`. Easiest way:

```bash
pip install -e /opt/aitbc
```

or, if you prefer not to install globally:

```bash
export PYTHONPATH=/opt/aitbc:$PYTHONPATH
```

After that, the CLI can be invoked with:

```bash
python3 -m aitbc.training_setup.cli <command>
```

Note: The CLI script automatically adds the parent directory to sys.path for importability.

## Core Operations

### Environment Setup

```bash
# Setup complete training environment
python3 -m aitbc.training_setup.cli setup

# Check prerequisites
python3 -m aitbc.training_setup.cli check

# Verify environment
python3 -m aitbc.training_setup.cli verify
```

### Wallet Management

```bash
# Fund a specific wallet
python3 -m aitbc.training_setup.cli fund-wallet my-wallet --password my-password
```

### Schema-Driven Stage Execution

```bash
# Run a training stage from JSON schema
python3 -m aitbc.training_setup.cli run-stage /path/to/stage.json
```

## Python API Usage

```python
from aitbc.training_setup import TrainingEnvironment

# Create environment with deterministic wallet naming
env = TrainingEnvironment(
    aitbc_dir="/opt/aitbc",
    log_dir="/var/log/aitbc/training-setup",
    faucet_amount=1000,
    wallet_prefix="training-w"
)

# Setup full environment
results = env.setup_full_environment()

# Run stage from JSON
result = env.run_stage_from_json("/path/to/stage.json")

# Get deterministic wallet names
wallet1 = env.get_wallet_name(1)  # training-w1
wallet2 = env.get_wallet_name(2)  # training-w2
```

## Schema-Driven Stage Execution

### Stage JSON Format

```json
{
  "stage": 1,
  "title": "Foundation – Wallets & Accounts",
  "prerequisites": ["AITBC node running", "Genesis wallet funded"],
  "commands": [
    {
      "cmd": "wallet create",
      "args": ["training-w1", "--password", "abc123"],
      "exit_code": 0
    },
    {
      "cmd": "wallet send",
      "args": ["--password", "", "genesis", "training-w1", "100"],
      "exit_code": 0
    }
  ],
  "expected": {
    "wallet_exists": {"type": "value", "value": true},
    "balance": {"type": "value", "value": {"symbol": "AIT", "amount": 100}}
  }
}
```

### Transaction Hash Validation

The stage runner automatically extracts transaction hashes from command output. Check results for `tx_hash` field:

```python
result = env.run_stage_from_json("/path/to/stage.json")
for cmd_result in result['commands']:
    if cmd_result.get('tx_hash'):
        print(f"Transaction: {cmd_result['tx_hash']}")
```

## Messaging Configuration

Messaging configuration is attempted but non-fatal. If it fails, the setup continues with a warning. Core blockchain operations don't require messaging.

The messaging command uses the canonical form:
```bash
./aitbc-cli agent message --wallet <wallet_name> --password <password> --auth-token <token>
```

## Current Limitations & Workarounds

### Funding Issues
- Locally created wallets aren't automatically funded on-chain
- Workaround: Use the pre-funded genesis wallet (999,999,890 AIT) for initial transactions
- Example: `/opt/aitbc/aitbc-cli wallet send --password "" genesis <target> <amount>`

### Genesis Initialization
- The `--force` flag causes CLI errors
- Workaround: Genesis block already exists, so initialization skips automatically

### Messaging Configuration
- May have CLI argument mismatches
- Workaround: Messaging is optional; focus on core blockchain operations first

## Troubleshooting

### Import Errors

If you get "ModuleNotFoundError: No module named 'aitbc'", ensure:
1. Package is installed: `pip install -e /opt/aitbc`
2. Or PYTHONPATH is set: `export PYTHONPATH=/opt/aitbc:$PYTHONPATH`

### Funding Failures

Check that:
- Genesis wallet exists and is funded (pre-funded with 999,999,890 AIT)
- AITBC node is running
- Network connectivity is available

### Messaging Warnings

Messaging configuration is optional. If it fails, the setup continues with a warning. Check logs in `/var/log/aitbc/training-setup/training_setup.log` for details.

## Best Practices

1. **Use Deterministic Wallet Names:** Use `get_wallet_name(index)` for consistent wallet naming
2. **Check Prerequisites First:** Always call `check_prerequisites()` before setup
3. **Verify After Setup:** Call `verify_environment()` to confirm setup success
4. **Handle Exceptions:** Use try/except blocks with specific exception types
5. **Review Logs:** Check logs in `/var/log/aitbc/training-setup/` for debugging
6. **Schema-Driven Execution:** Use JSON stage definitions for reproducible training

## Next Steps

1. Install the package or set `PYTHONPATH`.
2. Run `python3 -m aitbc.training_setup.cli setup` to confirm the flow.
3. If the messaging command fails, check the `token` value and wallet password matches the wallet you created.
