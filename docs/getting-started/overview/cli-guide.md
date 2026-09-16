# AITBC CLI Getting Started Guide

**Last Updated:** 2026-05-28

**Complete Command Line Interface Setup and Usage**

> **Note:** This document describes the CLI usage for the AITBC platform. For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## 🚀 **Quick Start**

### Prerequisites

- Linux system (Debian 13+ recommended)
- Python 3.13+ installed
- System access (for initial setup)

### Installation

```bash
# 1. Navigate to AITBC directory
cd /opt/aitbc

# 2. Test CLI installation
aitbc --help
aitbc version

# 3. Verify services are running
systemctl list-units --state=running | grep aitbc
```

## 🔧 **Development Environment Setup**

### Permission Configuration

```bash
# Fix permissions (one-time setup)
/opt/aitbc/scripts/clean-permissions-fix.sh

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
aitbc wallet create --name "my-wallet"

# List wallets
aitbc wallet list

# Check balance
aitbc wallet balance --name "my-wallet"
```

### Exchange Operations

```bash
# Note: Exchange operations may require additional setup
# Check exchange status via API
curl -s http://localhost:8106/health
```

### Blockchain Operations

```bash
# Get blockchain info
aitbc blockchain status

# Check node status
aitbc network status

# Check balance
aitbc wallet balance --name "my-wallet"
```

## 🛠️ **Advanced Usage**

### Output Formats

```bash
# Table output (default)
aitbc wallet list

# JSON output
aitbc --output json blockchain status
```

### Debug Mode

```bash
# Enable debug output
aitbc --debug blockchain status

# Test service connectivity
curl -s http://localhost:8202/health
curl -s http://localhost:8203/health
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
systemctl restart aitbc-blockchain-node.service

# View logs
journalctl -u aitbc-blockchain-node.service -f
```

#### Command Not Found

```bash
# Check CLI installation
ls -la /usr/local/bin/aitbc

# Activate virtual environment
source /opt/aitbc/venv/bin/activate

# Check dependencies
/opt/aitbc/scripts/utils/check-dependencies.sh
```

#### API Connection Issues

```bash
# Check service endpoints
curl -s http://localhost:8202/health
curl -s http://localhost:8203/health
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

- Complete CLI Reference
- Testing Procedures
- [Permission Setup](../../cli/permission-setup.md)
- [Exchange Integration](../../apps/exchange/exchange.md)

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
aitbc version

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
**Test Coverage**: See ROADMAP.md for current test coverage targets
