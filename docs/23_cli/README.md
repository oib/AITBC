# AITBC CLI Documentation

## Overview

The AITBC CLI is a comprehensive command-line interface for interacting with the AITBC network. It provides enhanced features for clients, miners, agents, and platform operators with complete testing integration and multi-chain support.

## 📋 Testing Integration

### **Testing Skill**
For comprehensive testing capabilities and automated test execution, see the **AITBC Testing Skill**:
```
/windsurf/skills/test
```

### **Test Workflow**
For step-by-step testing procedures and CLI testing guidance, see:
```
/windsurf/workflows/test
```

### **Test Documentation**
For detailed CLI testing scenarios and multi-chain testing, see:
```
docs/10_plan/89_test.md
```

### **Test Suite**
Complete CLI test suite located at:
```
tests/cli/
├── test_agent_commands.py      # Agent command testing
├── test_wallet.py              # Wallet command testing
├── test_marketplace.py         # Marketplace command testing
└── test_cli_integration.py     # CLI integration testing
```

## Installation

```bash
# From monorepo root
pip install -e .

# Verify installation
aitbc --version
aitbc --help

# Test CLI installation
python -c "from aitbc_cli.main import cli; print('CLI import successful')"
```

## Testing the CLI

### **Installation Testing**
```bash
# Test CLI import and basic functionality
cd /home/oib/windsurf/aitbc/cli
source venv/bin/activate
python -c "from aitbc_cli.main import cli; print('CLI import successful')"

# Run CLI help commands
python -m aitbc_cli --help
python -m aitbc_cli agent --help
python -m aitbc_cli wallet --help
python -m aitbc_cli marketplace --help
```

### **Automated Testing**
```bash
# Run all CLI tests
python -m pytest tests/cli/ -v

# Run specific CLI test categories
python -m pytest tests/cli/test_agent_commands.py -v
python -m pytest tests/cli/test_wallet.py -v
python -m pytest tests/cli/test_marketplace.py -v
python -m pytest tests/cli/test_cli_integration.py -v

# Run comprehensive test suite
./tests/run_all_tests.sh
```

### **Multi-Chain Testing**
```bash
# Test multi-chain CLI functionality
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain chains

# Test CLI connectivity to coordinator
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key health

# Execute multi-chain test scenarios
python -m pytest tests/integration/test_multichain.py -v
```

## Quick Start

### Basic Setup
```bash
# Configure CLI
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key

# Test connectivity
aitbc blockchain status
aitbc --config
```

### Create Wallet
```bash
aitbc wallet create --name my-wallet
aitbc wallet balance
```

## Command Groups

### 🔗 Blockchain Operations
```bash
# Status and synchronization
aitbc blockchain status
aitbc blockchain sync
aitbc blockchain info

# Network information
aitbc blockchain peers
aitbc blockchain blocks --limit 10
aitbc blockchain validators

# Multi-chain operations
aitbc blockchain chains
aitbc blockchain genesis --chain-id ait-devnet
aitbc blockchain send --chain-id ait-healthchain --from alice --to bob --data "test"
```

# Transaction operations
aitbc blockchain transaction <TX_ID>
```

### 👛 Wallet Management
```bash
# Wallet operations
aitbc wallet create --name my-wallet
aitbc wallet balance
aitbc wallet send --to <ADDRESS> --amount 1.0
aitbc wallet stake --amount 10.0

# Multi-signature wallets
aitbc wallet multisig-create --participants alice,bob,charlie --threshold 2
aitbc wallet backup --name my-wallet
```

### 🤖 Agent Operations
```bash
# Agent workflows
aitbc agent workflow create \
  --name "ai_inference" \
  --description "AI inference workflow" \
  --config '{"model": "gpt2", "type": "inference"}'

aitbc agent execute ai_inference \
  --input '{"prompt": "Hello world"}' \
  --priority normal

# Agent learning and optimization
aitbc agent learning enable --agent-id agent_123 \
  --mode performance --auto-tune

# Agent networks
aitbc agent network create \
  --name "compute_network" \
  --type "resource_sharing"
```

### 🚀 OpenClaw Deployment
```bash
# Application deployment
aitbc openclaw deploy \
  --name "web_app" \
  --image "nginx:latest" \
  --replicas 3 \
  --region "us-west"

# Deployment management
aitbc openclaw status web_app
aitbc openclaw optimize web_app \
  --target performance --auto-tune

# Edge deployments
aitbc openclaw edge deploy \
  --name "edge_service" \
  --compute "gpu" \
  --region "edge_location"
```

### ⚡ Optimization Features
```bash
# Enable agent optimization
aitbc optimize enable --agent-id agent_123 \
  --mode performance --auto-tune

# Get recommendations
aitbc optimize recommendations --agent-id agent_123

# Apply optimizations
aitbc optimize apply --agent-id agent_123 \
  --recommendation-id rec_456

# Predictive scaling
aitbc optimize predict --agent-id agent_123 \
  --metric cpu_usage --horizon 1h

# Auto-tuning
aitbc optimize tune --agent-id agent_123 \
  --objective performance \
  --constraints '{"cost": "<100"}'
```

### 🏪 Marketplace Operations
```bash
# List available resources
aitbc marketplace list
aitbc marketplace gpu list

# Register GPU offers
aitbc marketplace offer create \
  --miner-id gpu_miner_123 \
  --gpu-model "RTX-4090" \
  --gpu-memory "24GB" \
  --price-per-hour "0.05" \
  --models "gpt2,llama" \
  --endpoint "http://localhost:11434"

# Rent GPUs
aitbc marketplace gpu rent --gpu-id gpu_789 --duration 2h

# Order management
aitbc marketplace orders --status active
aitbc marketplace reviews --miner-id gpu_miner_123
```

### 👤 Client Operations
```bash
# Job submission
aitbc client submit \
  --prompt "What is AI?" \
  --model gpt2 \
  --priority normal \
  --timeout 3600

# Job management
aitbc client status --job-id <JOB_ID>
aitbc client list --status completed
aitbc client download --job-id <JOB_ID> --output ./results

# Batch operations
aitbc client batch-submit --jobs-file jobs.json
aitbc client cancel --job-id <JOB_ID>
```

### ⛏️ Miner Operations
```bash
# Miner registration
aitbc miner register \
  --name my-gpu \
  --gpu v100 \
  --count 1 \
  --region us-west \
  --price-per-hour 0.05

# Mining operations
aitbc miner poll
aitbc miner status
aitbc miner earnings --period daily

# Advanced features
aitbc miner deregister --miner-id my-gpu
```

### 🔧 Configuration Management
```bash
# Basic configuration
aitbc config show
aitbc config set coordinator_url http://localhost:8000
aitbc config get api_key

# Configuration profiles
aitbc config profiles create development
aitbc config profiles set development gpu_count 4
aitbc config profiles use development

# Secrets management
aitbc config secrets set api_key your_secret_key
aitbc config secrets get api_key
```

### 📊 Monitoring and Debugging
```bash
# Debug information
aitbc --debug
aitbc --config

# Monitoring dashboard
aitbc monitor dashboard
aitbc monitor metrics --component cli

# Alerts and notifications
aitbc monitor alerts --type gpu_temperature
aitbc monitor webhooks create --url http://localhost:8080/webhook
```

### 🧪 Simulation and Testing
```bash
# Workflow simulation
aitbc simulate workflow --test-scenario basic
aitbc simulate load-test --concurrent-users 10

# Scenario testing
aitbc simulate scenario --name market_stress_test
```

## Global Options

| Option | Description |
|--------|-------------|
| `--url URL` | Coordinator API URL |
| `--api-key KEY` | API key for authentication |
| `--output table\|json\|yaml` | Output format |
| `-v / -vv / -vvv` | Verbosity level |
| `--debug` | Debug mode with system information |
| `--config` | Show current configuration |

## Configuration Files

### Default Configuration Location
- **Linux/macOS**: `~/.config/aitbc/config.yaml`
- **Windows**: `%APPDATA%\aitbc\config.yaml`

### Environment Variables
```bash
export AITBC_API_KEY=your-api-key
export AITBC_COORDINATOR_URL=http://localhost:8000
export AITBC_OUTPUT_FORMAT=table
export AITBC_LOG_LEVEL=INFO
```

## Troubleshooting

### Common Issues

```bash
# Check CLI installation
aitbc --version

# Test connectivity
aitbc blockchain status

# Verify configuration
aitbc --config

# Debug mode
aitbc --debug
```

### Performance Issues

```bash
# Check system resources
aitbc monitor metrics --component system

# Optimize CLI performance
aitbc config set cache_enabled true
aitbc config set parallel_requests 4
```

### Network Issues

```bash
# Test API connectivity
curl http://localhost:8000/health/live

# Check coordinator status
aitbc blockchain status

# Verify API endpoints
aitbc config show
```

## Best Practices

1. **Use configuration profiles** for different environments
2. **Enable debug mode** when troubleshooting issues
3. **Monitor performance** with the built-in dashboard
4. **Use batch operations** for multiple similar tasks
5. **Secure your API keys** with secrets management
6. **Regular backups** of wallet configurations

## Advanced Features

### Custom Workflows
```bash
# Create custom agent workflow
aitbc agent workflow create \
  --name custom_pipeline \
  --description "Custom processing pipeline" \
  --config '{"steps": ["preprocess", "inference", "postprocess"]}'

# Execute with custom parameters
aitbc agent execute custom_pipeline \
  --input '{"data": "sample"}' \
  --workflow-config '{"batch_size": 32}'
```

### Automation Scripts
```bash
#!/bin/bash
# Example automation script

# Check wallet balance
BALANCE=$(aitbc wallet balance --output json | jq '.balance')

if [ "$BALANCE" -lt 1.0 ]; then
    echo "Low balance detected"
    aitbc monitor alerts create --type low_balance --message "Wallet balance below 1.0 AITBC"
fi

# Check miner status
aitbc miner status
aitbc monitor metrics --component gpu
```

### Integration with Other Tools
```bash
# Pipe results to other tools
aitbc marketplace gpu list --output json | jq '.[] | select(.price_per_hour < 0.05)'

# Use in scripts
for gpu in $(aitbc marketplace gpu list --output json | jq -r '.[].gpu_id'); do
    echo "Processing GPU: $gpu"
    # Additional processing
done
```

## Migration from Old CLI

If you're migrating from the previous CLI version:

1. **Update installation**: `pip install -e .`
2. **Migrate configuration**: Old config files should work, but new features are available
3. **Check new commands**: `aitbc --help` to see all available commands
4. **Test connectivity**: `aitbc blockchain status` to verify connection

## Support and Community

- **Documentation**: [Full documentation](../README.md)
- **Issues**: [GitHub Issues](https://github.com/aitbc/aitbc/issues)
- **Community**: [Discord/Forum links]
- **Updates**: Check `aitbc --version` for current version

---

*This documentation covers the enhanced AITBC CLI with all new features and capabilities.*
