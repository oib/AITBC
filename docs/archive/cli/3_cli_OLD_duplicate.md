# AITBC CLI Getting Started Guide

**Complete Command Line Interface Setup and Usage**

## 🚀 **Quick Start**

### Prerequisites
- Linux system (Debian 13+ recommended)
- Python 3.13+ installed
- System access (sudo for initial setup)

### Installation
```bash
# 1. Load development environment
source /opt/aitbc/.env.dev

# 2. Test CLI installation
aitbc --help
aitbc version

# 3. Verify services are running
aitbc-services status
```

## 🔧 **Development Environment Setup**

### Permission Configuration
```bash
# Fix permissions (one-time setup)
sudo /opt/aitbc/scripts/clean-sudoers-fix.sh

# Test permissions
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

## 📋 **Basic Operations**

### Wallet Management
```bash
# Create new wallet
aitbc wallet create --name "my-wallet"

# List wallets
aitbc wallet list

# Check balance
aitbc wallet balance --wallet "my-wallet"

# Get address
aitbc wallet address --wallet "my-wallet"
```

### Exchange Operations
```bash
# Register with exchange
aitbc exchange register --name "Binance" --api-key <your-api-key>

# Create trading pair
aitbc exchange create-pair AITBC/BTC

# Start trading
aitbc exchange start-trading --pair AITBC/BTC

# Check exchange status
aitbc exchange status
```

### Blockchain Operations
```bash
# Get blockchain info
aitbc blockchain info

# Check node status
aitbc blockchain status

# List recent blocks
aitbc blockchain blocks --limit 10

# Check balance
aitbc blockchain balance --address <address>
```

## 🛠️ **Advanced Usage**

### Output Formats
```bash
# JSON output
aitbc --output json wallet balance

# YAML output
aitbc --output yaml blockchain info

# Table output (default)
aitbc wallet list
```

### Debug Mode
```bash
# Enable debug output
aitbc --debug wallet list

# Test mode (uses mock data)
aitbc --test-mode exchange status

# Custom timeout
aitbc --timeout 60 blockchain info
```

### Configuration
```bash
# Show current configuration
aitbc config show

# Get specific config value
aitbc config get coordinator_url

# Set config value
aitbc config set timeout 30

# Edit configuration
aitbc config edit
```

## 🔍 **Troubleshooting**

### Common Issues

#### Permission Denied
```bash
# Fix permissions
/opt/aitbc/scripts/fix-permissions.sh

# Test permissions
/opt/aitbc/scripts/test-permissions.sh
```

#### Service Not Running
```bash
# Check service status
aitbc-services status

# Restart services
aitbc-services restart

# View logs
aitbc-logs
```

#### Command Not Found
```bash
# Check CLI installation
which aitbc

# Load environment
source /opt/aitbc/.env.dev

# Check PATH
echo $PATH | grep aitbc
```

#### API Connection Issues
```bash
# Test with debug mode
aitbc --debug blockchain status

# Test with custom URL
aitbc --url http://localhost:8000 blockchain info

# Check service endpoints
curl http://localhost:8000/health
```

### Debug Mode
```bash
# Enable debug for any command
aitbc --debug <command>

# Check configuration
aitbc config show

# Test service connectivity
aitbc --test-mode blockchain status
```

## 📚 **Next Steps**

### Explore Features
1. **Wallet Operations**: Try creating and managing wallets
2. **Exchange Integration**: Register with exchanges and start trading
3. **Blockchain Operations**: Explore blockchain features
4. **Compliance**: Set up KYC/AML verification

### Advanced Topics
1. **Market Making**: Configure automated trading
2. **Oracle Integration**: Set up price feeds
3. **Security**: Implement multi-sig and time-lock
4. **Development**: Build custom tools and integrations

### Documentation
- [Complete CLI Reference](../23_cli/README.md)
- [Testing Procedures](../23_cli/testing.md)
- [Permission Setup](../23_cli/permission-setup.md)
- [Exchange Integration](../19_marketplace/exchange_integration.md)

## 🎯 **Tips and Best Practices**

### Development Workflow
```bash
# 1. Load environment
source /opt/aitbc/.env.dev

# 2. Check services
aitbc-services status

# 3. Test CLI
aitbc version

# 4. Start development
aitbc wallet create
```

### Security Best Practices
- Use strong passwords for wallet encryption
- Enable multi-sig for large amounts
- Keep API keys secure
- Regular backup of wallets
- Monitor compliance requirements

### Performance Tips
- Use appropriate output formats for automation
- Leverage test mode for development
- Cache frequently used data
- Monitor service health

---

**Last Updated**: March 8, 2026  
**CLI Version**: 0.1.0  
**Test Coverage**: 67/67 tests passing (100%)
