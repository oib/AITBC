---
title: Development Setup
description: Set up your development environment for AITBC
---

# Development Setup

This guide helps you set up a development environment for building on AITBC.

## Prerequisites

- Python 3.13.5+
- Git
- PostgreSQL 15+ and Redis 7+ (for full local services)
- Node.js 18+ (for frontend development)

## Local Development

### 1. Clone Repository

```bash
git clone https://github.com/aitbc/aitbc.git
cd aitbc
```

### 2. Install Dependencies

```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies using the declarative profile (e.g. hub)
./scripts/deployment/install-profiles.sh hub

# Install the CLI in editable mode
pip install -e cli/
```

### 3. Start Services

```bash
# Start PostgreSQL and Redis
sudo systemctl start postgresql redis-server

# Run the setup script for a local node
sudo ./scripts/deployment/setup.sh

# Or start a specific service manually from its app directory
python -m apps.blockchain-node.src.aitbc_chain.main
```

### 4. Verify Setup

```bash
# Check services
aitbc status

# Run tests
pytest
```

## IDE Setup

### VS Code

Install extensions:

- Python
- GitLens

### PyCharm

Configure Python interpreter to use `venv` and enable pre-commit.

## Environment Variables

Create `.env` file:

```bash
AITBC_API_KEY=your_dev_key
AITBC_BASE_URL=http://localhost:8203
AITBC_NETWORK=testnet
```

## Next Steps

- [API Authentication](../architecture/3_coordinator-api.md#authentication)
- [Getting Started](../getting-started/README.md)
- [Scenarios](../scenarios/README.md)
