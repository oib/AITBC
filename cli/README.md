# AITBC CLI - Command Line Interface

A powerful and comprehensive command-line interface for interacting with the AITBC (AI Training & Blockchain Computing) network.

## Installation

```bash
# Clone the repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc

# Install in development mode
pip install -e .

# Or install from PyPI (when published)
pip install aitbc-cli
```

## Quick Start

1. **Set up your API key**:
   ```bash
   export CLIENT_API_KEY=your_api_key_here
   # Or save permanently
   aitbc config set api_key your_api_key_here
   ```

2. **Check your wallet**:
   ```bash
   aitbc wallet balance
   ```

3. **Submit your first job**:
   ```bash
   aitbc client submit inference --prompt "What is AI?" --model gpt-4
   ```

## Features

- 🚀 **Fast & Efficient**: Optimized for speed with minimal overhead
- 🎨 **Rich Output**: Beautiful tables, JSON, and YAML output formats
- 🔐 **Secure**: Built-in credential management with keyring
- 📊 **Comprehensive**: 40+ commands covering all aspects of the network
- 🧪 **Testing Ready**: Full simulation environment for testing
- 🔧 **Extensible**: Easy to add new commands and features

## Command Groups

### Client Operations
Submit and manage inference jobs:
```bash
aitbc client submit inference --prompt "Your prompt here" --model gpt-4
aitbc client status <job_id>
aitbc client history --status completed
```

### Mining Operations
Register as a miner and process jobs:
```bash
aitbc miner register --gpu-model RTX4090 --memory 24 --price 0.5
aitbc miner poll --interval 5
```

### Wallet Management
Manage your AITBC tokens:
```bash
aitbc wallet balance
aitbc wallet send <address> <amount>
aitbc wallet history
```

### Authentication
Manage API keys and authentication:
```bash
aitbc auth login your_api_key
aitbc auth status
aitbc auth keys create --name "My Key"
```

### Blockchain Queries
Query blockchain information:
```bash
aitbc blockchain blocks --limit 10
aitbc blockchain transaction <tx_hash>
aitbc blockchain sync-status
```

### Marketplace
GPU marketplace operations:
```bash
aitbc marketplace gpu list --available
aitbc marketplace gpu book <gpu_id> --hours 2
aitbc marketplace reviews <gpu_id>
```

### System Administration
Admin operations (requires admin privileges):
```bash
aitbc admin status
aitbc admin analytics --period 24h
aitbc admin logs --component coordinator
```

### Configuration
Manage CLI configuration:
```bash
aitbc config show
aitbc config set coordinator_url http://localhost:8000
aitbc config profiles save production
```

### Simulation
Test and simulate operations:
```bash
aitbc simulate init --distribute 10000,5000
aitbc simulate user create --type client --name testuser
aitbc simulate workflow --jobs 10
```

## Output Formats

All commands support multiple output formats:

```bash
# Table format (default)
aitbc wallet balance

# JSON format
aitbc --output json wallet balance

# YAML format
aitbc --output yaml wallet balance
```

## Global Options

These options can be used with any command:

- `--url TEXT`: Override coordinator URL
- `--api-key TEXT`: Override API key
- `--output [table|json|yaml]`: Output format
- `-v, --verbose`: Increase verbosity (use -vv, -vvv for more)
- `--debug`: Enable debug mode
- `--config-file TEXT`: Path to config file
- `--help`: Show help
- `--version`: Show version

## Shell Completion

Enable tab completion for bash/zsh:

```bash
# For bash
echo 'source /path/to/aitbc_shell_completion.sh' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'source /path/to/aitbc_shell_completion.sh' >> ~/.zshrc
source ~/.zshrc
```

## Configuration

The CLI can be configured in multiple ways:

1. **Environment variables**:
   ```bash
   export CLIENT_API_KEY=your_key
   export AITBC_COORDINATOR_URL=http://localhost:8000
   export AITBC_OUTPUT_FORMAT=json
   ```

2. **Config file**:
   ```bash
   aitbc config set coordinator_url http://localhost:8000
   aitbc config set api_key your_key
   ```

3. **Profiles**:
   ```bash
   # Save a profile
   aitbc config profiles save production
   
   # Switch profiles
   aitbc config profiles load production
   ```

## Examples

### Basic Workflow

```bash
# 1. Configure
export CLIENT_API_KEY=your_key

# 2. Check balance
aitbc wallet balance

# 3. Submit job
job_id=$(aitbc --output json client submit inference --prompt "What is AI?" | jq -r '.job_id')

# 4. Monitor progress
watch -n 5 "aitbc client status $job_id"

# 5. Get results
aitbc client receipts --job-id $job_id
```

### Mining Setup

```bash
# 1. Register as miner
aitbc miner register \
    --gpu-model RTX4090 \
    --memory 24 \
    --price 0.5 \
    --region us-west

# 2. Start mining
aitbc miner poll --interval 5

# 3. Check earnings
aitbc wallet earn
```

### Using the Marketplace

```bash
# 1. Find available GPUs
aitbc marketplace gpu list --available --price-max 1.0

# 2. Book a GPU
gpu_id=$(aitbc marketplace gpu list --available --output json | jq -r '.[0].id')
aitbc marketplace gpu book $gpu_id --hours 4

# 3. Use it for your job
aitbc client submit inference \
    --prompt "Generate an image of a sunset" \
    --model stable-diffusion \
    --gpu $gpu_id

# 4. Release when done
aitbc marketplace gpu release $gpu_id
```

### Testing with Simulation

```bash
# 1. Initialize test environment
aitbc simulate init --distribute 10000,5000

# 2. Create test users
aitbc simulate user create --type client --name alice --balance 1000
aitbc simulate user create --type miner --name bob --balance 500

# 3. Run workflow simulation
aitbc simulate workflow --jobs 10 --rounds 3

# 4. Check results
aitbc simulate results sim_123
```

## Troubleshooting

### Common Issues

1. **"API key not found"**
   ```bash
   export CLIENT_API_KEY=your_key
   # or
   aitbc auth login your_key
   ```

2. **"Connection refused"**
   ```bash
   # Check coordinator URL
   aitbc config show
   # Update if needed
   aitbc config set coordinator_url http://localhost:8000
   ```

3. **"Permission denied"**
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

## Contributing

We welcome contributions! Please see our [Contributing Guide](../CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .[dev]

# Run tests
pytest tests/cli/

# Run with local changes
python -m aitbc_cli.main --help
```

## Support

- 📖 [Documentation](../docs/cli-reference.md)
- 🐛 [Issue Tracker](https://github.com/aitbc/aitbc/issues)
- 💬 [Discord Community](https://discord.gg/aitbc)
- 📧 [Email Support](mailto:support@aitbc.net)

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

---

Made with ❤️ by the AITBC team
