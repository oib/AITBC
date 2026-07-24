# Getting Started

Welcome to the AITBC Platform Builder tooling. This guide covers installing the
CLI, configuring your environment, and running your first local node.

## Prerequisites

- Python 3.13+
- `git`
- A running AITBC coordinator (local or remote)

## Install the CLI

The CLI is installed in the project virtual environment:

```bash
cd /opt/aitbc
./venv/bin/aitbc --help
```

## Configure your environment

Generate a starter `.env` file:

```bash
./venv/bin/aitbc bootstrap-env --output .env
```

Then fill in the missing keys and load the file:

```bash
source .env
./venv/bin/aitbc config check
```

## Register as a developer

```bash
./venv/bin/aitbc developer register \
  --wallet-address 0x... \
  --name "Your Name" \
  --email you@example.com \
  --github your-handle
```

## Next steps

- Read `contributing.md` to learn how to submit changes.
- Read `grants.md` to apply for a DAO grant.
