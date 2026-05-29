# Local Development Setup

This guide covers setting up AITBC for local development and testing.

## Quick Start

```bash
# Clone repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install local packages
pip install -e packages/py/aitbc-crypto
pip install -e packages/py/aitbc-sdk

# Start services
./scripts/deployment/setup.sh
```

## Service Configuration

```bash
# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start blockchain node
python -m apps.blockchain_node.main

# Start coordinator API
python -m apps.coordinator_api.main

# Start marketplace service
python -m apps.marketplace_service.main
```

## Verification

```bash
# Check service health
curl http://localhost:8006/health  # Blockchain RPC
curl http://localhost:8011/health  # Coordinator
curl http://localhost:8102/health  # Marketplace
```

## See Also

- [Prerequisites](prerequisites.md) - System requirements
- [Single Server](single-server.md) - Production deployment
- [Configuration](configuration.md) - Environment configuration
