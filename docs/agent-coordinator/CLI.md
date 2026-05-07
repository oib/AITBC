# AITBC Agent Coordinator - CLI Reference

The AITBC CLI provides commands for interacting with the Agent Coordinator service for agent management and task distribution.

## Agent SDK Commands

### Register Agent

Register a new agent with the coordinator service.

**Command:**
```bash
aitbc-cli agent sdk register --agent-id <ID> [OPTIONS]
```

**Required Arguments:**
- `--agent-id`: Unique identifier for the agent

**Optional Arguments:**
- `--type`: Agent type (provider, consumer, general, worker) - default: worker
- `--capabilities`: Comma-separated list of agent capabilities
- `--services`: Comma-separated list of available services
- `--endpoints`: JSON string of service endpoints
- `--metadata`: JSON string of metadata
- `--coordinator-url`: Coordinator URL - default: http://localhost:9001

**Examples:**
```bash
# Basic registration
aitbc-cli agent sdk register --agent-id hermes-agent --type worker

# Full registration with all parameters
aitbc-cli agent sdk register \
  --agent-id hermes-agent \
  --type worker \
  --capabilities "data-processing,analysis,debugging" \
  --services "task-execution,coordination" \
  --endpoints '{"http":"http://localhost:9002"}' \
  --metadata '{"version":"1.0.0","owner":"aitbc"}'
```

**Output:**
```
Registering agent hermes-agent with coordinator at http://localhost:9001...
Agent registered successfully
Registration:
  Status: success
  Message: Agent hermes-agent registered successfully
  Agent Id: hermes-agent
  Registered At: 2026-05-07T16:26:55.464178+00:00
```

### List Agents

Discover and list agents from the coordinator.

**Command:**
```bash
aitbc-cli agent sdk list [OPTIONS]
```

**Optional Arguments:**
- `--status`: Filter by agent status (active, inactive, busy, stale)
- `--agent-type`: Filter by agent type
- `--coordinator-url`: Coordinator URL - default: http://localhost:9001

**Examples:**
```bash
# List all agents
aitbc-cli agent sdk list

# List only active agents
aitbc-cli agent sdk list --status active

# List worker type agents
aitbc-cli agent sdk list --agent-type worker
```

**Output:**
```
Discovering agents from coordinator at http://localhost:9001...
Found 2 agents
Agents:
  Status: success
  Query: {}
  Agents:
    - Agent details...
  Count: 2
  Timestamp: 2026-05-07T16:39:34.254450+00:00
```

### Get Agent Status

Retrieve detailed information about a specific agent.

**Command:**
```bash
aitbc-cli agent sdk status --agent-id <ID> [OPTIONS]
```

**Required Arguments:**
- `--agent-id`: Unique identifier of the agent

**Optional Arguments:**
- `--coordinator-url`: Coordinator URL - default: http://localhost:9001

**Examples:**
```bash
aitbc-cli agent sdk status --agent-id hermes-agent
```

**Output:**
```
Getting agent info for hermes-agent from coordinator at http://localhost:9001...
Agent info retrieved
Agent:
  Status: success
  Agent: Agent details...
  Timestamp: 2026-05-07T16:39:42.744729+00:00
```

### Update Agent Status

Update the status and load metrics of an agent.

**Command:**
```bash
aitbc-cli agent sdk update-status --agent-id <ID> --status <STATUS> [OPTIONS]
```

**Required Arguments:**
- `--agent-id`: Unique identifier of the agent
- `--status`: New status (active, inactive, busy, stale)

**Optional Arguments:**
- `--load-metrics`: JSON string of load metrics
- `--coordinator-url`: Coordinator URL - default: http://localhost:9001

**Examples:**
```bash
# Mark agent as busy
aitbc-cli agent sdk update-status --agent-id hermes-agent --status busy

# Update status with load metrics
aitbc-cli agent sdk update-status \
  --agent-id hermes-agent \
  --status busy \
  --load-metrics '{"active_connections":5,"pending_tasks":2}'
```

**Output:**
```
Updating agent hermes-agent status to busy...
Agent status updated successfully
Status Update:
  Status: success
  Message: Agent hermes-agent status updated
  Agent Id: hermes-agent
  New Status: busy
  Updated At: 2026-05-07T16:40:03.536877+00:00
```

## AI Commands

### Submit AI Job

Submit an AI job to the coordinator for distribution.

**Command:**
```bash
aitbc-cli ai submit --wallet <WALLET> --type <TYPE> --prompt <PROMPT> [OPTIONS]
```

**Required Arguments:**
- `--wallet`: Wallet name for the transaction
- `--type`: Job type or model name
- `--prompt`: Prompt for the AI job

**Optional Arguments:**
- `--payment`: Payment amount
- `--password`: Wallet password
- `--password-file`: Path to password file
- `--chain-id`: Chain ID
- `--rpc-url`: RPC URL
- `--coordinator-url`: Coordinator URL - default: http://localhost:9001

**Examples:**
```bash
aitbc-cli ai submit \
  --wallet openclaw-trainee \
  --type llama2 \
  --prompt "Explain quantum computing"
```

**Output:**
```
Submitting AI job to http://localhost:9001...
AI job submitted successfully
Job: Job details...
```

### Get Task Distribution Statistics

Get task distribution statistics from the agent coordinator.

**Command:**
```bash
aitbc-cli ai distribution-stats [OPTIONS]
```

**Optional Arguments:**
- `--coordinator-url`: Coordinator URL - default: http://localhost:9001

**Examples:**
```bash
aitbc-cli ai distribution-stats
```

**Output:**
```
Getting task distribution statistics from http://localhost:9001...
Task distribution statistics:
  Status: success
  Stats:
    tasks_distributed: 1
    tasks_completed: 1
    tasks_failed: 0
    load_balancer_stats:
      strategy: least_connections
      active_agents: 1
      total_assignments: 1
      ...
  Timestamp: 2026-05-07T16:38:40.722733+00:00
```

### AI Service Status

Check the status of AI services (agent coordinator + blockchain AI).

**Command:**
```bash
aitbc-cli ai status [OPTIONS]
```

**Optional Arguments:**
- `--coordinator-url`: Coordinator URL
- `--rpc-url`: RPC URL
- `--chain-id`: Chain ID

**Examples:**
```bash
aitbc-cli ai status
```

**Output:**
```
Checking Agent Coordinator at http://localhost:9001...
  Agent Coordinator: healthy (v1.0.0)
Checking Blockchain AI stats at http://localhost:8006...
  Blockchain AI Stats: Available

Overall Status: operational
  Agent Coordinator: Operational
  Blockchain AI: Operational
```

## Common Options

### Output Format

All CLI commands support different output formats:

```bash
aitbc-cli --output json agent sdk list
aitbc-cli --output yaml agent sdk status --agent-id hermes-agent
aitbc-cli --output table ai distribution-stats
```

### Verbose Mode

Enable verbose output for debugging:

```bash
aitbc-cli --verbose agent sdk register --agent-id test-agent
```

### Debug Mode

Enable debug mode for detailed troubleshooting:

```bash
aitbc-cli --debug agent sdk list
```

## Workflows

### Register and Verify Agent

```bash
# Register agent
aitbc-cli agent sdk register \
  --agent-id my-agent \
  --type worker \
  --capabilities "data-processing,analysis"

# Verify registration
aitbc-cli agent sdk status --agent-id my-agent

# Check if agent appears in discovery
aitbc-cli agent sdk list --status active
```

### Submit and Monitor Task

```bash
# Submit task
aitbc-cli ai submit \
  --wallet openclaw-trainee \
  --type llama2 \
  --prompt "test prompt"

# Check distribution stats
aitbc-cli ai distribution-stats

# Monitor active agents
aitbc-cli agent sdk list --status active
```

### Update Agent Load

```bash
# Mark agent as busy
aitbc-cli agent sdk update-status \
  --agent-id my-agent \
  --status busy \
  --load-metrics '{"active_connections":10,"pending_tasks":5}'

# Mark agent as available again
aitbc-cli agent sdk update-status \
  --agent-id my-agent \
  --status active \
  --load-metrics '{"active_connections":0,"pending_tasks":0}'
```

## Error Handling

### Common Errors

**Agent not found:**
```
Agent not found: my-agent
```
Solution: Verify the agent ID is correct and the agent is registered.

**Coordinator unavailable:**
```
Error registering agent: Connection refused
```
Solution: Check that the coordinator service is running on port 9001.

**Invalid parameters:**
```
Error: --agent-id and --status are required
```
Solution: Provide all required arguments.

### Troubleshooting

**Check service status:**
```bash
systemctl status aitbc-agent-coordinator.service
```

**View service logs:**
```bash
journalctl -u aitbc-agent-coordinator.service -f
```

**Test coordinator health:**
```bash
curl http://localhost:9001/health
```

**Test coordinator API directly:**
```bash
curl http://localhost:9001/tasks/status
```

## Environment Variables

The CLI respects the following environment variables:

- `AITBC_COORDINATOR_URL`: Default coordinator URL
- `AITBC_RPC_URL`: Default RPC URL
- `AITBC_CHAIN_ID`: Default chain ID

Example:
```bash
export AITBC_COORDINATOR_URL=http://localhost:9001
aitbc-cli agent sdk list
```

## Configuration

The CLI configuration is stored in:
- `~/.aitbc/config.json` - User-specific configuration
- `/etc/aitbc/config.json` - System-wide configuration

Configuration file format:
```json
{
  "coordinator_url": "http://localhost:9001",
  "rpc_url": "http://localhost:8006",
  "chain_id": "ait-mainnet",
  "default_wallet": "openclaw-trainee"
}
```

## Integration with Other CLI Commands

The agent coordinator CLI integrates with other AITBC CLI commands:

- `aitbc-cli wallet` - For wallet management
- `aitbc-cli blockchain` - For blockchain operations
- `aitbc-cli ai` - For AI job submission and monitoring
- `aitbc-cli system` - For system status and operations

## Advanced Usage

### Batch Agent Registration

```bash
#!/bin/bash
# Register multiple agents
for i in {1..5}; do
  aitbc-cli agent sdk register \
    --agent-id "agent-$i" \
    --type worker \
    --capabilities "data-processing"
done
```

### Monitoring Script

```bash
#!/bin/bash
# Monitor agent coordinator
while true; do
  clear
  echo "=== Agent Coordinator Status ==="
  aitbc-cli ai distribution-stats
  echo ""
  echo "=== Active Agents ==="
  aitbc-cli agent sdk list --status active
  sleep 5
done
```

### Load Testing

```bash
#!/bin/bash
# Submit multiple tasks
for i in {1..10}; do
  aitbc-cli ai submit \
    --wallet openclaw-trainee \
    --type llama2 \
    --prompt "Test task $i" &
done
wait
```
