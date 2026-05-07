# AITBC Training - Agent Coordinator Architecture

## Important: Real Coordinator Location

The actual AITBC Agent Coordinator service is located at:
- **Path:** `/opt/aitbc/apps/agent-coordinator/src/app/`
- **Port:** 9001
- **Service:** `aitbc-agent-coordinator.service`

## DO NOT Use

- **Wrong location:** `/opt/aitbc/apps/agent-services/agent-coordinator/src/coordinator.py`
- This is a different/older implementation and is NOT the active service

## Key Components

### Core Files
- `agent_discovery.py` - Redis-backed agent registry with persistence
- `load_balancer.py` - Load balancer with multiple strategies (least_connections, round_robin, etc.)
- `routers/agents.py` - Agent management REST API endpoints
- `routers/tasks.py` - Task submission and distribution API endpoints
- `lifespan.py` - Service initialization and component startup
- `state.py` - Global state management for coordinator components

### Service Initialization
The service initializes in `lifespan.py`:
1. Creates `AgentRegistry()` with Redis backing
2. Starts registry Redis connection
3. Creates `LoadBalancer(registry)` with least_connections strategy
4. Creates `TaskDistributor(balancer)` with priority queues
5. Starts background task distribution loop

## Agent Registration

### API Endpoint
```
POST /agents/register
```

### Example
```bash
curl -X POST http://localhost:9001/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "hermes-agent",
    "agent_type": "worker",
    "capabilities": ["data-processing", "analysis", "general"],
    "services": ["task-execution", "analysis"],
    "endpoints": {"http": "http://localhost:9002"},
    "metadata": {"version": "1.0.0"}
  }'
```

### Response
```json
{
  "status": "success",
  "message": "Agent hermes-agent registered successfully",
  "agent_id": "hermes-agent",
  "registered_at": "2026-05-07T16:26:55.464178+00:00"
}
```

## Task Distribution

### API Endpoint
```
POST /tasks/submit
```

### Example
```bash
curl -X POST http://localhost:9001/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "task_data": {
      "model": "llama2",
      "prompt": "test prompt"
    },
    "priority": "normal",
    "requirements": {}
  }'
```

### Distribution Flow
1. Task submitted to `TaskDistributor`
2. Distributor finds eligible agents via `AgentRegistry.discover_agents()`
3. Load balancer selects agent using configured strategy (default: least_connections)
4. Task assigned to selected agent
5. Agent metrics updated in Redis

## Task Status

### API Endpoint
```
GET /tasks/status
```

### Example
```bash
curl http://localhost:9001/tasks/status
```

### Response
```json
{
  "status": "success",
  "stats": {
    "tasks_distributed": 1,
    "tasks_completed": 1,
    "tasks_failed": 0,
    "load_balancer_stats": {
      "strategy": "least_connections",
      "active_agents": 1,
      "total_assignments": 1,
      "avg_agent_load": 1
    }
  }
}
```

## Agent Discovery

### API Endpoint
```
POST /agents/discover
```

### Example
```bash
curl -X POST http://localhost:9001/agents/discover \
  -H "Content-Type: application/json" \
  -d '{
    "status": "active",
    "agent_type": "worker"
  }'
```

## Redis Persistence

The agent registry uses Redis for persistence:
- Agent data stored as hashes: `agent:{agent_id}`
- Active agents indexed in set: `agents:active`
- Load metrics tracked per agent
- Health scores calculated from heartbeats

## Service Status

### Health Check
```bash
curl http://localhost:9001/health
```

### Service Management
```bash
systemctl status aitbc-agent-coordinator.service
systemctl restart aitbc-agent-coordinator.service
journalctl -u aitbc-agent-coordinator.service -f
```

## Cross-Node Distribution

For multi-node setups, register agents on each node:
```bash
# Register agent on aitbc1
curl -X POST http://aitbc1:9001/agents/register \
  -d '{"agent_id":"aitbc1-agent", ...}'

# Submit task on localhost
curl -X POST http://localhost:9001/tasks/submit \
  -d '{"task_data":{...}}'

# Task will be distributed to any active agent across nodes
```
