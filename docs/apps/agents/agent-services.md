# Agent Services

## Status
✅ Operational

## Overview
Collection of agent-related services including agent bridge, compliance, protocols, registry, and trading capabilities.

## Architecture

### Components
- **Agent Bridge**: Bridge service for agent communication across networks
- **Agent Compliance**: Compliance checking and validation for agents
- **Agent Coordinator**: Coordination service for agent management
- **Agent Protocols**: Communication protocols for agent interaction
- **Agent Registry**: Central registry for agent registration and discovery
- **Agent Trading**: Trading capabilities for agent-based transactions

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Network connectivity for agent communication
- Valid agent credentials

### Installation
```bash
cd /opt/aitbc/apps/agent-services
# Install individual service dependencies
cd agent-bridge && pip install -r requirements.txt
cd agent-compliance && pip install -r requirements.txt
# ... repeat for other services
```

### Configuration
Each service has its own configuration file. Configure environment variables for each service:
```bash
# Agent Bridge
export AGENT_BRIDGE_ENDPOINT="http://localhost:8001"
export AGENT_BRIDGE_API_KEY="your-api-key"

# Agent Registry
export REGISTRY_DATABASE_URL="postgresql://user:pass@localhost/agent_registry"
```

### Running Services
```bash
# Start individual services
cd agent-bridge && python main.py
cd agent-compliance && python main.py
# ... repeat for other services
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Navigate to the specific service directory
3. Create virtual environment: `python -m venv .venv`
4. Install dependencies: `pip install -r requirements.txt`
5. Configure environment variables
6. Run tests: `pytest tests/`

### Project Structure
```
agent-services/
├── agent-bridge/          # Agent communication bridge
├── agent-compliance/      # Compliance checking service
├── agent-coordinator/     # Agent coordination (see coordinator/agent-coordinator.md)
├── agent-protocols/       # Communication protocols
├── agent-registry/        # Agent registration and discovery
└── agent-trading/         # Agent trading capabilities
```

### Testing
```bash
# Run tests for specific service
cd agent-bridge && pytest tests/

# Run all service tests
pytest agent-*/tests/
```

## API Reference

### Agent Bridge

#### Register Bridge
```http
POST /api/v1/bridge/register
Content-Type: application/json

{
  "agent_id": "string",
  "network": "string",
  "endpoint": "string"
}
```

#### Send Message
```http
POST /api/v1/bridge/send
Content-Type: application/json

{
  "from_agent": "string",
  "to_agent": "string",
  "message": {},
  "protocol": "string"
}
```

### Agent Registry

#### Register Agent
```http
POST /api/v1/registry/agents
Content-Type: application/json

{
  "agent_id": "string",
  "agent_type": "string",
  "capabilities": ["string"],
  "metadata": {}
}
```

#### Query Agents
```http
GET /api/v1/registry/agents?type=agent_type&capability=capability
```

### Agent Compliance

#### Check Compliance
```http
POST /api/v1/compliance/check
Content-Type: application/json

{
  "agent_id": "string",
  "action": "string",
  "context": {}
}
```

#### Get Compliance Report
```http
GET /api/v1/compliance/report/{agent_id}
```

### Agent Trading

#### Submit Trade
```http
POST /api/v1/trading/submit
Content-Type: application/json

{
  "agent_id": "string",
  "trade_type": "buy|sell",
  "asset": "string",
  "quantity": 100,
  "price": 1.0
}
```

#### Get Trade History
```http
GET /api/v1/trading/history/{agent_id}
```

## Configuration

### Agent Bridge
- `AGENT_BRIDGE_ENDPOINT`: Bridge service endpoint
- `AGENT_BRIDGE_API_KEY`: API key for authentication
- `BRIDGE_PROTOCOLS`: Supported communication protocols

### Agent Registry
- `REGISTRY_DATABASE_URL`: Database connection string
- `REGISTRY_CACHE_TTL`: Cache time-to-live
- `REGISTRY_SYNC_INTERVAL`: Sync interval for agent updates

### Agent Compliance
- `COMPLIANCE_RULES_PATH`: Path to compliance rules
- `COMPLIANCE_CHECK_INTERVAL`: Interval for compliance checks
- `COMPLIANCE_ALERT_THRESHOLD`: Threshold for compliance alerts

### Agent Trading
- `TRADING_FEE_PERCENTAGE`: Trading fee percentage
- `TRADING_MIN_ORDER_SIZE`: Minimum order size
- `TRADING_MAX_ORDER_SIZE`: Maximum order size

## Troubleshooting

**Bridge connection failed**: Check network connectivity and endpoint configuration.

**Agent not registered**: Verify agent registration with registry service.

**Compliance check failed**: Review compliance rules and agent configuration.

**Trade submission failed**: Check agent balance and trading parameters.

## Security Notes

- Use API keys for service authentication
- Encrypt agent communication channels
- Validate all agent actions through compliance service
- Monitor trading activities for suspicious patterns
- Regularly audit agent registry entries
