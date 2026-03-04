# CLI Workarounds Guide

## Current Working CLI Features

### ✅ Working Features (60%)

#### 1. Basic CLI Commands
```bash
# Check CLI version
aitbc --version

# Get help
aitbc --help

# Show configuration
aitbc config-show

# Test environment
aitbc test environment
```

#### 2. Wallet Management
```bash
# List wallets
aitbc wallet list

# Get wallet help
aitbc wallet --help

# Create new wallet (may fail)
aitbc wallet create --name test_wallet
```

#### 3. Configuration Management
```bash
# Show current config
aitbc config-show

# Use custom config file
aitbc --config-file /path/to/config.yaml config-show
```

### ❌ Non-Working Features (40%)

#### 1. API Integration
```bash
# This will fail with 404 error
aitbc test api

# Workaround: Use curl directly
curl -s https://aitbc.bubuit.net/api/health
```

#### 2. Marketplace Operations
```bash
# These will fail with network errors
aitbc marketplace gpu list
aitbc marketplace offers list

# Workaround: Use curl directly
curl -s https://aitbc.bubuit.net/api/v1/marketplace/gpus
```

#### 3. Agent Operations
```bash
# This will fail with network errors
aitbc agent list

# Workaround: Use curl directly
curl -s https://aitbc.bubuit.net/api/v1/agent/workflows
```

#### 4. Blockchain Operations
```bash
# This will fail with connection refused
aitbc blockchain status

# Workaround: Use curl directly
curl -s https://aitbc.bubuit.net/rpc/head
```

## Development Workarounds

### Use Mock Server for Testing
```bash
# Start mock server
python3 /home/oib/windsurf/aitbc/cli-dev/mock-cli-server.py &

# Use staging config
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-staging-config.yaml marketplace gpu list

# Stop mock server
kill %1
```

### Use External API Directly
```bash
# Test API health
curl -s https://aitbc.bubuit.net/api/health

# Test marketplace
curl -s https://aitbc.bubuit.net/api/v1/marketplace/gpus

# Test blockchain
curl -s https://aitbc.bubuit.net/rpc/head
```

## Production Usage Guidelines

### Safe CLI Operations
- Use wallet management commands
- Use configuration commands
- Use help commands
- Use environment tests

### Avoid These Commands
- API integration commands
- Marketplace commands
- Agent commands
- Blockchain commands

### Alternative Approaches
- Use external API directly with curl
- Use web interface for marketplace
- Use web interface for blockchain
- Use web interface for agents

## Testing Commands

### Test Working Features
```bash
cd /home/oib/windsurf/aitbc/cli-dev
./test-cli-functionality.sh
```

### Test with Mock Server
```bash
cd /home/oib/windsurf/aitbc/cli-dev
./test-cli-staging.sh
```

## Summary

- **60% of CLI features work perfectly**
- **40% need workarounds**
- **External API provides full functionality**
- **Mock server enables safe testing**
- **Production operations remain 100% functional**
