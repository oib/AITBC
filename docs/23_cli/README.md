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
# Load development environment
source /opt/aitbc/.env.dev

# Test CLI installation
aitbc --help
aitbc version
```

### Basic Operations
```bash
# Wallet operations
aitbc wallet create
aitbc wallet list
aitbc wallet balance

# Exchange operations
aitbc exchange register --name "Binance" --api-key <key>
aitbc exchange create-pair AITBC/BTC
aitbc exchange start-trading --pair AITBC/BTC

# Service management
aitbc-services status
aitbc-services restart
```

## 📋 **Command Groups**

### **Wallet Commands**
- `wallet create` - Create new wallet
- `wallet list` - List all wallets
- `wallet balance` - Check wallet balance
- `wallet send` - Send tokens
- `wallet address` - Get wallet address
- `wallet history` - Transaction history
- `wallet backup` - Backup wallet
- `wallet restore` - Restore wallet

### **Exchange Commands**
- `exchange register` - Register with exchange
- `exchange create-pair` - Create trading pair
- `exchange start-trading` - Start trading
- `exchange stop-trading` - Stop trading
- `exchange status` - Exchange status
- `exchange balances` - Exchange balances

### **Blockchain Commands**
- `blockchain info` - Blockchain information
- `blockchain status` - Node status
- `blockchain blocks` - List blocks
- `blockchain balance` - Check balance
- `blockchain peers` - Network peers
- `blockchain transaction` - Transaction details

### **Config Commands**
- `config show` - Show configuration
- `config get <key>` - Get config value
- `config set <key> <value>` - Set config value
- `config edit` - Edit configuration
- `config validate` - Validate configuration

### **Compliance Commands**
- `compliance list-providers` - List KYC providers
- `compliance kyc-submit` - Submit KYC verification
- `compliance kyc-status` - Check KYC status
- `compliance aml-screen` - AML screening
- `compliance full-check` - Full compliance check

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
# Load development environment
source /opt/aitbc/.env.dev

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
aitbc --debug wallet list

# Test mode
aitbc --test-mode exchange status

# Custom configuration
aitbc --config-file /path/to/config wallet list
```

### Service Integration
```bash
# Custom API endpoint
aitbc --url http://localhost:8000 blockchain status

# Custom API key
aitbc --api-key <key> exchange register --name "Exchange"

# Timeout configuration
aitbc --timeout 60 blockchain info
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
- [Permission Setup](./permission-setup.md) - Development environment configuration
- [Service Management](../8_development/) - Service operation guides
- [Exchange Integration](../19_marketplace/) - Exchange and trading documentation

---

**Last Updated**: March 8, 2026  
**CLI Version**: 0.1.0  
**Test Coverage**: 67/67 tests passing (100%)  
**Infrastructure**: Complete
