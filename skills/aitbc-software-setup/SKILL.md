---
name: aitbc-software-setup
description: "Set up AITBC blockchain software from scratch -- clone, install dependencies, configure systemd services, and verify on a fresh Debian/Ubuntu host."
---

# AITBC Software Setup

## Scope

This skill covers **initial software installation** of AITBC on a fresh Debian/Ubuntu host: cloning the repo, running the automated setup script, configuring services, and verifying the node can join the network.

For **production deployment** (Ollama, GPU miner, edge API), see the `aitbc-deployment` skill.
For **follower node** specific steps (genesis sync, batch import), see the `aitbc-node-setup` skill.
For **troubleshooting** running nodes, see the `aitbc-node-management` skill.

## Prerequisites

- Debian 13+ or Ubuntu 24.04+
- Root access
- Internet connectivity

## Quick Setup (Automated)

The one-command setup script handles everything: prerequisites, repo clone, venv, dependencies, PostgreSQL, Redis, systemd services.

```bash
curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh -o /tmp/aitbc_setup.sh
chmod +x /tmp/aitbc_setup.sh
sudo bash /tmp/aitbc_setup.sh
```

## What the Setup Script Does

The script runs 10 steps:

| Step | Action |
|------|--------|
| 1 | Verify root privileges |
| 2 | Check + install prerequisites (python3, pip3, git, systemd, node 24.x, postgresql, redis, nginx, jq, curl) |
| 3 | Clone repo to `/opt/aitbc` |
| 4 | Create runtime directories (`/var/lib/aitbc/`, `/etc/aitbc/`, `/var/log/aitbc/`, `/run/aitbc/secrets/`) |
| 5 | Setup PostgreSQL (9 databases with per-database users and random passwords) |
| 6 | Generate unique node identities (proposer_id, p2p_node_id) |
| 7 | Create secure credentials in `/etc/aitbc/credentials/` (600 permissions) |
| 8 | Create Python venv at `/opt/aitbc/venv` and install `requirements.txt` + `requirements-dev.txt` |
| 9 | Install systemd service symlinks and prepare health check script |
| 10 | Start services and enable autostart |

## Post-Setup Configuration

After the script completes, you MUST configure the node before it can join the network:

### 1. Set Node Role

Edit `/etc/aitbc/blockchain.env`:
```bash
# For follower nodes (most common):
ENABLE_BLOCK_PRODUCTION=false
NODE_ROLE=follower

# For genesis/hub nodes only:
ENABLE_BLOCK_PRODUCTION=true
NODE_ROLE=genesis
```

### 2. Configure Chain and Island IDs

Edit `/etc/aitbc/blockchain.env`:
```bash
CHAIN_ID=ait-hub.aitbc.bubuit.net
```

Edit `/etc/aitbc/node.env`:
```bash
NODE_ID=your-unique-node-name
ISLAND_ID=ait-hub.aitbc.bubuit.net-island
```

### 3. For Follower Nodes: Remove Proposer ID

```bash
rm -f /etc/aitbc/credentials/proposer_id
bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh
```

### 4. Copy Pre-configured Examples (Alternative)

For the open island, you can use the example configs:
```bash
cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Then edit NODE_ID to be unique
```

### 5. Add P2P Peers

Edit `/etc/aitbc/node.env`:
```bash
P2P_PEERS=hub.aitbc.bubuit.net:8001
```

## Service File Locations (Post-Restructure)

All systemd service files moved from `systemd/` to `apps/<service>/` on 2026-05-29:

| Service | Service File | Port |
|---------|-------------|------|
| Blockchain Node | `apps/blockchain-node/aitbc-blockchain-node.service` | -- |
| Blockchain RPC | `apps/blockchain-node/aitbc-blockchain-rpc.service` | 8006 |
| Blockchain P2P | `apps/blockchain-node/aitbc-blockchain-p2p.service` | 8001 |
| Blockchain Sync | `apps/blockchain-node/aitbc-blockchain-sync.service` | -- |
| Coordinator API | `apps/coordinator-api/aitbc-coordinator-api.service` | 8011 |
| Wallet | `apps/wallet/aitbc-wallet.service` | 8015 |
| Exchange API | `apps/exchange/aitbc-exchange-api.service` | 8010 |
| AI Engine | `apps/ai-engine/aitbc-ai.service` | -- |
| AI Learning | `apps/ai-engine/aitbc-learning.service` | -- |
| Multimodal | `apps/ai-engine/aitbc-multimodal.service` | -- |
| GPU Service | `apps/gpu-service/aitbc-gpu.service` | -- |
| Explorer | `apps/blockchain-explorer/aitbc-explorer.service` | -- |
| Marketplace | `apps/marketplace-service/aitbc-marketplace.service` | 8102 |
| Agent Coordinator | `apps/agent-coordinator/aitbc-agent-coordinator.service` | -- |
| Agent Registry | `apps/agent-management/aitbc-agent-registry.service` | -- |
| Hermes | `apps/hermes/aitbc-hermes.service` | -- |
| Blockchain Event Bridge | `apps/blockchain-event-bridge/aitbc-blockchain-event-bridge.service` | -- |
| Plugin | `scripts/utils/aitbc-plugin.service` | -- |
| Monitoring | `scripts/monitoring/aitbc-monitoring.service` | -- |

## Manual Service Installation (If Setup Script Fails)

```bash
# Install dependencies manually
apt-get install -y python3-pip python3-venv postgresql postgresql-contrib redis-server \
    build-essential libssl-dev libffi-dev nginx jq curl git
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs

# Clone repo
git clone https://github.com/oib/AITBC.git /opt/aitbc

# Create venv and install deps
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Link services
/opt/aitbc/scripts/utils/link-systemd.sh

# Or link manually:
for svc in /opt/aitbc/apps/*/aitbc-*.service /opt/aitbc/scripts/utils/aitbc-*.service \
          /opt/aitbc/scripts/monitoring/aitbc-*.service; do
    [ -f "$svc" ] && ln -sf "$svc" /etc/systemd/system/
done
systemctl daemon-reload
```

## Dependencies

Use the central requirements system at `/opt/aitbc/`:

```bash
# Core production (always needed)
pip install -r requirements.txt

# Development + testing tools
pip install -r requirements-dev.txt

# Optional modules (install as needed)
pip install -r requirements-optional/ai-ml.txt      # torch, transformers, openai, spacy
pip install -r requirements-optional/security.txt    # python-jose, passlib, sentry-sdk
# testing.txt references requirements-dev.txt (no separate install needed)
```

Or use the profile installer:
```bash
./scripts/deployment/install-profiles.sh core       # production only
./scripts/deployment/install-profiles.sh dev        # + dev tools
./scripts/deployment/install-profiles.sh all        # everything
```

## Starting Services

```bash
# Start core services (order matters)
systemctl start postgresql redis-server
systemctl start aitbc-blockchain-node
systemctl start aitbc-blockchain-rpc
systemctl start aitbc-blockchain-p2p

# Start API services
systemctl start aitbc-coordinator-api
systemctl start aitbc-wallet
systemctl start aitbc-exchange-api

# Check status
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc aitbc-coordinator-api

# View logs
journalctl -u aitbc-blockchain-node -f
journalctl -u aitbc-coordinator-api -f
```

## Verification

```bash
# Check blockchain RPC
curl http://localhost:8006/health

# Check coordinator API
curl http://localhost:8011/health

# Check wallet
curl http://localhost:8015/health

# Full health check
/opt/aitbc/scripts/monitoring/health_check.sh

# Sync status (follower nodes)
curl -s http://localhost:8006/rpc/head | python3 -m json.tool
curl -s <HUB_RPC_URL>/rpc/head | python3 -m json.tool
```

## Key Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `read_file` shows stale content | Tool caches file reads | Always verify with `cat`/`sed` via terminal |
| Node produces blocks on follower | `proposer_id` in credentials | `rm /etc/aitbc/credentials/proposer_id` + reload secrets |
| Code changes have no effect | Stale `.pyc` bytecode cache | `find /opt/aitbc -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null` |
| `git pull` fails with "divergent branches" | Force-push or multi-machine pushes | `git stash && git pull --rebase origin main && git stash pop` |
| Services fail to start | Missing prerequisites or config | Check `journalctl -u <service> -n 50` for errors |
| Python import errors after code change | `__pycache__` stale | Clear cache, restart service |
| Node won't sync from hub | Chain divergence | Wipe `/var/lib/aitbc/data/<chain_id>/` and restart p2p service |
| Port conflicts | Another process using the port | `ss -tulpn \| grep <port>` then kill or reconfigure |

## Runtime Directories

| Path | Purpose | Permissions |
|------|---------|-------------|
| `/opt/aitbc/` | Application code | 755 |
| `/opt/aitbc/venv/` | Python virtualenv | 755 |
| `/var/lib/aitbc/` | Runtime data | 755 |
| `/var/lib/aitbc/keystore/` | Blockchain keys | 700 |
| `/var/lib/aitbc/data/` | Database files | 755 |
| `/var/log/aitbc/` | Application logs | 755 |
| `/etc/aitbc/` | Configuration files | 755 |
| `/etc/aitbc/credentials/` | Secrets (passwords, keys) | 600 |
| `/run/aitbc/secrets/` | Runtime secrets (tmpfs, cleared on reboot) | 700 |

## PostgreSQL Databases

The setup script creates 9 databases:

| Database | Owner |
|----------|-------|
| `aitbc_coordinator` | `aitbc_user` |
| `aitbc_exchange` | `aitbc_user` |
| `aitbc_wallet` | `aitbc_user` |
| `aitbc_marketplace` | `aitbc_marketplace` |
| `aitbc_governance` | `aitbc_governance` |
| `aitbc_trading` | `aitbc_trading` |
| `aitbc_gpu` | `aitbc_gpu` |
| `aitbc_ai` | `aitbc_ai` |
| `aitbc_mempool` | `aitbc_mempool` |

Passwords stored in `/etc/aitbc/credentials/postgres_<user>_password` (600 permissions).

If the setup script failed partway through and databases were created without passwords, reset them:
```bash
sudo -u postgres psql -c "ALTER USER aitbc_user WITH PASSWORD 'aitbc_user_password';"
# Repeat for other users as needed
```

## Pre-commit Hooks

The repo includes `.pre-commit-config.yaml` with black, isort, flake8, mypy, bandit, and safety checks.

```bash
# Install pre-commit (included in requirements-dev.txt)
pre-commit install

# Run manually
pre-commit run --all-files

# Skip during active development
git commit --no-verify -m "WIP: message"
```

Pytest tests run in CI, NOT in pre-commit hooks. Use `--no-verify` to skip hooks during WIP commits.
