# AITBC Infrastructure Documentation

> Last updated: 2026-03-04 (Updated for new port logic and production-ready codebase)

## Overview

Two-tier architecture: **incus host (at1)** runs the reverse proxy with SSL termination, forwarding all `aitbc.bubuit.net` traffic to the **aitbc container** which runs nginx + all services. **Updated for new port logic implementation (8000-8003, 8010-8017) and production-ready codebase.**

```
Internet → aitbc.bubuit.net (HTTPS :443)
    │
    ▼
┌──────────────────────────────────────────────┐
│  Incus Host (at1 / localhost)                │
│  Nginx reverse proxy (:443 SSL → :80)       │
│  Config: /etc/nginx/sites-available/         │
│          aitbc-proxy.conf                    │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Container: aitbc (10.1.223.1)        │  │
│  │  Access: ssh aitbc-cascade            │  │
│  │  OS: Debian 13 Trixie                  │  │
│  │  Node.js: 22+                          │  │
│  │  Python: 3.13.5+                       │  │
│  │  GPU Access: None (CPU-only mode)     │  │
│  │  Miner Service: Not needed              │  │
│  │                                        │  │
│  │  Nginx (:80) → routes to services:    │  │
│  │    /              → static website     │  │
│  │    /explorer/     → Vite SPA           │  │
│  │    /marketplace/  → Vite SPA           │  │
│  │    /api/          → :8000 (coordinator)│  │
│  │    /api/exchange/ → :8001 (exchange)  │  │
│  │    /rpc/          → :8003 (blockchain) │  │
│  │    /app/          → :8016 (web ui)     │  │
│  │    /api/gpu/      → :8010 (multimodal) │  │
│  │    /api/gpu-multimodal/ → :8011        │  │
│  │    /api/optimization/ → :8012         │  │
│  │    /api/learning/ → :8013              │  │
│  │    /api/marketplace-enhanced/ → :8014 │  │
│  │    /api/openclaw/ → :8015              │  │
│  │    /health        → 200 OK             │  │
│  │                                        │  │
│  │  Config: /etc/nginx/sites-enabled/     │  │
│  │          aitbc.bubuit.net              │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

## Port Logic Implementation (March 4, 2026)

### **Core Services (8000-8003)**
- **Port 8000**: Coordinator API ✅ PRODUCTION READY
- **Port 8001**: Exchange API ✅ PRODUCTION READY  
- **Port 8002**: Blockchain Node (internal) ✅ PRODUCTION READY
- **Port 8003**: Blockchain RPC ✅ PRODUCTION READY

### **Enhanced Services (8010-8017)**
- **Port 8010**: Multimodal GPU Service ✅ PRODUCTION READY (CPU-only mode)
- **Port 8011**: GPU Multimodal Service ✅ PRODUCTION READY (CPU-only mode)
- **Port 8012**: Modality Optimization Service ✅ PRODUCTION READY
- **Port 8013**: Adaptive Learning Service ✅ PRODUCTION READY
- **Port 8014**: Marketplace Enhanced Service ✅ PRODUCTION READY
- **Port 8015**: OpenClaw Enhanced Service ✅ PRODUCTION READY
- **Port 8016**: Web UI Service ✅ PRODUCTION READY
- **Port 8017**: Geographic Load Balancer ✅ PRODUCTION READY

### **Legacy Ports (Decommissioned)**
- **Port 8080**: No longer used by AITBC
- **Port 9080**: Successfully decommissioned
- **Port 8009**: No longer in use

## Incus Host (at1)

### Host Details
- **Hostname**: `at1` (primary development workstation)
- **Environment**: Windsurf development environment
- **OS**: Debian 13 Trixie (development environment)
- **Node.js**: 22+ (current tested: v22.22.x)
- **Python**: 3.13.5+ (minimum requirement, strictly enforced)
- **GPU Access**: **Primary GPU access location** - all GPU workloads must run on at1
- **Architecture**: x86_64 Linux with CUDA GPU support

### Services (Host)

| Service | Port | Process | Python Version | Purpose | Status |
|---------|------|---------|----------------|---------|--------|
| Mock Coordinator | 8090 | python3 | 3.13.5+ | Development/testing API endpoint | systemd: aitbc-mock-coordinator.service |
| Blockchain Node | N/A | python3 | 3.13.5+ | Local blockchain node | systemd: aitbc-blockchain-node.service |
| Blockchain Node RPC | 8003 | python3 | 3.13.5+ | RPC API for blockchain | systemd: aitbc-blockchain-rpc.service |
| Local Development Tools | Varies | python3 | 3.13.5+ | CLI tools, scripts, testing | Manual/venv |
| **Note**: GPU Miner Client removed - no miner service needed on aitbc server

### Systemd Services (Host)

All services are configured as systemd units but currently inactive:

```bash
# Service files location: /etc/systemd/system/
aitbc-blockchain-node.service      # Blockchain node main process
aitbc-blockchain-rpc.service       # RPC API on port 8003
aitbc-mock-coordinator.service     # Mock coordinator on port 8090
# Note: aitbc-gpu-miner.service removed - no miner service needed
```

**Service Details:**
- **Working Directory**: `/opt/aitbc/` (standard path for all services)
- **Python Environment**: `/opt/aitbc/.venv/bin/python` (Python 3.13.5+)
- **Node.js Environment**: System Node.js 22+ (current tested: v22.22.x)
- **User**: oib
- **Restart Policy**: always (with 5s delay)

### Standard Service Structure (/opt/aitbc)

On at1, `/opt/aitbc` uses individual symlinks to the Windsurf project directories:

```bash
/opt/aitbc/                          # Service root with selective symlinks
├── apps/                            # Symlinked app directories
│   ├── blockchain-explorer -> /home/oib/windsurf/aitbc/apps/blockchain-explorer/
│   ├── blockchain-node -> /home/oib/windsurf/aitbc/apps/blockchain-node/
│   ├── coordinator-api -> /home/oib/windsurf/aitbc/apps/coordinator-api/
│   ├── explorer-web -> /home/oib/windsurf/aitbc/apps/explorer-web/
│   ├── marketplace-web -> /home/oib/windsurf/aitbc/apps/marketplace-web/
│   ├── pool-hub -> /home/oib/windsurf/aitbc/apps/pool-hub/
│   ├── trade-exchange -> /home/oib/windsurf/aitbc/apps/trade-exchange/
│   ├── wallet-daemon -> /home/oib/windsurf/aitbc/apps/wallet-daemon/
│   └── zk-circuits -> /home/oib/windsurf/aitbc/apps/zk-circuits/
├── data/                            # Local service data
├── logs/                            # Local service logs
├── models/                          # Local model storage
├── scripts -> /home/oib/windsurf/aitbc/scripts/  # Shared scripts
└── systemd -> /home/oib/windsurf/aitbc/systemd/  # Service definitions
```

**On aitbc/aitbc1 servers**: `/opt/aitbc` is symlinked to the git repo clone (`/opt/aitbc -> /path/to/aitbc-repo`) for complete repository access.

**Verification Commands:**
```bash
# Check service status
sc-status aitbc-blockchain-node.service aitbc-blockchain-rpc.service aitbc-gpu-miner.service aitbc-mock-coordinator.service

# Start services
sudo systemctl start aitbc-mock-coordinator.service
sudo systemctl start aitbc-blockchain-node.service

# Check logs
journalctl -u aitbc-mock-coordinator --no-pager -n 20

# Verify /opt/aitbc symlink structure
ls -la /opt/aitbc/                      # Should show individual app symlinks
ls -la /opt/aitbc/apps/                 # Should show all app symlinks
ls -la /opt/aitbc/scripts                # Should show symlink to windsurf scripts
ls -la /opt/aitbc/systemd               # Should show symlink to windsurf systemd
```

### Python Environment (at1)

**Development vs Service Environments**:

```bash
# Development environment (Windsurf project)
/home/oib/windsurf/aitbc/.venv/          # Development Python 3.13.5 environment
├── bin/python                          # Python executable
├── apps/                               # Service applications
├── cli/                                # CLI tools (12 command groups)
├── scripts/                            # Development scripts
└── tests/                              # Pytest suites

# Service environment (/opt/aitbc with symlinks)
/opt/aitbc/                             # Service root with selective symlinks
├── apps/blockchain-node -> /home/oib/windsurf/aitbc/apps/blockchain-node/
├── apps/coordinator-api -> /home/oib/windsurf/aitbc/apps/coordinator-api/
├── scripts -> /home/oib/windsurf/aitbc/scripts/
└── systemd -> /home/oib/windsurf/aitbc/systemd/

# Node.js environment
node --version                          # Should show v22.22.x
npm --version                           # Should show compatible version
```

**Note**: Services use individual symlinks to specific app directories, while development uses the full Windsurf project workspace.

**Verification Commands:**
```bash
# Verify symlink structure
ls -la /opt/aitbc/                      # Should show individual symlinks, not single repo symlink
ls -la /opt/aitbc/apps/blockchain-node  # Should point to windsurf project
python3 --version                      # Should show Python 3.13.5
ls -la /home/oib/windsurf/aitbc/.venv/bin/python  # Check development venv
node --version                              # Should show v22.22.x
npm --version                               # Should show compatible version

# Test symlink resolution
readlink -f /opt/aitbc/apps/blockchain-node  # Should resolve to windsurf project path
readlink -f /opt/aitbc/scripts               # Should resolve to windsurf scripts
```

### Nginx Reverse Proxy

The host runs a simple reverse proxy that forwards all traffic to the container. SSL is terminated here via Let's Encrypt.

- **Config**: `/etc/nginx/sites-available/aitbc-proxy.conf`
- **Enabled**: symlinked in `/etc/nginx/sites-enabled/`
- **SSL**: Let's Encrypt cert for `bubuit.net` (managed by Certbot)
- **Upstream**: `http://10.1.223.93` (container IP)
- **WebSocket**: supported (Upgrade/Connection headers forwarded)

```nginx
# /etc/nginx/sites-available/aitbc-proxy.conf (active)
server {
    server_name aitbc.bubuit.net;
    location / {
        proxy_pass http://10.1.223.93;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    listen 443 ssl;  # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/bubuit.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bubuit.net/privkey.pem;
}
# HTTP → HTTPS redirect (managed by Certbot)
```

**Purged legacy configs** (2026-02-14):
- `aitbc-website-new.conf` — served files directly from host, bypassing container. Deleted.

## Container: aitbc (10.1.223.1)

### Access
```bash
ssh aitbc-cascade                    # Direct SSH to container
```

**GPU Access**: No GPU passthrough. All GPU workloads must run on **at1** (Windsurf development host), not inside incus containers.

**Miner Service**: Not needed - aitbc server operates in CPU-only mode.

**Host Proxies (for localhost GPU clients)**
- `127.0.0.1:18000` → container `127.0.0.1:8000` (coordinator/marketplace API)
- Use this to submit offers/bids/contracts/mining requests from localhost GPU miners/dev clients.

**Container Services (Updated March 4, 2026)**
- **12 Services**: All 12 services operational with new port logic
- **Core Services**: 8000-8003 (Coordinator, Exchange, Blockchain Node, RPC)
- **Enhanced Services**: 8010-8017 (GPU services in CPU-only mode, Web UI, Load Balancer)
- **0.0.0.0 Binding**: All services bind to 0.0.0.0 for container access
- **Production Ready**: All services marked as production ready

## Container: aitbc1 (10.1.223.40) — New Dev Server

### Access
```bash
ssh aitbc1-cascade                   # Direct SSH to aitbc1 container (incus)
```

### Notes
- Purpose: secondary AITBC dev environment (incus container)
- Host: 10.1.223.40 (Debian 13 Trixie), accessible via new SSH alias `aitbc1-cascade`
- OS: Debian 13 Trixie (development environment)
- Node.js: 22+ (current tested: v22.22.x)
- Python: 3.13.5+ (minimum requirement, strictly enforced)
- Proxy device: incus proxy on host maps 127.0.0.1:18001 → 127.0.0.1:8000 inside container
- AppArmor profile: unconfined (incus raw.lxc)
- Use same deployment patterns as `aitbc` (nginx + services) once provisioned
- **GPU Access**: None. Run GPU-dependent tasks on **at1** (Windsurf development host) only.

**Host Proxies (for localhost GPU clients)**
- `127.0.0.1:18001` → container `127.0.0.1:8000` (coordinator/marketplace API)
- Use this to hit the second marketplace/coordinator from localhost GPU miners/dev clients.
- (Optional) Expose marketplace frontend for aitbc1 via an additional proxy/port if needed for UI tests.
- Health check suggestion: `curl -s http://127.0.0.1:18001/v1/health`

**at1 dual-miner/dual-client test (shared GPU)**
- Run two miners on **at1** (GPU shared), targeting each marketplace:
  - Miner A → `http://127.0.0.1:18000`
  - Miner B → `http://127.0.0.1:18001`
- Run two clients on **at1** for bids/contracts/Ollama answers:
  - Client 1 → `http://127.0.0.1:18000`
  - Client 2 → `http://127.0.0.1:18001`
- Use a shared dev chain so both marketplaces see the same on-chain events.
- Example commands (adjust to your scripts/flags):
  - `miner --id miner-A --gpu 0 --api http://127.0.0.1:18000`
  - `miner --id miner-B --gpu 0 --api http://127.0.0.1:18001`
  - `client --id client-1 --api http://127.0.0.1:18000 --ollama-model <model>`
  - `client --id client-2 --api http://127.0.0.1:18001 --ollama-model <model>`


### Services

| Service | Port | Process | Python Version | Public URL | Status |
|---------|------|---------|----------------|------------|--------|
| Nginx (web) | 80 | nginx | N/A | https://aitbc.bubuit.net/ | ✅ |
| Coordinator API | 8000 | python (uvicorn) | 3.13.5 | /api/ → /v1/ | ✅ |
| Exchange API | 8001 | python (uvicorn) | 3.13.5 | /api/exchange/* | ✅ |
| Blockchain Node | 8002 | python3 | 3.13.5 | Internal | ✅ |
| Blockchain RPC | 8003 | python3 | 3.13.5 | /rpc/ | ✅ |
| Multimodal GPU | 8010 | python | 3.13.5 | /api/gpu/* | ✅ (CPU-only) |
| GPU Multimodal | 8011 | python | 3.13.5 | /api/gpu-multimodal/* | ✅ (CPU-only) |
| Modality Optimization | 8012 | python | 3.13.5 | /api/optimization/* | ✅ |
| Adaptive Learning | 8013 | python | 3.13.5 | /api/learning/* | ✅ |
| Marketplace Enhanced | 8014 | python | 3.13.5 | /api/marketplace-enhanced/* | ✅ |
| OpenClaw Enhanced | 8015 | python | 3.13.5 | /api/openclaw/* | ✅ |
| Web UI | 8016 | python | 3.13.5 | /app/ | ✅ |
| Geographic Load Balancer | 8017 | python | 3.13.5 | /api/loadbalancer/* | ✅ |

**Python 3.13.5 and Node.js 22+ Upgrade Complete** (2026-03-04):
- All services upgraded to Python 3.13.5
- Node.js upgraded to 22+ (current tested: v22.22.x)
- Virtual environments updated and verified
- API routing fixed for external access
- Services fully operational with enhanced performance
- New port logic implemented: Core Services (8000+), Enhanced Services (8010+)
- GPU services configured for CPU-only mode
- Miner service removed - not needed
- 0.0.0.0 binding enabled for container access

### Python Environment Details

All Python services in the AITBC container run on **Python 3.13.5** with isolated virtual environments:

```bash
# Container: aitbc (10.1.223.1)
/opt/aitbc/apps/coordinator-api/.venv/          # Coordinator API (uvicorn, FastAPI)
/opt/aitbc/apps/blockchain-node/.venv/          # Blockchain Node 1 (aitbc_chain)
/opt/aitbc/apps/exchange/.venv/                  # Exchange API (Flask/specific framework)
# Note: Standardized /opt/aitbc structure for all services
```

**Verification Commands:**
```bash
ssh aitbc-cascade "python3 --version"  # Should show Python 3.13.5
ssh aitbc-cascade "node --version"      # Should show v22.22.x
ssh aitbc-cascade "npm --version"       # Should show compatible version
ssh aitbc-cascade "ls -la /opt/*/.venv/bin/python"  # Check venv symlinks
ssh aitbc-cascade "curl -s http://127.0.0.1:8000/v1/health"  # Coordinator API health
curl -s https://aitbc.bubuit.net/api/v1/health  # External API access
```

### Nginx Routes (container)

Config: `/etc/nginx/sites-enabled/aitbc.bubuit.net`

| Route | Target | Type | Status |
|-------|--------|------|--------|
| `/` | static files (`/var/www/aitbc.bubuit.net/`) | try_files | ✅ |
| `/explorer/` | Vite SPA (`/var/www/aitbc.bubuit.net/explorer/`) | try_files | ✅ |
| `/marketplace/` | Vite SPA (`/var/www/aitbc.bubuit.net/marketplace/`) | try_files | ✅ |
| `/docs/` | static HTML (`/var/www/aitbc.bubuit.net/docs/`) | alias | ✅ |
| `/api/` | proxy → `127.0.0.1:8000/` | proxy_pass | ✅ |
| `/api/explorer/` | proxy → `127.0.0.1:8000/v1/explorer/` | proxy_pass | ✅ |
| `/api/users/` | proxy → `127.0.0.1:8000/v1/users/` | proxy_pass | ✅ |
| `/api/exchange/` | proxy → `127.0.0.1:8001/` | proxy_pass | ✅ |
| `/api/trades/recent` | proxy → `127.0.0.1:8001/trades/recent` | proxy_pass | ✅ |
| `/api/orders/orderbook` | proxy → `127.0.0.1:8001/orders/orderbook` | proxy_pass | ✅ |
| `/admin/` | proxy → `127.0.0.1:8000/v1/admin/` | proxy_pass | ✅ |
| `/rpc/` | proxy → `127.0.0.1:8003` | proxy_pass | ✅ |
| `/app/` | proxy → `127.0.0.1:8016` | proxy_pass | ✅ |
| `/api/gpu/` | proxy → `127.0.0.1:8010` | proxy_pass | ✅ (CPU-only) |
| `/api/gpu-multimodal/` | proxy → `127.0.0.1:8011` | proxy_pass | ✅ (CPU-only) |
| `/api/optimization/` | proxy → `127.0.0.1:8012` | proxy_pass | ✅ |
| `/api/learning/` | proxy → `127.0.0.1:8013` | proxy_pass | ✅ |
| `/api/marketplace-enhanced/` | proxy → `127.0.0.1:8014` | proxy_pass | ✅ |
| `/api/openclaw/` | proxy → `127.0.0.1:8015` | proxy_pass | ✅ |
| `/api/loadbalancer/` | proxy → `127.0.0.1:8017` | proxy_pass | ✅ |
| `/health` | 200 OK | direct | ✅ |
| `/Marketplace` | 301 → `/marketplace/` | redirect (legacy) | ✅ |
| `/BrowserWallet` | 301 → `/docs/browser-wallet.html` | redirect (legacy) | ✅ |

**API Routing Updated** (2026-03-04):
- Updated `/api/` proxy_pass from `http://127.0.0.1:8000/v1/` to `http://127.0.0.1:8000/`
- Updated Exchange API routes to port 8001 (new port logic)
- Updated RPC route to port 8003 (new port logic)
- Added Enhanced Services routes (8010-8017)
- Added Web UI route to port 8016
- Added Geographic Load Balancer route to port 8017
- Removed legacy routes (Exchange, wallet, mock coordinator)
- External API access now working: `https://aitbc.bubuit.net/api/v1/health` → `{"status":"ok","env":"dev"}`
- All GPU services marked as CPU-only mode

### Web Root (`/var/www/aitbc.bubuit.net/`)

```
/var/www/aitbc.bubuit.net/
├── index.html              # Main website
├── 404.html                # Error page
├── favicon.ico
├── favicon.svg
├── font-awesome-local.css
├── docs/                   # HTML documentation (16 pages + css/js)
│   ├── index.html
│   ├── clients.html
│   ├── miners.html
│   ├── developers.html
│   ├── css/docs.css
│   └── js/theme.js
├── explorer/               # Blockchain explorer (Vite build)
│   ├── index.html
│   ├── assets/
│   ├── css/
│   └── js/
├── marketplace/            # GPU marketplace (Vite build)
│   ├── index.html
│   └── assets/
├── wallet/                 # Browser wallet redirect
│   └── index.html
└── firefox-wallet/         # Firefox extension download
```

### Data Storage (container)

```
/opt/aitbc/apps/coordinator-api/          # Coordinator application
├── src/coordinator.db         # Main database
└── .venv/                     # Python environment

/opt/aitbc/apps/blockchain-node/          # Blockchain Node 1
├── data/chain.db              # Chain database
└── .venv/                     # Python environment

/opt/aitbc/apps/exchange/                 # Exchange API
├── data/                      # Exchange data
└── .venv/                     # Python environment
```

### Configuration (container)
- Node 1: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/config.py`
- Coordinator API: `/opt/aitbc/apps/coordinator-api/.env`
- Exchange API: `/opt/aitbc/apps/exchange/.env`
- Enhanced Services: Environment variables in respective service files

## Remote Site (ns3)

### Host (ns3-root)
- **IP**: 95.216.198.140
- **Access**: `ssh ns3-root`
- **Bridge**: incusbr0 `192.168.100.1/24`
- **Port forwarding**: firehol (8000, 8001, 8003, 8010-8017 → 192.168.100.10)
- **Updated**: Port logic aligned with main aitbc server

### Container (ns3/aitbc)
- **IP**: 192.168.100.10
- **Domain**: aitbc.keisanki.net
- **Access**: `ssh ns3-root` → `incus shell aitbc`
- **Blockchain Node 3**: RPC on port 8003 (updated port logic)
- **GPU Access**: None (CPU-only mode)
- **Miner Service**: Not needed

```bash
curl http://aitbc.keisanki.net/rpc/head    # Node 3 RPC (port 8003)
```

## Cross-Site Synchronization

- **Status**: Active on all 3 nodes
- **Method**: RPC-based polling every 10 seconds
- **Features**: Transaction propagation, height detection, block import
- **Endpoints**:
  - Local: https://aitbc.bubuit.net/rpc/ (Node 1, port 8003)
  - Remote: http://aitbc.keisanki.net/rpc/ (Node 3, port 8003)
- **Updated**: All nodes using new port logic (8003 for RPC)
- **Consensus**: PoA with 2s block intervals
- **P2P**: Not connected yet; nodes maintain independent chain state

## Development Workspace (at1)

```
/home/oib/windsurf/aitbc/      # at1 Windsurf development workspace
├── apps/                      # Application source (8 apps)
├── cli/                       # CLI tools (12 command groups)
├── scripts/                   # Organized scripts (8 subfolders)
│   ├── blockchain/            # Genesis, proposer, mock chain
│   ├── dev/                   # Dev tools, local services
│   └── examples/              # Usage examples and simulations
├── tests/                     # Pytest suites + verification scripts
├── docs/                      # Markdown documentation (10 sections)
└── website/                   # Public website source
```

### Deploying to Container
```bash
# Push website files
scp -r website/* aitbc-cascade:/var/www/aitbc.bubuit.net/

# Push app updates
scp -r apps/explorer-web/dist/* aitbc-cascade:/var/www/aitbc.bubuit.net/explorer/

# Restart a service
ssh aitbc-cascade "systemctl restart coordinator-api"
```

## Health Checks

```bash
# From at1 (via container)
ssh aitbc-cascade "curl -s http://localhost:8000/v1/health"
ssh aitbc-cascade "curl -s http://localhost:8003/rpc/head | jq .height"

# Test enhanced services
ssh aitbc-cascade "curl -s http://localhost:8010/health"  # Multimodal GPU (CPU-only)
ssh aitbc-cascade "curl -s http://localhost:8017/health"  # Geographic Load Balancer

# From internet (Python 3.13.5 upgraded services)
curl -s https://aitbc.bubuit.net/health
curl -s https://aitbc.bubuit.net/api/v1/health  # ✅ Fixed API routing
curl -s https://aitbc.bubuit.net/api/explorer/blocks

# Test enhanced services externally
curl -s https://aitbc.bubuit.net/api/gpu/health
curl -s https://aitbc.bubuit.net/api/loadbalancer/health

# Remote site
ssh ns3-root "curl -s http://192.168.100.10:8003/rpc/head | jq .height"

# Python version verification
ssh aitbc-cascade "python3 --version"  # Python 3.13.5
```

## Monitoring and Logging

```bash
# Container systemd logs
ssh aitbc-cascade "journalctl -u aitbc-coordinator-api --no-pager -n 20"
ssh aitbc-cascade "journalctl -u aitbc-blockchain-node --no-pager -n 20"

# Enhanced services logs
ssh aitbc-cascade "journalctl -u aitbc-multimodal-gpu --no-pager -n 20"
ssh aitbc-cascade "journalctl -u aitbc-loadbalancer-geo --no-pager -n 20"

# Container nginx logs
ssh aitbc-cascade "tail -20 /var/log/nginx/aitbc.bubuit.net.error.log"

# Host nginx logs
sudo tail -20 /var/log/nginx/error.log
```

## Security

### SSL/TLS
- Let's Encrypt certificate for `bubuit.net` (wildcard)
- SSL termination at incus host nginx
- HTTP → HTTPS redirect (Certbot managed)

### CORS
- Coordinator API: localhost origins only (8000-8003, 8010-8017)
- Exchange API: localhost origins only (8000-8003, 8010-8017)
- Blockchain Node: localhost origins only (8000-8003, 8010-8017)
- Enhanced Services: localhost origins only (8010-8017)
- **Updated**: New port logic reflected in CORS policies

### Authentication
- Coordinator API: `X-Api-Key` header required
- Exchange API: session-based (wallet address login, 24h expiry)
- JWT secrets from environment variables (fail-fast on startup)

### Encryption
- Wallet private keys: Fernet (AES-128-CBC) with PBKDF2-SHA256 key derivation
- Database credentials: parsed from `DATABASE_URL` env var

### Environment Variables
```bash
# Coordinator API
JWT_SECRET=<secret>
DATABASE_URL=sqlite:///./aitbc_coordinator.db
MINER_API_KEYS=["production_key_32_characters_long_minimum"]
# Note: No miner service needed - configuration kept for compatibility

# Exchange API
SESSION_SECRET=<secret>
WALLET_ENCRYPTION_KEY=<key>

# Enhanced Services
HOST=0.0.0.0  # For container access
PORT=8010-8017  # Enhanced services port range
```
