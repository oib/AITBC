# Agent Coordinator - Agent Registration

**Last Updated**: 2026-06-30
**Version**: 1.0

## Manual Registration via CLI

### Basic Registration

```bash
# 1. Create the local agent definition
aitbc agent create --name my-agent --type worker

# 2. Register it with the coordinator
aitbc agent register \
  --agent-id my-agent \
  --coordinator-url http://localhost:8107
```

### Full Registration with Capabilities

```bash
# Capabilities are declared at creation time, then the agent is registered
aitbc agent create \
  --name my-agent \
  --type worker \
  --models "data-processing,analysis,debugging" \
  --specialization task-execution

aitbc agent register \
  --agent-id my-agent \
  --coordinator-url http://localhost:8107
```

## Automated Registration Script

```bash
#!/bin/bash
# register_agents.sh

COORDINATOR_URL="http://localhost:8107"

register_agent() {
  local agent_id=$1
  local agent_type=$2
  local capabilities=$3

  aitbc agent create --name "$agent_id" --type "$agent_type" --models "$capabilities"

  aitbc agent register \
    --agent-id "$agent_id" \
    --coordinator-url "$COORDINATOR_URL"
}

# Register agents
register_agent "worker-1" "worker" "data-processing,analysis"
register_agent "worker-2" "worker" "data-processing,analysis"
register_agent "worker-3" "worker" "inference,training"
```

## Cross-Node Registration

Register agents on multiple nodes for distributed task distribution:

```bash
# Register agent on node1
curl -X POST http://node1:8107/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "node1-worker",
    "agent_type": "worker",
    "capabilities": ["data-processing"],
    "endpoints": {"http": "http://node1:9002"}
  }'

# Register agent on node2
curl -X POST http://node2:8107/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "node2-worker",
    "agent_type": "worker",
    "capabilities": ["inference"],
    "endpoints": {"http": "http://node2:9002"}
  }'
```

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Monitoring](./operator-monitoring.md) - Health checks and agent monitoring
- [Troubleshooting](./operator-troubleshooting.md) - Common issues and solutions
