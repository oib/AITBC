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
1. Creates `AgentRegistry(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/1"))` with Redis backing
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

### Critical: Shared Redis Configuration

For cross-node task distribution to work, ALL coordinator instances MUST use the same shared Redis instance:

1. **Environment Configuration:** Set `REDIS_URL` in `/etc/aitbc/.env`:
   ```
   REDIS_URL=redis://10.1.223.93:6379/0
   ```

2. **Service Configuration:** The systemd service loads environment variables:
   ```
   EnvironmentFile=/etc/aitbc/.env
   ```

3. **Application Configuration:** The coordinator MUST read the environment variable in `lifespan.py`:
   ```python
   redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
   state.agent_registry = AgentRegistry(redis_url=redis_url)
   ```

4. **Verification:** Check if agents registered on one node appear on another:
   ```bash
   # Register on aitbc1
   curl -X POST http://aitbc1:9001/agents/register -d '{...}'
   
   # Discover on localhost
   curl -X POST http://localhost:9001/agents/discover -d '{}'
   
   # Should show the aitbc1 agent
   ```

### Example Cross-Node Setup
```bash
# Register agent on aitbc1
curl -X POST http://aitbc1:9001/agents/register \
  -d '{"agent_id":"aitbc1-agent", ...}'

# Submit task on localhost
curl -X POST http://localhost:9001/tasks/submit \
  -d '{"task_data":{...}}'

# Task will be distributed to any active agent across nodes
```

## Lessons Learned

### Redis Configuration Issues
- **Problem:** Coordinators default to `redis://localhost:6379/1` instead of reading environment variable
- **Solution:** Explicitly read `REDIS_URL` in `lifespan.py` and pass to `AgentRegistry`
- **Verification:** Check shared Redis keys: `redis-cli -h <host> KEYS 'agent:*'`

### Integration Test Patterns
- Use `httpx.AsyncClient` for async HTTP requests
- Use pytest fixtures for test setup/teardown
- Mark async test classes with `@pytest.mark.asyncio`
- Test both success and failure cases
- Verify actual Redis state for persistence tests

### Service Deployment
- Copy code changes to remote nodes before restarting
- Use `systemctl restart` to pick up code changes
- Check journalctl logs for startup errors
- Verify health endpoint after restart

### Cross-Node Setup
- Both coordinators must use same Redis instance
- Environment variables must be set correctly
- Service must be restarted to pick up code changes
- Test agent discovery across nodes before task distribution
