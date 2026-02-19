# AITBC Infrastructure Documentation

> Last updated: 2026-02-14

## Overview

Two-tier architecture: **incus host** (localhost) runs the reverse proxy with SSL termination, forwarding all `aitbc.bubuit.net` traffic to the **aitbc container** which runs nginx + all services.

```
Internet → aitbc.bubuit.net (HTTPS :443)
    │
    ▼
┌──────────────────────────────────────────────┐
│  Incus Host (localhost / at1)                │
│  Nginx reverse proxy (:443 SSL → :80)       │
│  Config: /etc/nginx/sites-available/         │
│          aitbc-proxy.conf                    │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Container: aitbc (10.1.223.93)       │  │
│  │  Access: ssh aitbc-cascade            │  │
│  │                                        │  │
│  │  Nginx (:80) → routes to services:    │  │
│  │    /              → static website     │  │
│  │    /explorer/     → Vite SPA           │  │
│  │    /marketplace/  → Vite SPA           │  │
│  │    /Exchange      → :3002 (Python)     │  │
│  │    /docs/         → static HTML        │  │
│  │    /wallet/       → :8002 (daemon)     │  │
│  │    /api/          → :8000 (coordinator)│  │
│  │    /rpc/          → :9080 (blockchain) │  │
│  │    /admin/        → :8000 (coordinator)│  │
│  │    /health        → 200 OK             │  │
│  │                                        │  │
│  │  Config: /etc/nginx/sites-enabled/     │  │
│  │          aitbc.bubuit.net              │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

## Incus Host (localhost)

### Services (Host)

| Service | Port | Process | Python Version | Purpose | Status |
|---------|------|---------|----------------|---------|--------|
| Mock Coordinator | 8090 | python3 | 3.11+ | Development/testing API endpoint | systemd: aitbc-mock-coordinator.service |
| Blockchain Node | N/A | python3 | 3.11+ | Local blockchain node | systemd: aitbc-blockchain-node.service |
| Blockchain Node RPC | 9080 | python3 | 3.11+ | RPC API for blockchain | systemd: aitbc-blockchain-rpc.service |
| GPU Miner Client | N/A | python3 | 3.11+ | GPU mining client | systemd: aitbc-gpu-miner.service |
| Local Development Tools | Varies | python3 | 3.11+ | CLI tools, scripts, testing | Manual/venv |

### Systemd Services (Host)

All services are configured as systemd units but currently inactive:

```bash
# Service files location: /etc/systemd/system/
aitbc-blockchain-node.service      # Blockchain node main process
aitbc-blockchain-rpc.service       # RPC API on port 9080
aitbc-gpu-miner.service           # GPU mining client
aitbc-mock-coordinator.service     # Mock coordinator on port 8090
```

**Service Details:**
- **Working Directory**: `/home/oib/windsurf/aitbc/apps/blockchain-node`
- **Python Environment**: `/home/oib/windsurf/aitbc/apps/blockchain-node/.venv/bin/python`
- **User**: oib
- **Restart Policy**: always (with 5s delay)

**Verification Commands:**
```bash
# Check service status
sc-status aitbc-blockchain-node.service aitbc-blockchain-rpc.service aitbc-gpu-miner.service aitbc-mock-coordinator.service

# Start services
sudo systemctl start aitbc-mock-coordinator.service
sudo systemctl start aitbc-blockchain-node.service

# Check logs
journalctl -u aitbc-mock-coordinator --no-pager -n 20
```

### Python Environment (Host)

Development and testing services on localhost use **Python 3.8+**:

```bash
# Localhost development workspace
/home/oib/windsurf/aitbc/               # Local development
├── .venv/                              # Primary Python environment
├── cli/                                # CLI tools (12 command groups)
├── scripts/                            # Development scripts
└── tests/                              # Pytest suites
```

**Verification Commands:**
```bash
python3 --version                      # Should show Python 3.8+
ls -la /home/oib/windsurf/aitbc/.venv/bin/python  # Check venv
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

## Container: aitbc (10.1.223.93)

### Access
```bash
ssh aitbc-cascade                    # Direct SSH to container
```

### Services

| Service | Port | Process | Python Version | Public URL |
|---------|------|---------|----------------|------------|
| Nginx (web) | 80 | nginx | N/A | https://aitbc.bubuit.net/ |
| Coordinator API | 8000 | python (uvicorn) | 3.11+ | /api/ → /v1/ |
| Blockchain Node RPC | 9080 | python3 | 3.11+ | /rpc/ |
| Wallet Daemon | 8002 | python | 3.11+ | /wallet/ |
| Trade Exchange | 3002 | python (server.py) | 3.11+ | /Exchange |
| Exchange API | 8085 | python | 3.11+ | /api/trades/*, /api/orders/* |

### Python Environment Details

All Python services in the AITBC container run on **Python 3.8+** with isolated virtual environments:

```bash
# Container: aitbc (10.1.223.93)
/opt/coordinator-api/.venv/          # Coordinator API (uvicorn, FastAPI)
/opt/blockchain-node/.venv/          # Blockchain Node 1 (aitbc_chain)
/opt/blockchain-node-2/.venv/        # Blockchain Node 2 (aitbc_chain)
/opt/exchange/.venv/                  # Exchange API (Flask/specific framework)
```

**Verification Commands:**
```bash
ssh aitbc-cascade "python3 --version"  # Should show Python 3.8+
ssh aitbc-cascade "ls -la /opt/*/.venv/bin/python"  # Check venv symlinks
```

### Nginx Routes (container)

Config: `/etc/nginx/sites-enabled/aitbc.bubuit.net`

| Route | Target | Type |
|-------|--------|------|
| `/` | static files (`/var/www/aitbc.bubuit.net/`) | try_files |
| `/explorer/` | Vite SPA (`/var/www/aitbc.bubuit.net/explorer/`) | try_files |
| `/marketplace/` | Vite SPA (`/var/www/aitbc.bubuit.net/marketplace/`) | try_files |
| `/docs/` | static HTML (`/var/www/aitbc.bubuit.net/docs/`) | alias |
| `/Exchange` | proxy → `127.0.0.1:3002` | proxy_pass |
| `/exchange` | 301 → `/Exchange` | redirect |
| `/api/` | proxy → `127.0.0.1:8000/v1/` | proxy_pass |
| `/api/explorer/` | proxy → `127.0.0.1:8000/v1/explorer/` | proxy_pass |
| `/api/users/` | proxy → `127.0.0.1:8000/v1/users/` | proxy_pass |
| `/api/trades/recent` | proxy → `127.0.0.1:8085` | proxy_pass |
| `/api/orders/orderbook` | proxy → `127.0.0.1:8085` | proxy_pass |
| `/admin/` | proxy → `127.0.0.1:8000/v1/admin/` | proxy_pass |
| `/rpc/` | proxy → `127.0.0.1:9080` | proxy_pass |
| `/wallet/` | proxy → `127.0.0.1:8002` | proxy_pass |
| `/v1/` | proxy → `10.1.223.1:8090` (mock coordinator) | proxy_pass |
| `/health` | 200 OK | direct |
| `/Marketplace` | 301 → `/marketplace/` | redirect (legacy) |
| `/BrowserWallet` | 301 → `/docs/browser-wallet.html` | redirect (legacy) |

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
/opt/coordinator-api/          # Coordinator application
├── src/coordinator.db         # Main database
└── .venv/                     # Python environment

/opt/blockchain-node/          # Blockchain Node 1
├── data/chain.db              # Chain database
└── .venv/                     # Python environment

/opt/blockchain-node-2/        # Blockchain Node 2
├── data/chain2.db             # Chain database
└── .venv/                     # Python environment

/opt/exchange/                 # Exchange API
├── data/                      # Exchange data
└── .venv/                     # Python environment
```

### Configuration (container)
- Node 1: `/opt/blockchain-node/src/aitbc_chain/config.py`
- Node 2: `/opt/blockchain-node-2/src/aitbc_chain/config.py`

## Remote Site (ns3)

### Host (ns3-root)
- **IP**: 95.216.198.140
- **Access**: `ssh ns3-root`
- **Bridge**: incusbr0 `192.168.100.1/24`
- **Port forwarding**: firehol (8000, 8081, 8082, 9080 → 192.168.100.10)

### Container (ns3/aitbc)
- **IP**: 192.168.100.10
- **Domain**: aitbc.keisanki.net
- **Access**: `ssh ns3-root` → `incus shell aitbc`
- **Blockchain Node 3**: RPC on port 8082

```bash
curl http://aitbc.keisanki.net/rpc/head    # Node 3 RPC
```

## Cross-Site Synchronization

- **Status**: Active on all 3 nodes
- **Method**: RPC-based polling every 10 seconds
- **Features**: Transaction propagation, height detection, block import
- **Endpoints**:
  - Local: https://aitbc.bubuit.net/rpc/ (Node 1, port 8081)
  - Remote: http://aitbc.keisanki.net/rpc/ (Node 3, port 8082)
- **Consensus**: PoA with 2s block intervals
- **P2P**: Not connected yet; nodes maintain independent chain state

## Development Workspace

```
/home/oib/windsurf/aitbc/      # Local development
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
# From localhost (via container)
ssh aitbc-cascade "curl -s http://localhost:8000/v1/health"
ssh aitbc-cascade "curl -s http://localhost:8081/rpc/head | jq .height"

# From internet
curl -s https://aitbc.bubuit.net/health
curl -s https://aitbc.bubuit.net/api/explorer/blocks

# Remote site
ssh ns3-root "curl -s http://192.168.100.10:8082/rpc/head | jq .height"
```

## Monitoring and Logging

```bash
# Container systemd logs
ssh aitbc-cascade "journalctl -u coordinator-api --no-pager -n 20"
ssh aitbc-cascade "journalctl -u aitbc-blockchain-node-1 --no-pager -n 20"

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
- Coordinator API: localhost origins only (3000, 8080, 8000, 8011)
- Exchange API: localhost origins only
- Blockchain Node: localhost origins only

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
DATABASE_URL=postgresql://user:pass@host/db

# Exchange API
SESSION_SECRET=<secret>
WALLET_ENCRYPTION_KEY=<key>
```
