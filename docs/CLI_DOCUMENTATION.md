# AITBC CLI Documentation

**Project Status**: ✅ **100% COMPLETED** (v0.3.0 - April 2, 2026)

## Overview

The AITBC CLI (Command Line Interface) is a comprehensive tool for managing the AITBC blockchain network, AI operations, marketplace interactions, agent workflows, and advanced economic intelligence operations. With the 100% project completion, the CLI now provides complete system management capabilities with enterprise-grade security, monitoring, and type safety.

## 🎉 **100% Project Completion Status**

### **✅ All CLI Systems: Fully Operational**
- **System Architecture Commands**: FHS compliance and directory management
- **Service Management Commands**: Single marketplace service control
- **Security Commands**: JWT authentication and API key management
- **Agent System Commands**: Multi-agent coordination and AI/ML operations
- **API Commands**: 17 endpoints with full functionality
- **Test Commands**: Comprehensive test suite execution
- **Monitoring Commands**: Prometheus metrics and alerting
- **Type Safety Commands**: MyPy checking and validation

### **🚀 Production CLI Features**
- **Authentication Management**: JWT token operations
- **Service Control**: Start/stop/restart services
- **Monitoring**: Real-time metrics and health checks
- **Security**: API key generation and validation
- **Testing**: Complete test suite execution
- **System Status**: Comprehensive system health reporting

## 🚀 **New in v0.3.0: Complete System Integration**

### **Enterprise Security Commands**
- **JWT Authentication**: Token generation, validation, refresh
- **RBAC Management**: Role assignment and permission control
- **API Key Management**: Generation, validation, revocation
- **Rate Limiting**: User-specific quota management

### **Production Monitoring Commands**
- **Metrics Collection**: Prometheus metrics retrieval
- **Alert Management**: Rule configuration and notification setup
- **SLA Monitoring**: Compliance tracking and reporting
- **Health Monitoring**: System and service health checks

### **Type Safety Commands**
- **MyPy Checking**: Strict type validation
- **Coverage Reports**: Type coverage analysis
- **Code Quality**: Formatting and linting

## Installation

### Prerequisites
- Python 3.13+
- Virtual environment at `/opt/aitbc/venv`
- AITBC services running on ports 8000, 8001, 8006

### Setup
```bash
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli --version
```

## Command Structure

### Core Commands

#### Wallet Management
```bash
# Create new wallet
./aitbc-cli create --name wallet-name --password your-password

# List all wallets
./aitbc-cli list

# Get wallet balance
./aitbc-cli balance --name wallet-name

# Send AIT
./aitbc-cli send --from from-wallet --to to-wallet --amount 100 --password your-password

# Get wallet transactions
./aitbc-cli transactions --name wallet-name --limit 10
```

#### Blockchain Operations
```bash
# Get blockchain information
./aitbc-cli chain [--rpc-url http://localhost:8006]

# Get network status
./aitbc-cli network

# Get blockchain analytics
./aitbc-cli analytics
```

#### AI Operations
```bash
# Submit AI job
./aitbc-cli ai-submit --wallet wallet-name --type inference --prompt "Generate image" --payment 100

# Check AI job status
./aitbc-cli ai-ops --action status --job-id job-id

# Get AI job results
./aitbc-cli ai-ops --action results --job-id job-id

# Advanced AI Operations - Phase 1 Completed
./aitbc-cli ai-submit --wallet genesis-ops --type parallel --prompt "Complex AI pipeline for medical diagnosis" --payment 500
./aitbc-cli ai-submit --wallet genesis-ops --type ensemble --prompt "Parallel AI processing with ensemble validation" --payment 600

# Advanced AI Operations - Phase 2 Completed
./aitbc-cli ai-submit --wallet genesis-ops --type multimodal --prompt "Multi-modal customer feedback analysis with cross-modal attention" --payment 1000
./aitbc-cli ai-submit --wallet genesis-ops --type fusion --prompt "Cross-modal fusion with joint reasoning and consensus validation" --payment 1200

# Advanced AI Operations - Phase 3 Completed
./aitbc-cli ai-submit --wallet genesis-ops --type resource-allocation --prompt "Dynamic resource allocation system with GPU pools and demand forecasting" --payment 800
./aitbc-cli ai-submit --wallet genesis-ops --type performance-tuning --prompt "AI performance optimization for sub-100ms inference latency" --payment 1000
```

#### Marketplace Operations
```bash
# List marketplace items
./aitbc-cli marketplace --action list

# Create marketplace listing
./aitbc-cli marketplace --action create --name "Service Name" --price 100 --description "Description" --wallet wallet-name

# Search marketplace
./aitbc-cli marketplace --action search --query "search term"

# View my listings
./aitbc-cli marketplace --action my-listings --wallet wallet-name
```

#### Resource Management
```bash
# Get resource status
./aitbc-cli resource --action status

# Allocate resources
./aitbc-cli resource --action allocate --agent-id agent-name --cpu 4 --memory 8192 --duration 3600
```

#### Mining Operations
```bash
# Start mining
./aitbc-cli mine-start

# Stop mining
./aitbc-cli mine-stop

# Check mining status
./aitbc-cli mine-status
```

### Advanced Commands

#### Agent Operations
```bash
# Run agent workflow
./aitbc-cli agent --agent agent-name --message "Task description" --thinking high

# OpenClaw operations
./aitbc-cli openclaw --action status
```

#### Workflow Operations
```bash
# Run workflow
./aitbc-cli workflow --name workflow-name --parameters "param1=value1,param2=value2"
```

#### Simulation Commands
```bash
# Simulate blockchain
./aitbc-cli simulate blockchain --blocks 10 --transactions 50 --delay 1.0

# Simulate wallets
./aitbc-cli simulate wallets --wallets 5 --balance 1000 --transactions 20

# Simulate price movements
./aitbc-cli simulate price --price 100 --volatility 0.05 --timesteps 100

# Simulate network
./aitbc-cli simulate network --nodes 3 --network-delay 0.1 --failure-rate 0.05

# Simulate AI jobs
./aitbc-cli simulate ai-jobs --jobs 10 --models "text-generation,image-generation" --duration-range "30-300"
```

## Configuration

### Environment Variables
```bash
export AITBC_COORDINATOR_URL="http://localhost:8000"
export AITBC_API_KEY="your-api-key"
export AITBC_RPC_URL="http://localhost:8006"
```

### Configuration File
The CLI uses configuration from `/etc/aitbc/.env` by default.

### Command Line Options
```bash
# Output format
./aitbc-cli --output table|json|yaml|csv command

# Verbose output
./aitbc-cli --verbose command

# Debug mode
./aitbc-cli --debug command

# Test mode
./aitbc-cli --test-mode command

# Dry run
./aitbc-cli --dry-run command

# Custom timeout
./aitbc-cli --timeout 60 command

# Skip SSL verification (testing only)
./aitbc-cli --no-verify command
```

## Service Integration

### Service Endpoints
- **Coordinator API**: http://localhost:8000
- **Exchange API**: http://localhost:8001
- **Blockchain RPC**: http://localhost:8006
- **Ollama**: http://localhost:11434

### Health Checks
```bash
# Check all services
curl -s http://localhost:8000/health
curl -s http://localhost:8001/api/health
curl -s http://localhost:8006/health
curl -s http://localhost:11434/api/tags
```

## Examples

### Basic Workflow
```bash
# 1. Create wallet
./aitbc-cli create --name my-wallet --password my-password

# 2. Fund wallet (from existing wallet)
./aitbc-cli send --from genesis-ops --to my-wallet --amount 1000 --password 123

# 3. Submit AI job
./aitbc-cli ai-submit --wallet my-wallet --type inference --prompt "Generate a landscape image" --payment 50

# 4. Check job status
./aitbc-cli ai-ops --action status --job-id latest

# 5. Get results
./aitbc-cli ai-ops --action results --job-id latest
```

### Marketplace Operations
```bash
# 1. Create service listing
./aitbc-cli marketplace --action create --name "AI Image Generation" --price 100 --description "High-quality image generation service" --wallet provider-wallet

# 2. List available services
./aitbc-cli marketplace --action list

# 3. Bid on service
./aitbc-cli marketplace --action bid --service-id service-id --amount 120 --wallet customer-wallet

# 4. Accept bid
./aitbc-cli marketplace --action accept-bid --service-id service-id --bid-id bid-id --wallet provider-wallet
```

### Simulation Examples
```bash
# Simulate blockchain with 100 blocks
./aitbc-cli simulate blockchain --blocks 100 --transactions 100 --delay 0.1

# Simulate price volatility
./aitbc-cli simulate price --price 100 --volatility 0.1 --timesteps 1000

# Simulate network failures
./aitbc-cli simulate network --nodes 5 --failure-rate 0.1 --network-delay 0.5
```

## Troubleshooting

### Common Issues

#### Command Not Found
```bash
# Check CLI installation
./aitbc-cli --version

# Check virtual environment
source venv/bin/activate
```

#### Service Connection Errors
```bash
# Check service status
systemctl status aitbc-coordinator-api.service
systemctl status aitbc-exchange-api.service
systemctl status aitbc-blockchain-node.service

# Check network connectivity
curl -s http://localhost:8000/health
```

#### Permission Errors
```bash
# Check file permissions
ls -la /opt/aitbc/aitbc-cli

# Fix permissions
chmod +x /opt/aitbc/aitbc-cli
```

### Debug Mode
```bash
# Enable debug output
./aitbc-cli --debug --verbose command

# Test with mock data
./aitbc-cli --test-mode command
```

## Development

### Running Tests
```bash
# Run all tests
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ -v

# Run specific test
python -m pytest cli/tests/test_cli_comprehensive.py::TestSimulateCommand -v

# Run with coverage
python -m pytest cli/tests/ --cov=cli --cov-report=html
```

### Adding New Commands
1. Create command file in `cli/aitbc_cli/commands/`
2. Import command in `cli/core/main.py`
3. Add tests in `cli/tests/`
4. Update documentation

### Code Style
```bash
# Format code
black cli/

# Lint code
flake8 cli/

# Type checking
mypy cli/
```

## API Reference

### Command Options

#### Global Options
- `--url`: Override coordinator URL
- `--api-key`: Set API key
- `--output`: Set output format (table, json, yaml, csv)
- `--verbose`: Increase verbosity
- `--debug`: Enable debug mode
- `--test-mode`: Use test endpoints
- `--dry-run`: Show what would be done
- `--timeout`: Set request timeout
- `--no-verify`: Skip SSL verification

#### Command-Specific Options
Each command has specific options documented in the help:
```bash
./aitbc-cli command --help
```

### Exit Codes
- `0`: Success
- `1`: General error
- `2`: Command line error

## Version History

### v0.2.2 (Current)
- Unified CLI with 20+ commands
- Enhanced output formatting
- AI operations integration
- Marketplace functionality
- Resource management
- Simulation commands
- OpenClaw agent integration

### v0.2.1
- Project consolidation to `/opt/aitbc`
- Enhanced service integration
- Improved error handling

### v0.2.0
- Modular command structure
- Enhanced configuration management
- Performance improvements

### v0.1.0
- Initial CLI implementation
- Basic wallet and blockchain operations

## Support

For issues and questions:
1. Check troubleshooting section
2. Run with `--debug --verbose` for detailed output
3. Check service health status
4. Review logs in `/var/log/aitbc/`

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation
6. Submit pull request
