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
# Configure environment (no root .env.example exists — services read
# /etc/aitbc/*.env on deployed nodes; for local dev set env vars directly)

# Start blockchain node (use the repo venv interpreter + installed packages)
/opt/aitbc/venv/bin/python -m aitbc_chain.main

# Start coordinator API
/opt/aitbc/venv/bin/python -m uvicorn coordinator_api.main:app --port 8203

# Start market service
/opt/aitbc/venv/bin/python -m uvicorn market_service.main:app --port 8102
```

## Verification

```bash
# Check service health
curl http://localhost:8202/health  # Blockchain RPC
curl http://localhost:8203/health  # Coordinator
curl http://localhost:8102/health  # Market
```

## See Also

- [Prerequisites](../getting-started/installation/prerequisites.md) - System requirements
- [Single Server](single-server.md) - Production deployment
- [Configuration](configuration.md) - Environment configuration
