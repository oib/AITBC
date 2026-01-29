# AITBC Infrastructure Documentation

## Overview
Four-site view: A) localhost (at1, runs miner & Windsurf), B) remote host ns3, C) ns3 container, D) shared capabilities.

## Environment Summary (four sites)

### Site A: Localhost (at1)
- **Role**: Developer box running Windsurf and miner
- **Container**: incus `aitbc`
- **IP**: 10.1.223.93
- **Access**: `ssh aitbc-cascade`
- **Domain**: aitbc.bubuit.net
- **Blockchain Nodes**: Node 1 (rpc 8082), Node 2 (rpc 8081)

#### Site A Services
| Service | Port | Protocol | Node | Status | URL |
|---------|------|----------|------|--------|-----|
| Coordinator API | 8000 | HTTP | - | ✅ Active | https://aitbc.bubuit.net/api/ |
| Blockchain Node 1 RPC | 8082 | HTTP | Node 1 | ✅ Active | https://aitbc.bubuit.net/rpc/ |
| Blockchain Node 2 RPC | 8081 | HTTP | Node 2 | ✅ Active | https://aitbc.bubuit.net/rpc2/ |
| Exchange API | 9080 | HTTP | - | ✅ Active | https://aitbc.bubuit.net/exchange/ |
| Explorer | 3000 | HTTP | - | ✅ Active | https://aitbc.bubuit.net/ |
| Marketplace | 3000 | HTTP | - | ✅ Active | https://aitbc.bubuit.net/marketplace/ |

#### Site A Access
```bash
ssh aitbc-cascade
curl http://localhost:8082/rpc/head   # Node 1 RPC
curl http://localhost:8081/rpc/head   # Node 2 RPC
```

### Site B: Remote Host ns3 (physical)
- **Host IP**: 95.216.198.140
- **Access**: `ssh ns3-root`
- **Bridge**: incusbr0 192.168.100.1/24
- **Purpose**: runs incus container `aitbc` with bc node 3

#### Site B Services
| Service | Port | Protocol | Purpose | Status | URL |
|---------|------|----------|---------|--------|-----|
| incus host bridge | 192.168.100.1/24 | n/a | L2 bridge for container | ✅ Active | n/a |
| SSH | 22 | SSH | Host management | ✅ Active | ssh ns3-root |

#### Site B Access
```bash
ssh ns3-root
```

### Site C: Remote Container ns3/aitbc
- **Container IP**: 192.168.100.10
- **Access**: `ssh ns3-root` → `incus shell aitbc`
- **Domain**: aitbc.keisanki.net
- **Blockchain Nodes**: Node 3 (rpc 8082) — provided by services `blockchain-node` + `blockchain-rpc`

#### Site C Services
| Service | Port | Protocol | Node | Status | URL |
|---------|------|----------|------|--------|-----|
| Blockchain Node 3 RPC | 8082 | HTTP | Node 3 | ✅ Active (service names: blockchain-node/blockchain-rpc) | http://aitbc.keisanki.net/rpc/ |

#### Site C Access
```bash
ssh ns3-root "incus shell aitbc"
curl http://192.168.100.10:8082/rpc/head       # Node 3 RPC (direct)
curl http://aitbc.keisanki.net/rpc/head         # Node 3 RPC (via /rpc/)
```

### Site D: Shared Features
- Transaction-dependent block creation on all nodes
- HTTP polling of RPC mempool
- PoA consensus with 2s intervals
- Cross-site RPC synchronization (transaction propagation)
- Independent chain state; P2P not connected yet

## Network Architecture (YAML)

```yaml
environments:
  site_a_localhost:
    ip: 10.1.223.93
    domain: aitbc.bubuit.net
    container: aitbc
    access: ssh aitbc-cascade
    blockchain_nodes:
      - id: 1
        rpc_port: 8082
        p2p_port: 7070
        status: active
      - id: 2
        rpc_port: 8081
        p2p_port: 7071
        status: active

  site_b_ns3_host:
    ip: 95.216.198.140
    access: ssh ns3-root
    bridge: 192.168.100.1/24

  site_c_ns3_container:
    container_ip: 192.168.100.10
    domain: aitbc.keisanki.net
    access: ssh ns3-root → incus shell aitbc
    blockchain_nodes:
      - id: 3
        rpc_port: 8082
        p2p_port: 7072
        status: active

shared_features:
  transaction_dependent_blocks: true
  rpc_mempool_polling: true
  consensus: PoA
  block_interval_seconds: 2
  cross_site_sync: true
  cross_site_sync_interval: 10
  p2p_connected: false
```

### Site A Extras (dev)

#### Local dev services
| Service | Port | Protocol | Purpose | Status | URL |
|---------|------|----------|---------|--------|-----|
| Test Coordinator | 8001 | HTTP | Local coordinator testing | ⚠️ Optional | http://127.0.0.1:8001 |
| Test Blockchain | 8080 | HTTP | Local blockchain testing | ⚠️ Optional | http://127.0.0.1:8080 |
| Ollama (GPU) | 11434 | HTTP | Local LLM serving | ✅ Available | http://127.0.0.1:11434 |

#### Client applications
| Application | Port | Protocol | Purpose | Connection |
|-------------|------|----------|---------|------------|
| Client Wallet | Variable | HTTP | Submits jobs to coordinator | → 10.1.223.93:8000 |
| Miner Client | Variable | HTTP | Polls for jobs | → 10.1.223.93:8000 |
| Browser Wallet | Browser | HTTP | Web wallet extension | → 10.1.223.93 |

### Site B Extras (host)
- Port forwarding managed via firehol (8000, 8081, 8082, 9080 → 192.168.100.10)
- Firewall host rules: 80, 443 open for nginx; legacy ports optional (8000, 8081, 8082, 9080, 3000)

### Site C Extras (container)
- Internal ports: 8000, 8081, 8082, 9080, 3000, 8080
- Systemd core services: coordinator-api, blockchain-node{,-2,-3}, blockchain-rpc{,-2,-3}, aitbc-exchange; web: nginx, dashboard_server, aitbc-marketplace-ui

### Site D: Shared
- Deployment status:
```yaml
deployment:
  localhost:
    blockchain_nodes: 2
    updated_codebase: true
    transaction_dependent_blocks: true
    last_updated: 2026-01-28
  remote:
    blockchain_nodes: 1
    updated_codebase: true
    transaction_dependent_blocks: true
    last_updated: 2026-01-28
```
- Reverse proxy: nginx (config `/etc/nginx/sites-available/aitbc-reverse-proxy.conf`)
- Service routes: explorer/api/rpc/rpc2/rpc3/exchange/admin on aitbc.bubuit.net
- Alternative subdomains: api.aitbc.bubuit.net, rpc.aitbc.bubuit.net
- Notes: external domains use nginx; legacy direct ports via firehol rules
```

Note: External domains require port forwarding to be configured on the host.

## Data Storage Locations

### Container Paths
```
/opt/coordinator-api/          # Coordinator application
├── src/coordinator.db         # Main database
└── .venv/                     # Python environment

/opt/blockchain-node/          # Blockchain Node 1
├── data/chain.db             # Chain database
└── .venv/                    # Python environment

/opt/blockchain-node-2/        # Blockchain Node 2
├── data/chain2.db            # Chain database
└── .venv/                    # Python environment

/opt/exchange/                 # Exchange API
├── data/                     # Exchange data
└── .venv/                    # Python environment

/var/www/html/                # Static web assets
├── assets/                   # CSS/JS files
└── explorer/                 # Explorer web app
```

### Local Paths
```
/home/oib/windsurf/aitbc/      # Development workspace
├── apps/                      # Application source
├── cli/                       # Command-line tools
├── home/                      # Client/miner scripts
└── tests/                     # Test suites
```

## Network Topology

### Physical Layout
```
Internet
    │
    ▼
┌─────────────────────┐
│   ns3-root         │  ← Host Server (95.216.198.140)
│   ┌─────────────┐  │
│   │  incus      │  │
│   │  aitbc      │  │  ← Container (192.168.100.10/24)
│   │             │  │      NAT → 10.1.223.93
│   └─────────────┘  │
└─────────────────────┘
```

### Access Paths
1. **Direct Container Access**: `ssh aitbc-cascade` → 10.1.223.93
2. **Via Host**: `ssh ns3-root` → `incus shell aitbc`
3. **Service Access**: All services via 10.1.223.93:PORT

## Monitoring and Logging

### Log Locations
```bash
# System logs
journalctl -u coordinator-api
journalctl -u blockchain-node
journalctl -u aitbc-exchange

# Application logs
tail -f /opt/coordinator-api/logs/app.log
tail -f /opt/blockchain-node/logs/chain.log
```

### Health Checks
```bash
# From host server
ssh ns3-root "curl -s http://192.168.100.10:8000/v1/health"
ssh ns3-root "curl -s http://192.168.100.10:8082/rpc/head"
ssh ns3-root "curl -s http://192.168.100.10:9080/health"

# From within container
ssh ns3-root "incus exec aitbc -- curl -s http://localhost:8000/v1/health"
ssh ns3-root "incus exec aitbc -- curl -s http://localhost:8082/rpc/head"
ssh ns3-root "incus exec aitbc -- curl -s http://localhost:9080/health"

# External testing (with port forwarding configured)
curl -s http://aitbc.bubuit.net:8000/v1/health
curl -s http://aitbc.bubuit.net:8082/rpc/head
curl -s http://aitbc.bubuit.net:9080/health
```

## Development Workflow

### 1. Local Development
```bash
# Start local services
cd apps/coordinator-api
python -m uvicorn src.app.main:app --reload --port 8001

# Run tests
python -m pytest tests/
```

### 2. Container Deployment
```bash
# Deploy to container
bash scripts/deploy/deploy-to-server.sh

# Update specific service
scp src/app/main.py ns3-root:/tmp/
ssh ns3-root "incus exec aitbc -- sudo systemctl restart coordinator-api"
```

### 3. Testing Endpoints
```bash
# Local testing
curl http://127.0.0.1:8001/v1/health

# Remote testing (from host)
ssh ns3-root "curl -s http://192.168.100.10:8000/v1/health"

# Remote testing (from container)
ssh ns3-root "incus exec aitbc -- curl -s http://localhost:8000/v1/health"

# External testing (with port forwarding)
curl -s http://aitbc.keisanki.net:8000/v1/health
```

## Security Considerations

### Access Control
- API keys required for coordinator (X-Api-Key header)
- Firewall blocks unnecessary ports
- Nginx handles SSL termination

### Isolation
- Services run as non-root users where possible
- Databases in separate directories
- Virtual environments for Python dependencies

## Monitoring

### Health Check Commands
```bash
# Localhost
ssh aitbc-cascade "systemctl status blockchain-node blockchain-node-2"
ssh aitbc-cascade "curl -s http://localhost:8082/rpc/head | jq .height"

# Remote
ssh ns3-root "systemctl status blockchain-node-3"
ssh ns3-root "curl -s http://192.168.100.10:8082/rpc/head | jq .height"
```

## Configuration Files

### Localhost Configuration
- Node 1: `/opt/blockchain-node/src/aitbc_chain/config.py`
- Node 2: `/opt/blockchain-node-2/src/aitbc_chain/config.py`

### Remote Configuration
- Node 3: `/opt/blockchain-node/src/aitbc_chain/config.py`

## Notes
- Nodes are not currently connected via P2P
- Each node maintains independent blockchain state
- All nodes implement transaction-dependent block creation
- Cross-site synchronization enabled for transaction propagation
- Domain aitbc.bubuit.net points to localhost environment
- Domain aitbc.keisanki.net points to remote environment

## Cross-Site Synchronization
- **Status**: Active on all nodes (fully functional)
- **Method**: RPC-based polling every 10 seconds
- **Features**: 
  - Transaction propagation between sites
  - Height difference detection
  - ✅ Block import with transaction support (`/blocks/import` endpoint)
- **Endpoints**:
  - Local nodes: https://aitbc.bubuit.net/rpc/ (port 8081)
  - Remote node: http://aitbc.keisanki.net/rpc/
- **Nginx Configuration**:
  - Site A: `/etc/nginx/sites-available/aitbc.bubuit.net` → `127.0.0.1:8081`
  - Fixed routing issue (was pointing to 8082, now correctly routes to 8081)

3. **Monitoring**: Add Prometheus + Grafana
4. **CI/CD**: Automated deployment pipeline
5. **Security**: OAuth2/JWT authentication, rate limiting
