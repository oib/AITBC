---
title: Installation
description: Install and set up AITBC on your system
---

# Installation

This guide will help you install AITBC on your system.

## System Requirements

- Python 3.8 or higher
- Docker and Docker Compose (optional)
- 4GB RAM minimum
- 10GB disk space

## Installation Methods

### Method 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc

# Start with Docker Compose
docker-compose up -d
```

### Method 2: pip Install

```bash
# Install the CLI
pip install aitbc-cli

# Verify installation
aitbc --version
```

### Method 3: From Source

```bash
# Clone repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc

# Install in development mode
pip install -e .
```

## Next Steps

After installation, proceed to the [Quickstart Guide](quickstart.md).
