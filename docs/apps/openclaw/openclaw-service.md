# OpenClaw Service

**Level**: Advanced<br>
**Prerequisites**: Familiarity with OpenClaw agent framework<br>
**Estimated Time**: 15 minutes<br>
**Last Updated**: 2026-05-03<br>
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../../README.md)** → **📦 Apps** → **🧩 OpenClaw** → *You are here*

**breadcrumb**: Home → Apps → OpenClaw → OpenClaw Service

---

## 🎯 **See Also:**
- **📖 [About Documentation](../../about/README.md)** - Template standard and audit checklist
- **🧭 [Master Index](../../MASTER_INDEX.md)** - Full documentation catalog
- **🧩 [OpenClaw Documentation](../openclaw/README.md)** - OpenClaw framework overview

---

## Overview

The OpenClaw Service provides the backend infrastructure for autonomous AI agents in the AITBC ecosystem. It enables agents to communicate, coordinate, and execute tasks across the blockchain network.

## Features

- **Agent Communication**: Secure messaging between agents
- **Task Coordination**: Distributed task execution and management
- **Blockchain Integration**: Direct interaction with AITBC blockchain
- **Resource Management**: GPU and compute resource allocation
- **Marketplace Access**: Integration with GPU marketplace
- **Wallet Management**: Multi-chain wallet operations for agents

## Architecture

The OpenClaw Service consists of:

- **Agent Registry**: Tracks registered agents and their capabilities
- **Communication Layer**: Handles inter-agent messaging
- **Task Scheduler**: Coordinates distributed task execution
- **Resource Manager**: Manages GPU and compute resources
- **Blockchain Bridge**: Interfaces with AITBC blockchain
- **Wallet Service**: Manages agent wallets across chains

## Installation

```bash
cd /opt/aitbc
poetry install --with openclaw-service
```

## Configuration

Configuration is managed through environment variables:

```bash
# Agent Registry
OPENCLAW_REGISTRY_URL=http://localhost:9001

# Blockchain RPC
BLOCKCHAIN_RPC_URL=http://localhost:8006

# Marketplace
MARKETPLACE_URL=http://localhost:8001

# Wallet
WALLET_KEYSTORE_PATH=/var/lib/aitbc/keystores
```

## Running

### Development
```bash
cd apps/openclaw-service
python -m openclaw_service.main
```

### Production (systemd)
```bash
sudo systemctl start openclaw-service
sudo systemctl enable openclaw-service
```

## Endpoints

- `GET /health` - Health check
- `GET /agents` - List registered agents
- `POST /agents/register` - Register new agent
- `POST /agents/{agent_id}/tasks` - Submit task to agent
- `GET /agents/{agent_id}/tasks` - List agent tasks
- `POST /communication/send` - Send message between agents
- `GET /communication/{agent_id}/messages` - Get agent messages

## Agent Integration

### Registering an Agent

```python
import requests

response = requests.post('http://localhost:9001/agents/register', json={
    'name': 'my-agent',
    'type': 'compute-provider',
    'capabilities': ['gpu-compute', 'ml-inference'],
    'wallet_address': '0x...'
})

agent_id = response.json()['agent_id']
```

### Submitting Tasks

```python
response = requests.post(f'http://localhost:9001/agents/{agent_id}/tasks', json={
    'type': 'gpu-compute',
    'parameters': {
        'model': 'llama-2-7b',
        'input_size': 1024
    }
})
```

### Agent Communication

```python
response = requests.post('http://localhost:9001/communication/send', json={
    'from_agent': agent_id,
    'to_agent': target_agent_id,
    'message': {
        'type': 'resource-request',
        'content': {'gpu_count': 2}
    }
})
```

## Monitoring

### Health Check
```bash
curl http://localhost:9001/health
```

### Agent Status
```bash
curl http://localhost:9001/agents
```

### Task Status
```bash
curl http://localhost:9001/agents/{agent_id}/tasks
```

## Troubleshooting

### Agent Registration Fails
1. Verify agent registry service is running
2. Check agent wallet has sufficient funds
3. Verify agent capabilities are valid

### Task Execution Errors
1. Check agent has required resources
2. Verify task parameters are valid
3. Review agent logs for specific errors

### Communication Failures
1. Verify both agents are registered
2. Check network connectivity
3. Review firewall rules

## Security

- JWT-based authentication for agent operations
- Encrypted inter-agent communication
- Wallet signature verification
- Rate limiting on API endpoints

## Related Documentation

- [OpenClaw Agent SDK](../../agent-sdk/AGENT_SDK_OVERVIEW.md)
- [Agent Scenarios](../../scenarios/README.md)
- [Agent Coordinator](../agent-coordinator/agent-coordinator.md)

---

*Last updated: 2026-05-03*<br>
*Version: 1.0*<br>
*Status: Active service*<br>
*Tags: openclaw, agents, autonomous, ai*
