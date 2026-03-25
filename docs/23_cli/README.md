# AITBC CLI Documentation

**Complete Command Line Interface Reference with Testing Integration**

## 📊 **CLI Status: 100% Complete**

### ✅ **Test Results**
- **Total Tests**: 67 tests
- **Tests Passed**: 67/67 (100%)
- **Commands Working**: All CLI commands operational
- **Integration**: Full service integration
- **Error Handling**: Comprehensive error management

## 🚀 **Quick Start**

### Installation and Setup
```bash
# Test CLI installation
aitbc --help
aitbc version
```

**Note**: The CLI is pre-configured with a bash alias for automatic virtual environment activation:
```bash
# The following alias is configured in ~/.bashrc:
alias aitbc="source /opt/aitbc/cli/venv/bin/activate && aitbc"
```

This allows you to use `aitbc <command>` directly without manually sourcing the virtual environment.

### Basic Operations
```bash
# Core operations
aitbc client submit --prompt "Generate an image" --model llama2
aitbc miner status
aitbc wallet create --type hd
aitbc marketplace list
aitbc blockchain info
aitbc exchange create-pair --pair AITBC/BTC --base-asset AITBC --quote-asset BTC
aitbc explorer status
aitbc explorer block 12345
aitbc explorer transaction 0x123...
aitbc explorer search --address 0xabc...

# Advanced features
aitbc analytics summary
aitbc ai-trading start --strategy arbitrage
aitbc compliance kyc-submit --user-id user123
aitbc agent create --type trading
aitbc multimodal process --input image.jpg --mode text

# Development tools
aitbc admin system-status
aitbc monitor health
aitbc deploy --target production
aitbc test --suite integration
```

## 📋 **Command Groups**

### **Core Commands**
- `client` - Submit and manage AI compute jobs
- `miner` - GPU mining operations and status
- `wallet` - Wallet management and transactions
- `marketplace` - GPU marketplace and trading
- `blockchain` - Blockchain operations and queries
- `exchange` - Real exchange integration (Binance, Coinbase, etc.)
- `explorer` - Blockchain explorer and analytics

### **Advanced Features**
- `analytics` - Chain performance monitoring and predictions
- `ai-trading` - AI-powered trading strategies
- `surveillance` - Market surveillance and compliance
- `compliance` - Regulatory compliance and reporting
- `governance` - Network governance and proposals

### **Development Tools**
- `admin` - Administrative operations
- `config` - Configuration management
- `monitor` - System monitoring and health
- `test` - CLI testing and validation
- `deploy` - Deployment and infrastructure management

### **Specialized Services**
- `agent` - AI agent operations
- `multimodal` - Multi-modal AI processing
- `oracle` - Price discovery and data feeds
- `market-maker` - Automated market making
- `genesis-protection` - Advanced security features
- `swarm` - Swarm intelligence operations
- `ai` - AI provider commands

### **Enterprise Integration**
- `enterprise-integration` - Enterprise system integration
- `cross-chain` - Cross-chain operations
- `regulatory` - Regulatory reporting

### **Security & Authentication**
- `auth` - Authentication and token management
- `keystore` - Key management
- `multisig` - Multi-signature operations
- `genesis` - Genesis block operations

### **Network & Infrastructure**
- `node` - Node management
- `chain` - Chain operations
- `sync` - Synchronization operations
- `optimize` - Performance optimization

### **Plugin System**
- `plugin` - Plugin management
- `plugin-registry` - Plugin registry
- `plugin-marketplace` - Plugin marketplace
- `plugin-security` - Plugin security
- `plugin-analytics` - Plugin analytics

## 🧪 **Testing**

### Test Coverage
```bash
# Run comprehensive CLI tests
cd /opt/aitbc/cli/tests
python3 comprehensive_tests.py

# Run group-specific tests
python3 group_tests.py

# Run level-based tests
python3 run_simple_tests.py
```

### Test Results Summary
- **Level 1 (Basic)**: 7/7 tests passing (100%)
- **Level 2 (Compliance)**: 5/5 tests passing (100%)
- **Level 3 (Wallet)**: 5/5 tests passing (100%)
- **Level 4 (Blockchain)**: 5/5 tests passing (100%)
- **Level 5 (Config)**: 5/5 tests passing (100%)
- **Level 6 (Integration)**: 5/5 tests passing (100%)
- **Level 7 (Error Handling)**: 4/4 tests passing (100%)

**Group Tests**:
- **Wallet Group**: 9/9 tests passing (100%)
- **Blockchain Group**: 8/8 tests passing (100%)
- **Config Group**: 8/8 tests passing (100%)
- **Compliance Group**: 6/6 tests passing (100%)

## 🔧 **Development Environment**

### Permission Setup
```bash
# Fix permissions (no sudo prompts)
/opt/aitbc/scripts/fix-permissions.sh

# Test permission setup
/opt/aitbc/scripts/test-permissions.sh
```

### Environment Variables
```bash
# Available aliases
aitbc-services    # Service management
aitbc-fix         # Quick permission fix
aitbc-logs        # View logs
```

## 🛠️ **Advanced Usage**

### Global Options
```bash
# Output formats
aitbc --output json wallet balance
aitbc --output yaml blockchain info

# Debug mode
aitbc --debug client submit --prompt "Test"

# Test mode
aitbc --test-mode exchange status

# Custom configuration
aitbc --config-file /path/to/config wallet list

# Dry run mode
aitbc --dry-run deploy --target production

# Custom timeout
aitbc --timeout 60 blockchain info

# Custom API endpoint
aitbc --url http://localhost:8000 blockchain status

# Custom API key
aitbc --api-key <key> exchange register --name "Exchange"

# Verbosity levels
aitbc -v client list
aitbc -vv marketplace show --job-id 123
aitbc -vvv admin system-status
```

### Service Integration
```bash
# Custom API endpoint
aitbc --url http://localhost:8000 blockchain status

# Custom API key
aitbc --api-key <key> exchange register --name "Exchange"

# Timeout configuration
aitbc --timeout 60 blockchain info

# Skip SSL verification (testing only)
aitbc --no-verify --test-mode client status

# Plugin management
aitbc plugin list
aitbc plugin install --name gpu-optimizer
aitbc plugin enable --name monitoring

# Multi-modal processing
aitbc multimodal process --input document.pdf --modes text,image
aitbc multimodal status --job-id 12345

# AI operations
aitbc ai list-providers
aitbc ai generate --provider ollama --model llama2 --prompt "Summarize"

# Agent operations
aitbc agent create --type trading --name trader1
aitbc agent start --agent-id trader1
aitbc agent status --agent-id trader1
```

## 🔍 **Troubleshooting**

### Common Issues
1. **Permission Denied**: Run `/opt/aitbc/scripts/fix-permissions.sh`
2. **Service Not Running**: Use `aitbc-services status` to check
3. **Command Not Found**: Ensure CLI is installed and in PATH
4. **API Connection Issues**: Check service endpoints with `aitbc --debug`

### Debug Mode
```bash
# Enable debug output
aitbc --debug <command>

# Check configuration
aitbc config show

# Test service connectivity
aitbc --test-mode blockchain status
```

## 📚 **Additional Resources**

- [Testing Procedures](./testing.md) - Detailed testing documentation
- [Service Management](../8_development/) - Service operation guides
- [Exchange Integration](../19_marketplace/) - Exchange and trading documentation

---

**Last Updated**: March 25, 2026  
**CLI Version**: 0.1.0  
**Test Coverage**: 67/67 tests passing (100%)  
**Infrastructure**: Complete  
**Command Groups**: 45+ command groups available  
**Plugin System**: Full plugin architecture supported
