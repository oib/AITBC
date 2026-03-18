# AITBC CLI Reference

## Overview

The AITBC CLI provides a comprehensive command-line interface for interacting with the AITBC network. It supports job submission, mining operations, wallet management, blockchain queries, marketplace operations, system administration, and test simulations.

## Installation

```bash
cd /home/oib/windsurf/aitbc
pip install -e .
```

## Global Options

All commands support the following global options:

- `--url TEXT`: Coordinator API URL (overrides config)
- `--api-key TEXT`: API key (overrides config)
- `--output [table|json|yaml]`: Output format (default: table)
- `-v, --verbose`: Increase verbosity (use -v, -vv, -vvv)
- `--debug`: Enable debug mode
- `--config-file TEXT`: Path to config file
- `--help`: Show help message
- `--version`: Show version and exit

## Configuration

### Setting API Key

```bash
# Set API key for current session
export CLIENT_API_KEY=your_api_key_here

# Or set permanently
aitbc config set api_key your_api_key_here
```

### Setting Coordinator URL

```bash
aitbc config set coordinator_url http://localhost:8000
```

## Commands

### Client Commands

Submit and manage inference jobs.

```bash
# Submit a job
aitbc client submit --prompt "What is AI?" --model gpt-4

# Submit with retry (3 attempts, exponential backoff)
aitbc client submit --prompt "What is AI?" --retries 3 --retry-delay 2.0

# Check job status
aitbc client status <job_id>

# List recent blocks
aitbc client blocks --limit 10

# List receipts
aitbc client receipts --status completed

# Cancel a job
aitbc client cancel <job_id>

# Show job history
aitbc client history --status completed --limit 20
```

### Miner Commands

Register as a miner and process jobs.

```bash
# Register as miner
aitbc miner register --gpu-model RTX4090 --memory 24 --price 0.5

# Start polling for jobs
aitbc miner poll --interval 5

# Mine a specific job
aitbc miner mine <job_id>

# Send heartbeat
aitbc miner heartbeat

# Check miner status
aitbc miner status

# View earnings
aitbc miner earnings --from-time 2026-01-01 --to-time 2026-02-12

# Update GPU capabilities
aitbc miner update-capabilities --gpu RTX4090 --memory 24 --cuda-cores 16384

# Deregister miner
aitbc miner deregister --force

# List jobs with filtering
aitbc miner jobs --type inference --min-reward 0.5 --status completed

# Concurrent mining (multiple workers)
aitbc miner concurrent-mine --workers 4 --jobs 20
```

### Wallet Commands

Manage your AITBC wallet and transactions.

```bash
# Check balance
aitbc wallet balance

# Show earning history
aitbc wallet earn --limit 20

# Show spending history
aitbc wallet spend --limit 20

# Show full history
aitbc wallet history

# Get wallet address
aitbc wallet address

# Show wallet stats
aitbc wallet stats

# Send funds
aitbc wallet send <address> <amount>

# Request payment
aitbc wallet request-payment <from_address> <amount> --description "For services"

# Create a new wallet
aitbc wallet create my_wallet --type hd

# List wallets
aitbc wallet list

# Switch active wallet
aitbc wallet switch my_wallet

# Backup wallet
aitbc wallet backup my_wallet --destination ./backup.json

# Restore wallet
aitbc wallet restore ./backup.json restored_wallet

# Stake tokens
aitbc wallet stake 100.0 --duration 90

# Unstake tokens
aitbc wallet unstake <stake_id>

# View staking info
aitbc wallet staking-info

# Liquidity pool staking (APY tiers: bronze/silver/gold/platinum)
aitbc wallet liquidity-stake 100.0 --pool main --lock-days 30

# Withdraw from liquidity pool with rewards
aitbc wallet liquidity-unstake <stake_id>

# View all rewards (staking + liquidity)
aitbc wallet rewards
```

### Governance Commands

Governance proposals and voting.

```bash
# Create a general proposal
aitbc governance propose "Increase block size" --description "Raise limit to 2MB" --duration 7

# Create a parameter change proposal
aitbc governance propose "Block Size" --description "Change to 2MB" --type parameter_change --parameter block_size --value 2000000

# Create a funding proposal
aitbc governance propose "Dev Fund" --description "Fund Q2 development" --type funding --amount 10000

# Vote on a proposal
aitbc governance vote <proposal_id> for --voter alice --weight 1.0

# List proposals
aitbc governance list --status active

# View voting results
aitbc governance result <proposal_id>
```

### Monitor Commands (extended)

```bash
# List active incentive campaigns
aitbc monitor campaigns --status active

# View campaign performance metrics
aitbc monitor campaign-stats
aitbc monitor campaign-stats staking_launch
```

### Auth Commands

Manage API keys and authentication.

```bash
# Login with API key
aitbc auth login your_api_key_here

# Logout
aitbc auth logout

# Show current token
aitbc auth token

# Check auth status
aitbc auth status

# Refresh token
aitbc auth refresh

# Create new API key
aitbc auth keys create --name "My Key"

# List API keys
aitbc auth keys list

# Revoke API key
aitbc auth keys revoke <key_id>

# Import from environment
aitbc auth import-env CLIENT_API_KEY
```

### Blockchain Commands

Query blockchain information and status.

```bash
# List recent blocks
aitbc blockchain blocks --limit 10

# Get block details
aitbc blockchain block <block_hash>

# Get transaction details
aitbc blockchain transaction <tx_hash>

# Check node status
aitbc blockchain status --node 1

# Check sync status
aitbc blockchain sync-status

# List connected peers
aitbc blockchain peers

# Get blockchain info
aitbc blockchain info

# Check token supply
aitbc blockchain supply

# List validators
aitbc blockchain validators
```

### Marketplace Commands

GPU marketplace operations.

```bash
# Register GPU
aitbc marketplace gpu register --name "RTX4090" --memory 24 --price-per-hour 0.5

# List available GPUs
aitbc marketplace gpu list --available

# List with filters
aitbc marketplace gpu list --model RTX4090 --memory-min 16 --price-max 1.0

# Get GPU details
aitbc marketplace gpu details <gpu_id>

# Book a GPU
aitbc marketplace gpu book <gpu_id> --hours 2

# Release a GPU
aitbc marketplace gpu release <gpu_id>

# List orders
aitbc marketplace orders list --status active

# Get pricing info
aitbc marketplace pricing RTX4090

# Get GPU reviews
aitbc marketplace reviews <gpu_id>

# Add a review
aitbc marketplace review <gpu_id> --rating 5 --comment "Excellent performance"
```

### Admin Commands

System administration operations.

```bash
# Check system status
aitbc admin status

# List jobs
aitbc admin jobs list --status active

# Get job details
aitbc admin jobs details <job_id>

# Cancel job
aitbc admin jobs cancel <job_id>

# List miners
aitbc admin miners list --status active

# Get miner details
aitbc admin miners details <miner_id>

# Suspend miner
aitbc admin miners suspend <miner_id>

# Get analytics
aitbc admin analytics --period 24h

# View logs
aitbc admin logs --component coordinator --tail 100

# Run maintenance
aitbc admin maintenance cleanup --retention 7d

# Execute custom action
aitbc admin action custom --script backup.sh
```

### Config Commands

Manage CLI configuration.

```bash
# Show current config
aitbc config show

# Set configuration values
aitbc config set coordinator_url http://localhost:8000
aitbc config set timeout 30
aitbc config set api_key your_key

# Show config file path
aitbc config path

# Edit config file
aitbc config edit

# Reset configuration
aitbc config reset

# Export configuration
aitbc config export --format json > config.json

# Import configuration
aitbc config import config.json

# Validate configuration
aitbc config validate

# List environment variables
aitbc config environments

# Save profile
aitbc config profiles save production

# List profiles
aitbc config profiles list

# Load profile
aitbc config profiles load production

# Delete profile
aitbc config profiles delete production
```

### Simulate Commands

Run simulations and manage test users.

```bash
# Initialize test economy
aitbc simulate init --distribute 10000,5000

# Initialize with reset
aitbc simulate init --reset

# Create test user
aitbc simulate user create --type client --balance 1000

# List test users
aitbc simulate user list

# Check user balance
aitbc simulate user balance <user_id>

# Fund user
aitbc simulate user fund <user_id> --amount 500

# Run workflow simulation
aitbc simulate workflow --jobs 10 --duration 60

# Run load test
aitbc simulate load-test --users 20 --rps 100 --duration 300

# List scenarios
aitbc simulate scenario list

# Run scenario
aitbc simulate scenario run basic_workflow

# Get results
aitbc simulate results <simulation_id>

# Reset simulation
aitbc simulate reset
```

## Output Formats

All commands support three output formats:

- **table** (default): Human-readable table format
- **json**: Machine-readable JSON format
- **yaml**: Human-readable YAML format

Example:
```bash
# Table output (default)
aitbc wallet balance

# JSON output
aitbc --output json wallet balance

# YAML output
aitbc --output yaml wallet balance
```

## Environment Variables

The following environment variables are supported:

- `CLIENT_API_KEY`: Your API key for authentication
- `AITBC_COORDINATOR_URL`: Coordinator API URL
- `AITBC_OUTPUT_FORMAT`: Default output format
- `AITBC_CONFIG_FILE`: Path to configuration file

## Examples

### Basic Workflow

```bash
# 1. Configure CLI
export CLIENT_API_KEY=your_api_key
aitbc config set coordinator_url http://localhost:8000

# 2. Check wallet
aitbc wallet balance

# 3. Submit a job
job_id=$(aitbc --output json client submit inference --prompt "What is AI?" | jq -r '.job_id')

# 4. Check status
aitbc client status $job_id

# 5. Get results
aitbc client receipts --job-id $job_id
```

### Mining Operations

```bash
# 1. Register as miner
aitbc miner register --gpu-model RTX4090 --memory 24 --price 0.5

# 2. Start mining
aitbc miner poll --interval 5

# 3. Check earnings
aitbc wallet earn
```

### Marketplace Usage

```bash
# 1. Find available GPUs
aitbc marketplace gpu list --available --price-max 1.0

# 2. Book a GPU
aitbc marketplace gpu book gpu123 --hours 4

# 3. Use the GPU for your job
aitbc client submit inference --prompt "Generate image" --gpu gpu123

# 4. Release the GPU
aitbc marketplace gpu release gpu123

# 5. Leave a review
aitbc marketplace review gpu123 --rating 5 --comment "Great performance!"
```

## Troubleshooting

### Common Issues

1. **API Key Not Found**
   ```bash
   export CLIENT_API_KEY=your_api_key
   # or
   aitbc auth login your_api_key
   ```

2. **Connection Refused**
   ```bash
   # Check coordinator URL
   aitbc config show
   # Update if needed
   aitbc config set coordinator_url http://localhost:8000
   ```

3. **Permission Denied**
   ```bash
   # Check key permissions
   aitbc auth status
   # Refresh if needed
   aitbc auth refresh
   ```

### Debug Mode

Enable debug mode for detailed error information:

```bash
aitbc --debug client status <job_id>
```

### Verbose Output

Increase verbosity for more information:

```bash
aitbc -vvv wallet balance
```

## Integration

### Shell Scripts

```bash
#!/bin/bash
# Submit job and wait for completion
job_id=$(aitbc --output json client submit inference --prompt "$1" | jq -r '.job_id')
while true; do
    status=$(aitbc --output json client status $job_id | jq -r '.status')
    if [ "$status" = "completed" ]; then
        aitbc client receipts --job-id $job_id
        break
    fi
    sleep 5
done
```

### Python Integration

```python
import subprocess
import json

# Submit job
result = subprocess.run(
    ['aitbc', '--output', 'json', 'client', 'submit', 'inference', '--prompt', 'What is AI?'],
    capture_output=True, text=True
)
job_data = json.loads(result.stdout)
job_id = job_data['job_id']

# Check status
result = subprocess.run(
    ['aitbc', '--output', 'json', 'client', 'status', job_id],
    capture_output=True, text=True
)
status_data = json.loads(result.stdout)
print(f"Job status: {status_data['status']}")
```

## Support

For more help:
- Use `aitbc --help` for general help
- Use `aitbc <command> --help` for command-specific help
- Check the logs with `aitbc admin logs` for system issues
- Visit the documentation at https://docs.aitbc.net
