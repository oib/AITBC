# Installation

**Last Updated:** 2026-05-28

> **Note:** This document describes the installation process for the AITBC platform. For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## Prerequisites

- Python 3.13+
- Git
- (Optional) PostgreSQL 14+ for production
- (Optional) NVIDIA GPU + CUDA for mining

## Security First Setup

**⚠️ IMPORTANT**: AITBC has enterprise-level security hardening. After installation, immediately run:

```bash
# Run comprehensive security audit and hardening
./scripts/comprehensive-security-audit.sh

# This will fix 90+ CVEs, harden SSH, and verify smart contracts
```

**Security Status**: 🛡️ AUDITED & HARDENED
- **0 vulnerabilities** in smart contracts (35 OpenZeppelin warnings only)
- **90 CVEs** fixed in dependencies (target achieved)
- **95/100 system hardening** index achieved (target metric)

> **Note:** Security metrics represent targets achieved during audit periods. Current security status should be verified using `./scripts/utils/check-dependencies.sh` and CI/CD security scanning.

## Monorepo Install

```bash
git clone https://github.com/oib/AITBC.git
cd aitbc
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs the enhanced AITBC CLI, coordinator API, and blockchain node from the monorepo.

## Verify CLI Installation

```bash
# Check CLI version and installation
aitbc --version
aitbc --help

# Test CLI connectivity
aitbc blockchain status
```

Expected output:
```
AITBC CLI v0.1.0
Platform: Linux/MacOS
Architecture: x86_64/arm64
✓ CLI installed successfully
```

## Environment Configuration

### Coordinator API

Create `apps/coordinator-api/.env`:
```env
JWT_SECRET=your-secret-key
DATABASE_URL=sqlite:///./data/coordinator.db   # or postgresql://user:pass@localhost/aitbc
LOG_LEVEL=INFO
```

### Blockchain Node

Create `apps/blockchain-node/.env`:
```env
CHAIN_ID=ait-devnet
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8006  # Updated to new blockchain RPC port
MEMPOOL_BACKEND=database
```

## Systemd Services (Production)

```bash
cp systemd/aitbc-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now aitbc-coordinator-api
systemctl enable --now aitbc-blockchain-node
```

## Verify

```bash
systemctl status aitbc-coordinator-api
curl http://localhost:8011/health
aitbc blockchain status
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port in use | `lsof -i :8011` then `kill` the PID |
| DB corrupt | `rm -f data/coordinator.db && python -m app.storage init` |
| Module not found | Ensure venv is active: `source .venv/bin/activate` |

## Next Steps

- [CLI Guide](../overview/cli-guide.md) — CLI usage guide
- [Miner Quick Start](../mining/miner-quick-start.md) — Miner quick start
- [Blockchain Setup](../node/blockchain-setup.md) — Blockchain node setup
