# AITBC Infrastructure Documentation

> Last updated: 2026-03-10 (Updated nginx configuration with new port logic implementation)

## Overview

Two-tier architecture: **aitbc1 primary server** (https://aitbc1.bubuit.net) and **aitbc secondary server** (https://aitbc.bubuit.net) with **aitbc1 as reverse proxy** forwarding all traffic to aitbc container services. **Updated for port logic 8000+ implementation with unified numbering scheme and production-ready codebase.**

```
Internet → aitbc1.bubuit.net (HTTPS :443) → aitbc.bubuit.net
    │
    ▼
┌──────────────────────────────────────────────┐
│  aitbc1 Primary Server (Reverse Proxy)        │
│  Nginx reverse proxy (:443 SSL → :80)       │
│  Config: /etc/nginx/sites-available/         │
│          aitbc-proxy.conf                    │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Container: aitbc (aitbc server)      │  │
│  │  Access: ssh aitbc                    │  │
│  │  OS: Debian 13 Trixie                  │  │
│  │  Node.js: 24+                          │  │
│  │  Python: 3.13.5+                       │  │
│  │  GPU Access: None (CPU-only mode)     │  │
│  │  Miner Service: Not needed              │  │
│  │                                        │  │
│  │  Nginx (:80) → routes to services:    │  │
│  │    /              → static website     │  │
│  │    /api/          → :8000 (coordinator)│  │
│  │    /exchange/     → :8001 (exchange)  │  │
│  │    /rpc/          → :8006 (blockchain) │  │
│  │    /wallet/       → :8000 (wallet)     │  │
│  │    /health        → :8000 (health)    │  │
│  │    /gpu/multimodal/ → :8010            │  │
│  │    /gpu/service/   → :8011             │  │
│  │    /optimization/  → :8012             │  │
│  │    /learning/      → :8013             │  │
│  │    /marketplace/enhanced/ → :8014      │  │
│  │    /openclaw/      → :8015             │  │
│  │    /explorer/      → :8016             │  │
│  │    /balancer/      → :8017             │  │
│  │                                        │  │
│  │  Config: /etc/nginx/sites-enabled/     │  │
│  │          aitbc.bubuit.net              │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

## Port Logic Implementation (Updated March 10, 2026)

### **Core Services (8000-8001) - AT1 STANDARD REFERENCE**
- **Port 8000**: Coordinator API ✅ PRODUCTION READY
- **Port 8001**: Exchange API ✅ PRODUCTION READY (127.0.0.1 binding)

### **Blockchain Services (8005-8006) - AT1 STANDARD REFERENCE**
- **Port 8005**: Primary Blockchain Node ✅ PRODUCTION READY (aitbc-blockchain-node.service)
- **Port 8006**: Primary Blockchain RPC ✅ PRODUCTION READY (aitbc-blockchain-rpc.service)

### **Enhanced Services (8010-8017) - CPU-ONLY MODE**
- **Port 8010**: Multimodal GPU Service ✅ PRODUCTION READY (CPU-only mode)
- **Port 8011**: GPU Multimodal Service ✅ PRODUCTION READY (CPU-only mode)
- **Port 8012**: Modality Optimization Service ✅ PRODUCTION READY
- **Port 8013**: Adaptive Learning Service ✅ PRODUCTION READY
- **Port 8014**: Marketplace Enhanced Service ✅ PRODUCTION READY
- **Port 8015**: OpenClaw Enhanced Service ✅ PRODUCTION READY
- **Port 8016**: Blockchain Explorer Service ✅ PRODUCTION READY
- **Port 8017**: Geographic Load Balancer ✅ PRODUCTION READY

### **Mock & Test Services (8020-8029)**
- **Port 8020**: Mock Coordinator API ✅ TESTING READY
- **Port 8021**: Coordinator API (dev) ✅ TESTING READY
- **Port 8022**: Test Blockchain Node (localhost) ✅ TESTING READY
- **Port 8023**: Mock Exchange API ✅ TESTING READY
- **Port 8024**: Mock Blockchain RPC ✅ TESTING READY
- **Port 8025**: Development Blockchain Node ✅ TESTING READY (aitbc-blockchain-node-dev.service)
- **Port 8026**: Development Blockchain RPC ✅ TESTING READY (aitbc-blockchain-rpc-dev.service)
- **Port 8027**: Load Testing Endpoint ✅ TESTING READY
- **Port 8028**: Integration Test API ✅ TESTING READY
- **Port 8029**: Performance Monitor ✅ TESTING READY

### **Container Services (8080-8089) - LEGACY**
- **Port 8080**: Container Coordinator API (aitbc) ⚠️ LEGACY - Use port 8000-8003 range
- **Port 8081**: Container Blockchain Node 1 ⚠️ LEGACY - Use port 8010+ range
- **Port 8082**: Container Exchange API ⚠️ LEGACY - Use port 8010+ range
- **Port 8083**: Container Wallet Daemon ⚠️ LEGACY - Use port 8010+ range
- **Port 8084**: Container Blockchain Node 2 ⚠️ LEGACY - Use port 8010+ range
- **Port 8085**: Container Explorer UI ⚠️ LEGACY - Use port 8010+ range
- **Port 8086**: Container Marketplace ⚠️ LEGACY - Use port 8010+ range
- **Port 8087**: Container Miner Dashboard ⚠️ LEGACY - Use port 8010+ range
- **Port 8088**: Container Load Balancer ⚠️ LEGACY - Use port 8010+ range
- **Port 8089**: Container Debug API ⚠️ LEGACY - Use port 8010+ range

### **Legacy Ports (Decommissioned)**
- **Port 8003**: Previously Primary Blockchain RPC - Decommissioned (moved to port 8006)
- **Port 8090**: No longer used by AITBC
- **Port 9080**: Successfully decommissioned
- **Port 8009**: No longer in use

## Incus Host (at1)

### Host Details
- **Hostname**: `at1` (primary development workstation)
- **Environment**: Windsurf development environment
- **OS**: Debian 13 Trixie (development environment)
- **Node.js**: 24+ (current tested: v24.14.x)
- **Python**: 3.13.5+ (minimum requirement, strictly enforced)
- **GPU Access**: **Primary GPU access location** - all GPU workloads must run on at1
- **Architecture**: x86_64 Linux with CUDA GPU support

### Services (Host)

| Service | Port | Process | Python Version | Purpose | Status |
|---------|------|---------|----------------|---------|--------|
| Coordinator API | 8000 | python3 | 3.13.5+ | Production coordinator API | systemd: aitbc-coordinator-api.service |
| Mock Coordinator | 8020 | python3 | 3.13.5+ | Development/testing API endpoint | systemd: aitbc-mock-coordinator.service |
| Blockchain Node | N/A | python3 | 3.13.5+ | Local blockchain node | systemd: aitbc-blockchain-node.service |
| Blockchain Node RPC | 8003 | python3 | 3.13.5+ | RPC API for blockchain | systemd: aitbc-blockchain-rpc.service |
| Local Development Tools | Varies | python3 | 3.13.5+ | CLI tools, scripts, testing | Manual/venv |
| **Note**: GPU Miner Client removed - no miner service needed on aitbc server |
| **Port Logic**: Production services use 8000-8019, Mock/Testing services use 8020+ |

### Systemd Services (Host)

All services are configured as systemd units but currently inactive:

```bash
# Service files location: /etc/systemd/system/
aitbc-coordinator-api.service       # Production coordinator API on port 8000
aitbc-blockchain-node.service       # Blockchain node main process
aitbc-blockchain-rpc.service        # RPC API on port 8003
aitbc-mock-coordinator.service      # Mock coordinator on port 8020
# Note: aitbc-gpu-miner.service removed - no miner service needed
```

**Service Details:**
- **Working Directory**: `/opt/aitbc/` (standard path for all services)
- **Python Environment**: `/opt/aitbc/.venv/bin/python` (Python 3.13.5+)
- **Node.js Environment**: System Node.js 24+ (current tested: v24.14.x)
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
systemctl start aitbc-mock-coordinator.service
systemctl start aitbc-blockchain-node.service

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
node --version                          # Should show v24.14.x
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
node --version                              # Should show v24.14.x
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
ssh aitbc                          # Direct SSH to aitbc server
```

**GPU Access**: No GPU passthrough. All GPU workloads must run on **at1** (Windsurf development host), not inside incus containers.

**Miner Service**: Not needed - aitbc server operates in CPU-only mode.

**Host Proxies (for localhost GPU clients)**
- `127.0.0.1:18000` → container `127.0.0.1:8000` (coordinator/marketplace API)
- Use this to submit offers/bids/contracts/mining requests from localhost GPU miners/dev clients.

**Container Services (Updated March 5, 2026 - Port Logic 8000+)**
- **12 Services**: All 12 services operational with unified port logic
- **Core Services**: 8000-8003 (Coordinator, Exchange, Blockchain Node, RPC)
- **Enhanced Services**: 8010-8017 (GPU services in CPU-only mode, Web UI, Load Balancer)
- **Port Logic**: All services use 8000+ numbering scheme for consistency
- **0.0.0.0 Binding**: All services bind to 0.0.0.0 for container access
- **Production Ready**: All services marked as production ready

**Port Logic Breakdown:**
- **8000**: Coordinator API (main API gateway)
- **8001**: Cross-Chain Exchange API (Multi-chain trading operations)
- **8002**: Blockchain Node (P2P node service)
- **8003**: Blockchain RPC (JSON-RPC interface)
- **8007**: Blockchain Service (Transaction processing and consensus)
- **8008**: Network Service (P2P block propagation)
- **8016**: Blockchain Explorer (Data aggregation and web interface)
- **8010**: Multimodal GPU (AI processing)
- **8011**: GPU Multimodal (multi-modal AI)
- **8012**: Modality Optimization (AI optimization)
- **8013**: Adaptive Learning (machine learning)
- **8014**: Marketplace Enhanced (advanced marketplace)
- **8015**: OpenClaw Enhanced (agent marketplace)
- **8016**: Web UI (dashboard interface)
- **8017**: Geographic Load Balancer (traffic distribution)

## Container: aitbc1 (10.1.223.40) — New Dev Server

### Access
```bash
ssh aitbc1-cascade                   # Direct SSH to aitbc1 container (incus)
```

### Notes
- Purpose: secondary AITBC dev environment (incus container)
- Host: 10.1.223.40 (Debian 13 Trixie), accessible via new SSH alias `aitbc1-cascade`
- OS: Debian 13 Trixie (development environment)
- Node.js: 24+ (current tested: v24.14.x)
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


### Services (Port Logic 8000+)

| Service | Port (8000+) | Process | Python Version | Public URL | Status |
|---------|-------------|---------|----------------|------------|--------|
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

**Python 3.13.5 and Node.js 24+ Upgrade Complete** (2026-03-05):
- All services upgraded to Python 3.13.5
- Node.js upgraded to 24+ (current tested: v24.14.x)
- Virtual environments updated and verified
- API routing fixed for external access
- Services fully operational with enhanced performance
- **Port Logic 8000+**: Unified numbering scheme implemented
  - Core Services: 8000-8003 (Coordinator, Exchange, Blockchain, RPC)
  - Enhanced Services: 8010-8017 (AI, GPU, Web UI, Load Balancer)
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

**Minimum Default Verification Commands:**
```bash
# From aitbc1 primary server
ssh aitbc "python3 --version"  # Should show Python 3.13.5
ssh aitbc "node --version"      # Should show v24.14.x
ssh aitbc "npm --version"       # Should show compatible version
ssh aitbc "ls -la /opt/*/.venv/bin/python"  # Check venv symlinks
ssh aitbc "curl -s http://127.0.0.1:8000/v1/health"  # Coordinator API health
curl -s https://aitbc.bubuit.net/api/v1/health  # External API access
```

**SSH Access:**
```bash
# From aitbc1 to aitbc (secondary server)
ssh aitbc

# From aitbc to aitbc1 (primary server)  
ssh aitbc1
```

### Nginx Routes (container)

Config: `/etc/nginx/sites-enabled/aitbc`

| Route | Target | Type | Status |
|-------|--------|------|--------|
| `/` | static files (`/var/www/html/`) | try_files | ✅ |
| `/api/` | proxy → `127.0.0.1:8000/v1/` | proxy_pass | ✅ |
| `/exchange/` | proxy → `127.0.0.1:8001/` | proxy_pass | ✅ |
| `/rpc/` | proxy → `127.0.0.1:8006/rpc/` | proxy_pass | ✅ |
| `/wallet/` | proxy → `127.0.0.1:8000/wallet/` | proxy_pass | ✅ |
| `/health` | proxy → `127.0.0.1:8000/v1/health` | proxy_pass | ✅ |
| `/gpu/multimodal/` | proxy → `127.0.0.1:8010/` | proxy_pass | ✅ (CPU-only) |
| `/gpu/service/` | proxy → `127.0.0.1:8011/` | proxy_pass | ✅ (CPU-only) |
| `/optimization/` | proxy → `127.0.0.1:8012/` | proxy_pass | ✅ |
| `/learning/` | proxy → `127.0.0.1:8013/` | proxy_pass | ✅ |
| `/marketplace/enhanced/` | proxy → `127.0.0.1:8014/` | proxy_pass | ✅ |
| `/openclaw/` | proxy → `127.0.0.1:8015/` | proxy_pass | ✅ |
| `/explorer/` | proxy → `127.0.0.1:8016/` | proxy_pass | ✅ |
| `/balancer/` | proxy → `127.0.0.1:8017/` | proxy_pass | ✅ |

**API Routing Updated** (2026-03-10):
- Updated nginx configuration to use new port logic from infrastructure documentation
- Updated RPC route from port 8003 to port 8006 (blockchain services)
- Updated Exchange API route to port 8001 (core services)
- Added Enhanced Services routes with correct port mappings (8010-8017)
- Simplified configuration for HTTP-only mode (SSL handled by host reverse proxy)
- External API access: `https://aitbc.bubuit.net/api/v1/health` → `{"status":"ok","env":"dev"}`
- All GPU services configured for CPU-only mode

### Web Root (`/var/www/html/`)

```
/var/www/html/
├── index.html              # Main website
├── 404.html                # Error page
└── static files            # CSS, JS, images
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

## Known Limitations and Compatibility Issues

### Concrete ML Python 3.13 Compatibility

**Status**: ⚠️ **Known Limitation**  
**Severity**: 🟡 **Medium** (Functional limitation, no security impact)  
**Date Identified**: March 5, 2026

#### Issue Description
The Coordinator API service logs a warning about Concrete ML not being installed due to Python version incompatibility:

```
WARNING:root:Concrete ML not installed; skipping Concrete provider. Concrete ML requires Python <3.13. Current version: 3.13.5
```

#### Technical Details
- **Affected Component**: Coordinator API FHE (Fully Homomorphic Encryption) Service
- **Root Cause**: Concrete ML library requires Python <3.13, but AITBC runs on Python 3.13.5
- **Impact**: Limited to Concrete ML FHE provider; TenSEAL provider continues to work normally
- **Current Status**: Service operates normally with TenSEAL provider only

#### Compatibility Matrix
| Python Version | Concrete ML Support | AITBC Status |
|---------------|-------------------|--------------|
| 3.8.x - 3.12.x | ✅ Supported | ❌ Not used |
| 3.13.x | ❌ Not Supported | ✅ Current version |
| 3.14+ | ❌ Unknown | ❌ Future consideration |

#### Functional Impact
- **FHE Operations**: ✅ **No Impact** - TenSEAL provides full FHE functionality
- **API Endpoints**: ✅ **No Impact** - All FHE endpoints work normally
- **Performance**: ✅ **No Impact** - TenSEAL performance is excellent
- **Security**: ✅ **No Impact** - Encryption schemes remain secure

#### Feature Limitations
- **Neural Network Compilation**: ❌ **Unavailable** - Concrete ML specific feature
- **Advanced ML Models**: ⚠️ **Limited** - Some complex models may require Concrete ML
- **Research Features**: ❌ **Unavailable** - Experimental Concrete ML features

#### Resolution Strategy
- **Short Term**: Continue with TenSEAL-only implementation (already in place)
- **Medium Term**: Monitor Concrete ML for Python 3.13 compatibility updates
- **Long Term**: Consider dual Python environment if business need arises

#### Related Documentation
- See `docs/12_issues/concrete-ml-compatibility.md` for detailed technical analysis
- Monitoring and alerting configured for service health
- No user-facing impact or action required

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
scp -r website/* aitbc:/var/www/aitbc.bubuit.net/

# Push app updates (blockchain-explorer serves its own interface)
# No separate deployment needed - blockchain-explorer handles both API and UI

# Restart a service
ssh aitbc "systemctl restart coordinator-api"
```

## Health Checks

```bash
# From aitbc1 (via aitbc server)
ssh aitbc "curl -s http://localhost:8000/v1/health"
ssh aitbc "curl -s http://localhost:8003/rpc/head | jq .height"

# Test enhanced services
ssh aitbc "curl -s http://localhost:8010/health"  # Multimodal GPU (CPU-only)
ssh aitbc "curl -s http://localhost:8017/health"  # Geographic Load Balancer

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
ssh aitbc "python3 --version"  # Python 3.13.5
```

## Monitoring and Logging

```bash
# Container systemd logs
ssh aitbc "journalctl -u aitbc-coordinator-api --no-pager -n 20"
ssh aitbc "journalctl -u aitbc-blockchain-node --no-pager -n 20"

# Enhanced services logs
ssh aitbc "journalctl -u aitbc-multimodal-gpu --no-pager -n 20"
ssh aitbc "journalctl -u aitbc-loadbalancer-geo --no-pager -n 20"

# Container nginx logs
ssh aitbc "tail -20 /var/log/nginx/aitbc.bubuit.net.error.log"

# Host nginx logs
tail -20 /var/log/nginx/error.log
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

### Container Access & Port Logic (Updated March 6, 2026)

#### **SSH-Based Server Access**
```bash
# Access aitbc server
ssh aitbc

# Access aitbc1 server (from incus host only)
ssh aitbc1-cascade

# Check services in servers
ssh aitbc 'systemctl list-units | grep aitbc-'

# Debug specific services
ssh aitbc 'systemctl status aitbc-coordinator-api'
```

#### **Port Distribution Strategy - NEW STANDARD**
```bash
# === NEW STANDARD PORT LOGIC ===

# Core Services (8000-8003) - NEW STANDARD
- Port 8000: Coordinator API (local) ✅ NEW STANDARD
- Port 8001: Exchange API (local) ✅ NEW STANDARD
- Port 8002: Blockchain Node (local) ✅ NEW STANDARD
- Port 8003: Blockchain RPC (local) ✅ NEW STANDARD

# Blockchain Services (8004-8005) - PRODUCTION READY
- Port 8004: Primary Blockchain Node ✅ PRODUCTION READY (aitbc-blockchain-node.service)
- Port 8005: Blockchain RPC 2 ✅ PRODUCTION READY

# Level 2 Services (8010-8017) - NEW STANDARD
- Port 8010: Multimodal GPU Service ✅ NEW STANDARD
- Port 8011: GPU Multimodal Service ✅ NEW STANDARD
- Port 8012: Modality Optimization Service ✅ NEW STANDARD
- Port 8013: Adaptive Learning Service ✅ NEW STANDARD
- Port 8014: Marketplace Enhanced Service ✅ NEW STANDARD
- Port 8015: OpenClaw Enhanced Service ✅ NEW STANDARD
- Port 8016: Web UI Service ✅ NEW STANDARD
- Port 8017: Geographic Load Balancer ✅ NEW STANDARD

# Mock & Test Services (8020-8029) - NEW STANDARD
- Port 8020: Mock Coordinator API ✅ NEW STANDARD
- Port 8021: Coordinator API (dev) ✅ NEW STANDARD
- Port 8022: Test Blockchain Node (localhost) ✅ NEW STANDARD
- Port 8025: Development Blockchain Node ✅ NEW STANDARD (aitbc-blockchain-node-dev.service)
- Port 8026-8029: Additional testing services ✅ NEW STANDARD

# === LEGACY PORTS (DEPRECATED) ===

# Legacy Container Services (8080-8089) - DEPRECATED
- Port 8080-8089: All container services ⚠️ DEPRECATED - Use 8000+ and 8010+ ranges
```

#### **Service Naming Convention**
```bash
# === STANDARDIZED SERVICE NAMES ===

# Primary Production Services:
✅ aitbc-blockchain-node.service (port 8005) - Primary blockchain node
✅ aitbc-blockchain-rpc.service (port 8006) - Primary blockchain RPC (localhost + containers)
✅ aitbc-coordinator-api.service (port 8000) - Main coordinator API
✅ aitbc-exchange-api.service (port 8001) - Exchange API
✅ aitbc-wallet.service (port 8002) - Wallet Service (localhost + containers)

# Development/Test Services:
✅ aitbc-blockchain-node-dev.service (port 8025) - Development blockchain node
✅ aitbc-blockchain-rpc-dev.service (port 8026) - Development blockchain RPC
✅ aitbc-coordinator-api-dev.service (port 8021) - Development coordinator API

# Container Locations:
✅ localhost (at1): Primary services + development services
✅ aitbc container: Primary services + development services
✅ aitbc1 container: Primary services + development services
```

#### **Port Conflict Resolution**
```bash
# Updated port assignments - NO CONFLICTS:
# Local services use 8000-8003 range (core services)
# Blockchain services use 8004-8005 range (primary blockchain nodes)
# Level 2 services use 8010-8017 range (enhanced services)
# Mock & test services use 8020-8029 range (development services)

# Check port usage
netstat -tlnp | grep -E ":(800[0-5]|801[0-7]|802[0-9])"
ssh aitbc 'netstat -tlnp | grep -E ":(800[0-5]|801[0-7]|802[0-9])'

# Service Management Commands:
# Primary services:
systemctl status aitbc-blockchain-node.service  # localhost
systemctl status aitbc-blockchain-rpc.service   # localhost (port 8006)
systemctl status aitbc-wallet.service          # localhost (port 8002)
ssh aitbc 'systemctl status aitbc-blockchain-node.service'  # aitbc server

# Wallet services:
ssh aitbc 'systemctl status aitbc-wallet.service'  # port 8002

# RPC services:
ssh aitbc 'systemctl status aitbc-blockchain-rpc.service'    # port 8006
ssh aitbc 'systemctl status aitbc-blockchain-rpc-dev.service' # port 8026

# Development services:
ssh aitbc 'systemctl status aitbc-blockchain-node-dev.service'
```
