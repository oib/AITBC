# Agent Coordinator - Agent Registration

**Last Updated**: 2026-06-30
**Version**: 1.0

## Manual Registration via CLI

### Basic Registration

```bash
aitbc-cli agent sdk register \
  --agent-id my-agent \
  --type worker \
  --coordinator-url http://localhost:9001
```

### Full Registration with Capabilities

```bash
aitbc-cli agent sdk register \
  --agent-id my-agent \
  --type worker \
  --capabilities "data-processing,analysis,debugging" \
  --services "task-execution,coordination" \
  --endpoints '{"http":"http://my-host:9002"}' \
  --metadata '{"version":"1.0.0","owner":"my-team"}' \
  --coordinator-url http://localhost:9001
```

## Automated Registration Script

```bash
#!/bin/bash
# register_agents.sh

COORDINATOR_URL="http://localhost:9001"

register_agent() {
  local agent_id=$1
  local agent_type=$2
  local capabilities=$3

  aitbc-cli agent sdk register \
    --agent-id "$agent_id" \
    --type "$agent_type" \
    --capabilities "$capabilities" \
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
curl -X POST http://node1:9001/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "node1-worker",
    "agent_type": "worker",
    "capabilities": ["data-processing"],
    "endpoints": {"http": "http://node1:9002"}
  }'

# Register agent on node2
curl -X POST http://node2:9001/agents/register \
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
