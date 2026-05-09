---
description: Comprehensive AITBC service-to-port mapping reference for all nodes and environments
title: AITBC Service Port Mapping
version: 1.0
---

# AITBC Service Port Mapping Skill

## Purpose
Provide comprehensive service-to-port mapping reference for AITBC blockchain platform across all nodes (localhost, aitbc1, gitea-runner) and environments.

## Activation
Trigger when user needs to know which service runs on which port, troubleshoot port conflicts, configure service endpoints, or understand service architecture.

## Core AITBC Services

### Blockchain Layer
- **8006**: Blockchain RPC (aitbc_chain.app)
  - Purpose: Main blockchain RPC endpoint for block queries, transactions, and chain operations
  - Nodes: localhost, aitbc1, gitea-runner
  - Service: aitbc-blockchain-rpc.service, aitbc-blockchain-node.service
  - Wrapper: aitbc-blockchain-rpc-wrapper.py
  - Config: RPC_BIND_PORT environment variable (default: 8006)

- **7070**: P2P Mesh Network (aitbc_chain.p2p_network)
  - Purpose: Peer-to-peer gossip protocol for block propagation and node discovery
  - Nodes: localhost, aitbc1
  - Service: aitbc-blockchain-p2p.service
  - Wrapper: aitbc-blockchain-p2p-wrapper.py
  - Config: P2P_BIND_PORT environment variable (default: 7070)

- **8204**: Blockchain Event Bridge (blockchain_event_bridge.main)
  - Purpose: Event streaming service for blockchain events to external systems
  - Nodes: localhost, aitbc1
  - Service: aitbc-blockchain-event-bridge.service
  - Wrapper: aitbc-blockchain-event-bridge-wrapper.py
  - Config: bind_port environment variable (default: 8204)

### Coordinator Layer
- **8011**: Coordinator API (app.main)
  - Purpose: Main coordinator API for AI job submission, miner registration, marketplace operations
  - Nodes: localhost, aitbc1
  - Service: aitbc-coordinator-api.service
  - Wrapper: aitbc-coordinator-api-wrapper.py
  - Config: Hardcoded in wrapper (port 8011)

- **8012**: Adaptive Learning Service (app.services.adaptive_learning_app)
  - Purpose: AI model adaptive learning and optimization service
  - Nodes: localhost, aitbc1
  - Service: aitbc-learning.service
  - Config: Hardcoded in systemd (port 8012)
  - Note: Changed from 8011 to 8012 to avoid port conflict with coordinator API

- **9001**: Agent Coordinator
  - Purpose: Agent coordination, communication, and session management
  - Nodes: localhost
  - Service: aitbc-agent-coordinator.service
  - Config: AITBC_COORDINATOR_PORT environment variable (default: 9001)
  - Documentation: docs/agent-coordinator/ARCHITECTURE.md

### Exchange & Trading
- **8001**: Exchange API (simple_exchange_api.py)
  - Purpose: Cross-chain exchange and trading platform
  - Nodes: aitbc1
  - Service: aitbc-exchange-api.service
  - Wrapper: aitbc-exchange-api-wrapper.py
  - Config: Hardcoded in wrapper (port 8001)

### Wallet Services
- **8003**: Wallet Daemon (simple_daemon.py)
  - Purpose: Background wallet service for transaction signing and key management
  - Nodes: localhost, aitbc1
  - Service: aitbc-wallet.service
  - Wrapper: aitbc-wallet-wrapper.py
  - Config: Uses internal wallet RPC (no external port)

### AI Services
- **8005**: AI Service (src.ai_service.main)
  - Purpose: AI model inference and computation service
  - Nodes: localhost, aitbc1
  - Service: aitbc-ai.service
  - Config: Hardcoded in systemd (port 8005)

- **8020**: Multimodal Service (src.app.services.multimodal_app)
  - Purpose: Multimodal AI processing and integration
  - Nodes: aitbc1
  - Service: aitbc-multimodal.service
  - Config: Hardcoded in systemd (port 8020)

- **8021**: Modality Optimization Service (src.app.services.modality_optimization_app)
  - Purpose: AI modality optimization and tuning
  - Nodes: aitbc1
  - Service: aitbc-modality-optimization.service
  - Config: Hardcoded in systemd (port 8021)

### Agent Services
- **8014**: Hermes (aitbc-hermes-wrapper.py)
  - Purpose: AI agent communication and coordination framework
  - Nodes: localhost
  - Service: aitbc-hermes.service
  - Wrapper: aitbc-hermes-wrapper.py
  - Config: Hardcoded in wrapper (port 8014)

- **8016**: Plugin Registry (aitbc-plugin-wrapper.py)
  - Purpose: Agent plugin management and registry service
  - Nodes: aitbc1
  - Service: aitbc-plugin.service
  - Wrapper: aitbc-plugin-wrapper.py
  - Config: Hardcoded in wrapper (port 8016)

### Monitoring & Observability
- **8002**: Monitoring Service
  - Purpose: System monitoring, metrics collection, and health checks
  - Nodes: aitbc1
  - Service: aitbc-monitoring.service
  - Wrapper: aitbc-monitoring-wrapper.py
  - Config: Hardcoded in wrapper (port 8002)

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

### Known Conflicts & Resolutions
- **8011 vs 8012**: Coordinator API (8011) conflicted with Adaptive Learning Service (8011)
  - Resolution: Changed Adaptive Learning Service to port 8012 on all nodes
  - Files modified: /etc/systemd/system/aitbc-learning.service

### Port Allocation Guidelines
- **8000-8099**: Core AITBC services (blockchain, coordinator, exchange, wallet)
- **8100-8199**: AI and agent services (multimodal, optimization, plugins)
- **8200-8299**: Event streaming and bridge services
- **9000-9099**: Agent coordination and orchestration
- **7000-7099**: P2P and networking services

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
grep -r "port" /opt/aitbc/scripts/wrappers/*.py
```

### Test Service Endpoints
```bash
# Coordinator API health
curl http://localhost:8011/v1/health

# Blockchain RPC head
curl http://localhost:8006/rpc/head

# Exchange API
curl http://localhost:8001/v1/health

# Agent Coordinator
curl http://localhost:9001/v1/health
```

## Environment Variables

### Port Configuration Variables
- `RPC_BIND_PORT`: Blockchain RPC port (default: 8006)
- `P2P_BIND_PORT`: P2P network port (default: 7070)
- `AITBC_COORDINATOR_PORT`: Agent coordinator port (default: 9001)
- `bind_port`: Event bridge port (default: 8204)

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

## Node-Specific Service Distribution

### Localhost (aitbc - Genesis Node)
- Core: 8006, 7070, 8204, 8011, 8012
- AI: 8005, 8014, 9001
- Wallet: 8003
- Infrastructure: 80, 443, 5432, 6379, 11434

### aitbc1 (Follower Node)
- Core: 8006, 7070, 8204, 8011, 8012
- Exchange: 8001
- AI: 8005, 8020, 8021, 8016
- Monitoring: 8002
- Wallet: 8003
- Infrastructure: 5432, 6379

### gitea-runner (CI/CD Node)
- Infrastructure only: 5432, 6379, 22, 25
- No AITBC services running (CI execution environment)

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
