# Installation

## Prerequisites

- Python 3.10+
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
- **90 CVEs** fixed in dependencies
- **95/100 system hardening** index achieved

## Monorepo Install

```bash
git clone https://github.com/oib/AITBC.git
cd aitbc
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs the CLI, coordinator API, and blockchain node from the monorepo.

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
RPC_BIND_PORT=8080
MEMPOOL_BACKEND=database
```

## Systemd Services (Production)

```bash
sudo cp systemd/aitbc-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aitbc-coordinator-api
sudo systemctl enable --now aitbc-blockchain-node-1
```

## Verify

```bash
systemctl status aitbc-coordinator-api
curl http://localhost:8000/v1/health
aitbc blockchain status
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port in use | `sudo lsof -i :8000` then `kill` the PID |
| DB corrupt | `rm -f data/coordinator.db && python -m app.storage init` |
| Module not found | Ensure venv is active: `source .venv/bin/activate` |

## Next Steps

- [3_cli.md](./3_cli.md) — CLI usage guide
- [../2_clients/1_quick-start.md](../2_clients/1_quick-start.md) — Client quick start
- [../3_miners/1_quick-start.md](../3_miners/1_quick-start.md) — Miner quick start
