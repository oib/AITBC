# Installation

**Last Updated:** 2026-05-28

> **Note:** This document describes the installation process for the AITBC platform. For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## Prerequisites

- Python 3.13+
- Git
- (Optional) PostgreSQL 14+ for production
- (Optional) NVIDIA GPU + CUDA for mining

## Security First Setup

**⚠️ IMPORTANT**: After installation, run the security tooling that ships in the repo:

```bash
# Production security assessment (writes /opt/aitbc/security_audit_report.json)
python3 scripts/security/security_audit.py

# Dependency vulnerability scan
./scripts/security/dependency-scan.sh

# System hardening (SSH, services, file permissions) — review before running
./scripts/utils/security_hardening.sh
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

Services load env files from `/etc/aitbc/` — per-app `.env` files inside
`apps/` are not read by the packaged units. See
[ENVIRONMENT_CONFIGURATION](../../blockchain/ENVIRONMENT_CONFIGURATION.md)
for the full reference.

### Coordinator API (`/etc/aitbc/aitbc-coordinator-api.env` + shared files)

```env
JWT_SECRET=<YOUR_JWT_SECRET>
LOG_LEVEL=INFO
```

`JWT_SECRET` is normally set in `/etc/aitbc/blockchain-secrets.env` (shared,
mode 600) rather than per-service.

### Blockchain Node (`/etc/aitbc/blockchain.env` + `/etc/aitbc/node.env`)

```env
CHAIN_ID=ait-devnet
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8202
MEMPOOL_BACKEND=database
```

## Systemd Services (Production)

Unit files ship inside each app directory — `apps/<service>/aitbc-<name>.service`
(there is no top-level `systemd/` directory):

```bash
ln -sf /opt/aitbc/apps/coordinator-api/aitbc-coordinator-api.service /etc/systemd/system/
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-node.service /etc/systemd/system/
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-rpc.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now aitbc-coordinator-api aitbc-blockchain-node aitbc-blockchain-rpc
```

## Verify

```bash
systemctl status aitbc-coordinator-api
curl http://localhost:8203/health
aitbc blockchain status
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port in use | `lsof -i :8203` then `kill` the PID |
| DB corrupt | Chain DB lives at `/var/lib/aitbc/data/<chain-id>/chain.db` — stop the node before touching it |
| Module not found | Ensure venv is active: `source /opt/aitbc/venv/bin/activate` |

## Next Steps

- [CLI Guide](../overview/cli-guide.md) — CLI usage guide
- [Miner Quick Start](../mining/miner-quick-start.md) — Miner quick start
- [Blockchain Setup](../node/blockchain-setup.md) — Blockchain node setup
