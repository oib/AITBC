---
title: Development Setup
description: Set up your development environment for AITBC
---

# Development Setup

This guide helps you set up a development environment for building on AITBC.

## Prerequisites

- Python 3.8+
- Git
- Docker (optional)
- Node.js 16+ (for frontend development)

## Local Development

### 1. Clone Repository
```bash
git clone https://github.com/aitbc/aitbc.git
cd aitbc
```

### 2. Install Dependencies
```bash
# Python dependencies
pip install -r requirements.txt

# Development dependencies
pip install -r requirements-dev.txt
```

### 3. Start Services
```bash
# Using Docker Compose
docker-compose -f docker-compose.dev.yml up -d

# Or start individually
aitbc dev start
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
- Docker
- GitLens

### PyCharm
Configure Python interpreter and enable Docker integration.

## Environment Variables

Create `.env` file:
```bash
AITBC_API_KEY=your_dev_key
AITBC_BASE_URL=http://localhost:8011
AITBC_NETWORK=testnet
```

## Next Steps

- [API Authentication](api-authentication.md)
- [Python SDK](sdks/python.md)
- [Examples](examples.md)
