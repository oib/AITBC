---
description: Comprehensive AITBC service-to-port mapping reference for all nodes and environments (v0.4.7+)
title: AITBC Service Port Mapping
version: 2.0
---

# AITBC Service Port Mapping Skill

## Purpose
Provide comprehensive service-to-port mapping reference for AITBC blockchain platform across all nodes (localhost, aitbc1, gitea-runner) and environments.

## Activation
Trigger when user needs to know which service runs on which port, troubleshoot port conflicts, configure service endpoints, or understand service architecture.

## Core AITBC Services (v0.4.7+ Architecture)

### API Gateway & Routing
- **8201**: API Gateway (api_gateway.main)
  - Purpose: Routes requests to all microservices (marketplace, coordinator, blockchain, etc.)
  - Nodes: localhost, aitbc1
  - Service: aitbc-api-gateway.service
  - Config: Hardcoded in service (port 8201)
  - Routes: /api/* → microservices

### Blockchain Layer
- **8202**: Blockchain RPC (aitbc_chain.app)
  - Purpose: Main blockchain RPC endpoint for block queries, transactions, and chain operations
  - Nodes: localhost, aitbc1, gitea-runner
  - Service: aitbc-blockchain-rpc.service, aitbc-blockchain-node.service
  - Wrapper: aitbc-blockchain-rpc-wrapper.py
  - Config: RPC_BIND_PORT environment variable (default: 8202)

- **7070**: P2P Mesh Network (aitbc_chain.p2p_network)
  - Purpose: Peer-to-peer gossip protocol for block propagation and node discovery
  - Nodes: localhost, aitbc1
  - Service: aitbc-blockchain-p2p.service
  - Wrapper: aitbc-blockchain-p2p-wrapper.py
  - Config: P2P_BIND_PORT environment variable (default: 7070)

### Coordinator & Agent Layer
- **8203**: Coordinator API (app.main)
  - Purpose: Agent coordination, messaging, and cross-node communication
  - Nodes: localhost, aitbc1
  - Service: aitbc-coordinator-api.service
  - Config: Hardcoded in service (port 8203)
  - Routes: /v1/coordinator/*, /v1/hermes/*

- **8103**: Hermes (aitbc-hermes-wrapper.py)
  - Purpose: AI agent communication and coordination framework
  - Nodes: localhost
  - Service: aitbc-hermes.service
  - Wrapper: aitbc-hermes-wrapper.py
  - Config: Hardcoded in wrapper (port 8103)

### Marketplace & Services
- **8102**: Marketplace Service (marketplace_service.main)
  - Purpose: Software service registry with reputation system
  - Nodes: localhost, aitbc1
  - Service: aitbc-marketplace.service
  - Config: Hardcoded in service (port 8102)
  - Routes: /v1/marketplace/*, /v1/plugin/*

- **8109**: Plugin Registry (plugin_service.main)
  - Purpose: Service plugin management and registry
  - Nodes: localhost, aitbc1
  - Service: aitbc-plugin.service
  - Config: Hardcoded in service (port 8109)
  - Routes: /plugin/*

### AI & Media Services
- **11434**: Ollama (ollama serve)
  - Purpose: Local LLM inference service for AI operations
  - Nodes: localhost
  - Service: ollama
  - Config: Default Ollama port (11434)
  - Routes: /ollama/*

- **8110**: Whisper (whisper_service.main)
  - Purpose: Audio transcription service with GPU acceleration
  - Nodes: localhost, aitbc1
  - Service: aitbc-whisper.service
  - Config: Hardcoded in service (port 8110)
  - Routes: /whisper/*

- **8230**: FFmpeg (ffmpeg_service.main)
  - Purpose: GPU-accelerated video processing service
  - Nodes: localhost, aitbc1
  - Service: aitbc-ffmpeg.service
  - Config: Hardcoded in service (port 8230)
  - Routes: /v1/ffmpeg/*

## Infrastructure Services

### Database & Cache
- **5432**: PostgreSQL
  - Purpose: Relational database for coordinator, marketplace, and other services
  - Nodes: localhost, aitbc1, gitea-runner
  - Service: postgresql

- **6379**: Redis
  - Purpose: Cache, message queue, and session storage
  - Nodes: localhost, aitbc1, gitea-runner
  - Service: redis

### Web & Proxy
- **80**: Nginx
  - Purpose: Reverse proxy and web server for HTTPS termination and load balancing
  - Nodes: localhost
  - Service: nginx

- **443**: Nginx HTTPS
  - Purpose: HTTPS endpoint for public API access
  - Nodes: localhost
  - Service: nginx

### Communication
- **22**: SSH
  - Purpose: Secure shell access for remote management
  - Nodes: localhost, aitbc1, gitea-runner
  - Service: sshd

- **25**: SMTP
  - Purpose: Email delivery for notifications
  - Nodes: localhost, aitbc1, gitea-runner
  - Service: postfix

### Real-time Communication
- **3478**: TURN Server
  - Purpose: WebRTC TURN relay for real-time communication
  - Nodes: localhost
  - Service: coturn

### AI Infrastructure
- **11434**: Ollama
  - Purpose: Local LLM inference service for AI operations
  - Nodes: localhost
  - Service: ollama

## Port Conflict Resolution

### Known Conflicts & Resolutions (v0.4.7+)
- No known port conflicts in current architecture
- Legacy conflicts resolved by service consolidation and reorganization

### Port Allocation Guidelines (v0.4.7+)
- **7000-7099**: P2P and networking services (7070: P2P mesh)
- **8000-8099**: Legacy services (deprecated in v0.4.7)
- **8100-8199**: Core microservices (8102: Marketplace, 8103: Hermes, 8109: Plugin Registry, 8110: Whisper)
- **8200-8299**: API Gateway and infrastructure (8201: API Gateway, 8202: Blockchain RPC, 8203: Coordinator API)
- **8230-8299**: Media processing (8230: FFmpeg)
- **9000-9099**: Agent coordination and orchestration (if needed)
- **11434**: Ollama LLM inference (standard port)

## Service Discovery Commands

### Check Active Ports
```bash
# Localhost
sudo lsof -i -P -n | grep LISTEN

# Remote nodes
ssh aitbc1 "sudo lsof -i -P -n | grep LISTEN"
ssh gitea-runner "sudo lsof -i -P -n | grep LISTEN"
```

### Check Service Status
```bash
# All AITBC services
systemctl status aitbc-*.service

# Specific service
systemctl status aitbc-coordinator-api.service
```

### Check Service Port Configuration
```bash
# Systemd service files
grep -r "port" /etc/systemd/system/aitbc-*.service

# Wrapper scripts
grep -r "port" /opt/aitbc/apps/*/aitbc-*-wrapper.py
```

### Test Service Endpoints (v0.4.7+)
```bash
# API Gateway health
curl http://localhost:8201/health

# Blockchain RPC head
curl http://localhost:8202/rpc/head

# Coordinator API health
curl http://localhost:8203/v1/health

# Marketplace service health
curl http://localhost:8102/v1/marketplace/health

# Hermes health
curl http://localhost:8103/v1/hermes/health

# Whisper health
curl http://localhost:8110/health

# Plugin registry
curl http://localhost:8109/plugins

# Ollama models
curl http://localhost:11434/api/tags

# FFmpeg health
curl http://localhost:8230/health
```

## Environment Variables

### Port Configuration Variables (v0.4.7+)
- `RPC_BIND_PORT`: Blockchain RPC port (default: 8202)
- `P2P_BIND_PORT`: P2P network port (default: 7070)
- `API_GATEWAY_PORT`: API Gateway port (default: 8201)
- `COORDINATOR_API_PORT`: Coordinator API port (default: 8203)
- `MARKETPLACE_SERVICE_PORT`: Marketplace service port (default: 8102)
- `HERMES_PORT`: Hermes port (default: 8103)
- `WHISPER_PORT`: Whisper port (default: 8110)
- `PLUGIN_REGISTRY_PORT`: Plugin registry port (default: 8109)
- `FFMPEG_PORT`: FFmpeg port (default: 8230)

### Node-Specific Configuration
- `/etc/aitbc/.env`: Environment configuration
- `/etc/aitbc/node.env`: Node-specific configuration
- `/run/aitbc/secrets/.env`: Runtime secrets

## Troubleshooting

### Port Already in Use
1. Identify process: `sudo lsof -i :<port>`
2. Kill stale process: `sudo kill -9 <PID>`
3. Restart service: `sudo systemctl restart <service>`

### Service Not Listening
1. Check service status: `systemctl status <service>`
2. Check logs: `journalctl -u <service> -n 50`
3. Verify port configuration in wrapper script
4. Check firewall rules: `sudo iptables -L -n`

### Port Conflicts
1. Identify conflicting services using same port
2. Update one service to use different port
3. Update systemd service file and wrapper script
4. Reload systemd: `sudo systemctl daemon-reload`
5. Restart affected services

## Node-Specific Service Distribution (v0.4.7+)

### aitbc3 (Production Node)
- Core: 8202 (Blockchain RPC), 7070 (P2P)
- Gateway: 8201 (API Gateway)
- Coordinator: 8203 (Coordinator API), 8103 (Hermes)
- Marketplace: 8102 (Marketplace Service), 8109 (Plugin Registry)
- Services: 8110 (Whisper), 8230 (FFmpeg), 11434 (Ollama)
- Infrastructure: 80, 443 (Nginx), 5432 (PostgreSQL), 6379 (Redis)

### Hub Node (aitbc)
- Core: 8202 (Blockchain RPC), 7070 (P2P)
- Gateway: 8201 (API Gateway)
- Coordinator: 8203 (Coordinator API), 8103 (Hermes)
- Marketplace: 8102 (Marketplace Service)
- Services: 11434 (Ollama)
- Infrastructure: 80, 443 (Nginx), 5432 (PostgreSQL), 6379 (Redis)

### Shop Nodes
- Core: 8202 (Blockchain RPC), 7070 (P2P)
- Gateway: 8201 (API Gateway)
- Services: 11434 (Ollama), 8110 (Whisper - if GPU available)
- Infrastructure: 5432 (PostgreSQL), 6379 (Redis)

## Best Practices

### Port Configuration
1. Use environment variables for port configuration where possible
2. Document port changes in service files
3. Update wrapper scripts when changing ports
4. Test port availability before service deployment
5. Use standard port ranges for service categories

### Service Management
1. Always reload systemd after service file changes
2. Check service logs after port changes
3. Verify service health after restart
4. Monitor port conflicts during deployment
5. Document custom port configurations

### Security Considerations
1. Bind sensitive services to localhost when possible
2. Use firewall rules to restrict port access
3. Avoid exposing internal services to public internet
4. Use reverse proxy for public-facing services
5. Monitor port usage for unauthorized access

## Related Documentation
- [Multi-Node Operations](/opt/aitbc/docs/skills/aitbc-multi-node-operations.md)
- [Basic Operations](/opt/aitbc/docs/skills/aitbc-basic-operations.md)
- [Agent Coordinator](/opt/aitbc/docs/agent-coordinator/ARCHITECTURE.md)
- [Blockchain Troubleshooting](/opt/aitbc/docs/skills/aitbc-blockchain-troubleshooting.md)
