# AITBC CLI Getting Started Guide

**Complete Command Line Interface Setup and Usage**

> **Note:** This document describes the CLI usage for the AITBC platform. For the current operational state and deployment status, see [Current Operational State](../../infrastructure/CURRENT_OPERATIONAL_STATE.md). For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## 🚀 **Quick Start**

### Prerequisites
- Linux system (Debian 13+ recommended)
- Python 3.13+ installed
- System access (sudo for initial setup)

### Installation
```bash
# 1. Navigate to AITBC directory
cd /opt/aitbc

# 2. Test CLI installation
/opt/aitbc/aitbc-cli --help
/opt/aitbc/aitbc-cli --version

# 3. Verify services are running
systemctl list-units --state=running | grep aitbc
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
# Activate Python virtual environment
source /opt/aitbc/venv/bin/activate

# Check dependencies
/opt/aitbc/scripts/utils/check-dependencies.sh
```

## 📋 **Basic Operations**

### Wallet Management
```bash
# Create new wallet
/opt/aitbc/aitbc-cli create --name "my-wallet" --password "password123"

# List wallets
/opt/aitbc/aitbc-cli list

# Check balance
/opt/aitbc/aitbc-cli balance --name "my-wallet"
```

### Exchange Operations
```bash
# Note: Exchange operations may require additional setup
# Check exchange status via API
curl -s http://localhost:8001/health
```

### Blockchain Operations
```bash
# Get blockchain info
/opt/aitbc/aitbc-cli chain

# Check node status
/opt/aitbc/aitbc-cli network

# Check balance
/opt/aitbc/aitbc-cli balance --name "my-wallet"
```

## 🛠️ **Advanced Usage**

### Output Formats
```bash
# Table output (default)
/opt/aitbc/aitbc-cli list

# JSON output (if supported)
/opt/aitbc/aitbc-cli chain --output json
```

### Debug Mode
```bash
# Enable debug output (if supported)
/opt/aitbc/aitbc-cli --debug chain

# Test service connectivity
curl -s http://localhost:8006/health
curl -s http://localhost:8011/health
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
systemctl list-units --state=running | grep aitbc

# Restart services
sudo systemctl restart aitbc-blockchain-node.service

# View logs
journalctl -u aitbc-blockchain-node.service -f
```

#### Command Not Found
```bash
# Check CLI installation
ls -la /opt/aitbc/aitbc-cli

# Activate virtual environment
source /opt/aitbc/venv/bin/activate

# Check dependencies
/opt/aitbc/scripts/utils/check-dependencies.sh
```

#### API Connection Issues
```bash
# Check service endpoints
curl -s http://localhost:8006/health
curl -s http://localhost:8011/health
curl -s http://localhost:8102/health

# Check service status
systemctl status aitbc-coordinator-api.service
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
# 1. Navigate to AITBC directory
cd /opt/aitbc

# 2. Activate virtual environment
source venv/bin/activate

# 3. Check services
systemctl list-units --state=running | grep aitbc

# 4. Test CLI
/opt/aitbc/aitbc-cli --version

# 5. Check dependencies
./scripts/utils/check-dependencies.sh
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

**Last Updated**: May 28, 2026
**CLI Version**: Current
**Test Coverage**: See [ROADMAP.md](../../planning/ROADMAP.md) for current test coverage targets
