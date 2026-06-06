# Global AI Agents

## Status
✅ Operational

## Overview
Global AI agent coordination service for managing distributed AI agents across multiple regions and networks.

## Architecture

### Core Components
- **Agent Discovery**: Discovers AI agents across the global network
- **Coordination Engine**: Coordinates agent activities and decisions
- **Communication Bridge**: Bridges communication between regional agent clusters
- **Load Distributor**: Distributes AI workloads across regions
- **State Synchronizer**: Synchronizes agent state across regions

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Access to regional agent clusters
- Network connectivity between regions

### Installation
```bash
cd /opt/aitbc/apps/global-ai-agents
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
REGIONAL_CLUSTERS=us-east:https://us.example.com,eu-west:https://eu.example.com
COORDINATION_INTERVAL=30
STATE_SYNC_ENABLED=true
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure regional cluster endpoints
5. Run tests: `pytest tests/`

### Project Structure
```
global-ai-agents/
├── src/
│   ├── agent_discovery/      # Agent discovery
│   ├── coordination_engine/  # Coordination logic
│   ├── communication_bridge/ # Regional communication
│   ├── load_distributor/     # Workload distribution
│   └── state_synchronizer/   # State synchronization
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run coordination engine tests
pytest tests/test_coordination.py

# Run state synchronizer tests
pytest tests/test_sync.py
```

## API Reference

### Agent Discovery

#### Discover Agents
```http
POST /api/v1/global-ai/discover
Content-Type: application/json

{
  "region": "us-east",
  "agent_type": "string"
}
```

#### Get Agent Registry
```http
GET /api/v1/global-ai/agents?region=us-east
```

#### Register Agent
```http
POST /api/v1/global-ai/agents/register
Content-Type: application/json

{
  "agent_id": "string",
  "region": "us-east",
  "capabilities": ["string"]
}
```

### Coordination

#### Coordinate Task
```http
POST /api/v1/global-ai/coordinate
Content-Type: application/json

{
  "task_id": "string",
  "task_type": "string",
  "requirements": {},
  "regions": ["us-east", "eu-west"]
}
```

#### Get Coordination Status
```http
GET /api/v1/global-ai/coordination/{task_id}
```

### Communication

#### Send Message
```http
POST /api/v1/global-ai/communication/send
Content-Type: application/json

{
  "from_region": "us-east",
  "to_region": "eu-west",
  "message": {}
}
```

#### Get Communication Log
```http
GET /api/v1/global-ai/communication/log?limit=100
```

### Load Distribution

#### Distribute Workload
```http
POST /api/v1/global-ai/distribute
Content-Type: application/json

{
  "workload": {},
  "strategy": "round_robin|least_loaded"
}
```

#### Get Load Status
```http
GET /api/v1/global-ai/load/status
```

### State Synchronization

#### Sync State
```http
POST /api/v1/global-ai/sync/trigger
Content-Type: application/json

{
  "state_type": "string",
  "regions": ["us-east", "eu-west"]
}
```

#### Get Sync Status
```http
GET /api/v1/global-ai/sync/status
```

## Configuration

### Environment Variables
- `REGIONAL_CLUSTERS`: Comma-separated regional cluster endpoints
- `COORDINATION_INTERVAL`: Coordination check interval (default: 30s)
- `STATE_SYNC_ENABLED`: Enable state synchronization
- `MAX_LATENCY`: Maximum acceptable latency between regions

### Coordination Strategies
- **Round Robin**: Distribute tasks evenly across regions
- **Least Loaded**: Route to region with lowest load
- **Proximity**: Route to nearest region based on latency

### Synchronization Parameters
- **Sync Interval**: Frequency of state synchronization
- **Conflict Resolution**: Strategy for resolving state conflicts
- **Compression**: Enable state compression for transfers

## Troubleshooting

**Agent not discovered**: Check regional cluster connectivity and agent registration.

**Coordination failed**: Verify agent availability and task requirements.

**Communication bridge down**: Check network connectivity between regions.

**State sync delayed**: Review sync interval and network bandwidth.

## Security Notes

- Use TLS for all inter-region communication
- Implement authentication for regional clusters
- Encrypt state data during synchronization
- Monitor for unauthorized agent registration
- Implement rate limiting for coordination requests
- Regularly audit agent registry
