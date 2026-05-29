# AITBC Agent Coordinator - Operator Guide

**Last Updated:** 2026-05-28
**Version:** 1.0

> **Important:** This document describes the Agent Coordinator service. The Agent Coordinator service runs on port 9001. For the Coordinator API (job submission), use port 8011. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

This guide provides operators with the knowledge to deploy, configure, monitor, and troubleshoot the AITBC Agent Coordinator service.

## Service Deployment

### Prerequisites

- Redis server running on localhost or remote host
- Python 3.13+
- Systemd (for service management)
- AITBC blockchain node (optional, for blockchain integration)

### Installation

1. **Install dependencies:**
```bash
cd /opt/aitbc/apps/agent-coordinator
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
# Edit /etc/aitbc/.env
export AITBC_REDIS_URL=redis://localhost:6379
export AITBC_COORDINATOR_PORT=9001
export AITBC_LOG_LEVEL=INFO
```

3. **Start Redis:**
```bash
systemctl start redis
systemctl enable redis
```

4. **Start coordinator service:**
```bash
systemctl start aitbc-agent-coordinator.service
systemctl enable aitbc-agent-coordinator.service
```

### Service Configuration

**Service file location:** `/etc/systemd/system/aitbc-agent-coordinator.service`

**Key configuration parameters:**
- `PYTHONPATH=apps/agent-coordinator/src` - Python module path
- `uvicorn app.main:app` - FastAPI application entry point
- `--host 0.0.0.0` - Bind to all interfaces
- `--port 9001` - Service port

### Redis Configuration

**Connection URL:** `redis://localhost:6379/0`

**Redis data persistence:**
- Agent data: `agent:{agent_id}` (hash)
- Active agents: `agents:active` (set)
- Load metrics: Stored in agent hash

**Redis monitoring:**
```bash
redis-cli
> KEYS agent:*
> SMEMBERS agents:active
> HGETALL agent:hermes-agent
```

## Agent Registration Procedures

### Manual Registration via CLI

**Basic registration:**
```bash
aitbc-cli agent sdk register \
  --agent-id my-agent \
  --type worker \
  --coordinator-url http://localhost:9001
```

**Full registration with capabilities:**
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

### Automated Registration Script

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

### Cross-Node Registration

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

## Monitoring and Troubleshooting

### Health Checks

**Service health:**
```bash
curl http://localhost:9001/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-05-07T16:00:00.000000+00:00"
}
```

**Task distribution stats:**
```bash
curl http://localhost:9001/tasks/status
```

**CLI health check:**
```bash
aitbc-cli ai status
```

### Service Status

**Check systemd service:**
```bash
systemctl status aitbc-agent-coordinator.service
```

**View service logs:**
```bash
journalctl -u aitbc-agent-coordinator.service -f
```

**View recent logs:**
```bash
journalctl -u aitbc-agent-coordinator.service -n 100
```

### Agent Monitoring

**List all agents:**
```bash
aitbc-cli agent sdk list
```

**List active agents only:**
```bash
aitbc-cli agent sdk list --status active
```

**Check specific agent:**
```bash
aitbc-cli agent sdk status --agent-id my-agent
```

**Monitor distribution stats:**
```bash
aitbc-cli ai distribution-stats
```

### Redis Monitoring

**Check Redis connection:**
```bash
redis-cli ping
```

**View all registered agents:**
```bash
redis-cli
> KEYS agent:*
```

**View active agents:**
```bash
redis-cli
> SMEMBERS agents:active
```

**View agent details:**
```bash
redis-cli
> HGETALL agent:my-agent
```

**Monitor Redis memory:**
```bash
redis-cli INFO memory
```

### Common Issues and Solutions

#### Service won't start

**Symptoms:**
```
Failed to start aitbc-agent-coordinator.service
```

**Solutions:**
1. Check Redis is running:
```bash
systemctl status redis
```

2. Check Redis connection:
```bash
redis-cli ping
```

3. Check service logs:
```bash
journalctl -u aitbc-agent-coordinator.service -n 50
```

4. Verify PYTHONPATH:
```bash
echo $PYTHONPATH
# Should include: /opt/aitbc/apps/agent-coordinator/src
```

#### No agents discovered

**Symptoms:**
```bash
aitbc-cli agent sdk list
Found 0 agents
```

**Solutions:**
1. Check if agents are registered:
```bash
redis-cli SMEMBERS agents:active
```

2. Register an agent:
```bash
aitbc-cli agent sdk register --agent-id test-agent --type worker
```

3. Check agent status:
```bash
aitbc-cli agent sdk status --agent-id test-agent
```

#### Tasks not distributing

**Symptoms:**
- Tasks submitted but not assigned
- `tasks_distributed` count not increasing

**Solutions:**
1. Check for active agents:
```bash
aitbc-cli agent sdk list --status active
```

2. Check task distributor status:
```bash
curl http://localhost:9001/tasks/status
```

3. Verify agent capabilities match task requirements
4. Check load balancer strategy
5. Review service logs for errors

#### Agent marked as stale

**Symptoms:**
- Agent status changes from active to stale
- Agent not receiving new tasks

**Solutions:**
1. Update agent status:
```bash
aitbc-cli agent sdk update-status --agent-id my-agent --status active
```

2. Check heartbeat mechanism (if implemented)
3. Verify agent is still running
4. Check network connectivity

#### Redis connection errors

**Symptoms:**
```
Error connecting to Redis
```

**Solutions:**
1. Check Redis service:
```bash
systemctl status redis
```

2. Restart Redis:
```bash
systemctl restart redis
```

3. Check Redis configuration:
```bash
redis-cli INFO server
```

4. Verify Redis URL in environment:
```bash
echo $AITBC_REDIS_URL
```

## Performance Tuning

### Load Balancing Strategies

**Current default:** `LEAST_CONNECTIONS`

**Available strategies:**
- `LEAST_CONNECTIONS` - Fewest active connections
- `ROUND_ROBIN` - Circular distribution
- `WEIGHTED_ROUND_ROBIN` - Performance-based
- `RESOURCE_BASED` - CPU/memory metrics
- `GEOGRAPHIC` - Location-based
- `RANDOM` - Random selection (testing)

**Changing strategy:** (requires code modification in `lifespan.py`)

### Priority Queue Configuration

**Priority levels:**
1. urgent
2. critical
3. high
4. normal
5. low

**Queue sizing:** Configured in `TaskDistributor` class

**Monitoring queue sizes:**
```bash
curl http://localhost:9001/tasks/status | jq .stats.queue_sizes
```

### Resource Limits

**Redis memory limits:**
```bash
redis-cli CONFIG SET maxmemory 1gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**Service memory limits:** (configure in systemd service file)
```
MemoryLimit=2G
MemorySwap=2G
```

**Connection limits:** (configure in uvicorn startup)
```
--limit-concurrency 100
```

## Security Considerations

### Network Security

**Bind to specific interface:**
```bash
# In service file, change --host 0.0.0.0 to --host 127.0.0.1 for local only
--host 127.0.0.1
```

**Use firewall:**
```bash
# Allow only specific IPs
ufw allow from 192.168.1.0/24 to any port 9001
```

### Authentication

**Future implementation:** API key authentication and JWT tokens

**Current status:** No authentication (open access)

**Recommendation:** Deploy behind reverse proxy with authentication

### Data Encryption

**Redis encryption:** Configure Redis with TLS
**API encryption:** Use HTTPS in production

## Backup and Recovery

### Redis Backup

**Manual backup:**
```bash
redis-cli SAVE
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d).rdb
```

**Automated backup:**
```bash
#!/bin/bash
# backup_redis.sh
redis-cli BGSAVE
sleep 5
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d-%H%M%S).rdb
# Keep last 7 days
find /backup -name "redis-*.rdb" -mtime +7 -delete
```

**Restore from backup:**
```bash
systemctl stop redis
cp /backup/redis-20260507.rdb /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb
systemctl start redis
```

### Service Configuration Backup

**Backup service file:**
```bash
cp /etc/systemd/system/aitbc-agent-coordinator.service /backup/
```

**Backup environment:**
```bash
cp /etc/aitbc/.env /backup/
```

## Scaling

### Horizontal Scaling

**Multiple coordinator instances:**
1. Deploy multiple coordinator instances behind load balancer
2. Use shared Redis instance
3. Configure consistent PYTHONPATH across instances

**Load balancer configuration:**
```nginx
upstream coordinator {
    server localhost:9001;
    server localhost:9002;
    server localhost:9003;
}

server {
    listen 80;
    location / {
        proxy_pass http://coordinator;
    }
}
```

### Redis Clustering

**For high availability:**
- Use Redis Sentinel for failover
- Use Redis Cluster for sharding
- Configure coordinator to use Redis Sentinel

## Maintenance

### Regular Maintenance Tasks

**Daily:**
- Monitor service health
- Check task distribution stats
- Review error logs

**Weekly:**
- Backup Redis data
- Review agent registrations
- Clean up stale agents

**Monthly:**
- Review performance metrics
- Update software dependencies
- Audit security configurations

### Agent Cleanup

**Remove inactive agents:**
```bash
redis-cli
> SREM agents:active "stale-agent-id"
> DEL agent:stale-agent-id
```

**Bulk cleanup script:**
```bash
#!/bin/bash
# cleanup_stale_agents.sh
redis-cli --scan --pattern "agent:*" | while read key; do
  status=$(redis-cli HGET "$key" status)
  if [ "$status" = "stale" ]; then
    agent_id=$(echo "$key" | cut -d: -f2)
    redis-cli SREM agents:active "$agent_id"
    redis-cli DEL "$key"
    echo "Removed stale agent: $agent_id"
  fi
done
```

### Service Restart

**Graceful restart:**
```bash
systemctl reload aitbc-agent-coordinator.service
```

**Force restart:**
```bash
systemctl restart aitbc-agent-coordinator.service
```

**Rolling restart (multiple instances):**
```bash
for i in {1..3}; do
  systemctl restart aitbc-agent-coordinator@$i.service
  sleep 10
done
```

## Alerting

### Recommended Alerts

**Service alerts:**
- Service down (health check fails)
- High error rate (> 5%)
- High response time (> 5s)

**Agent alerts:**
- No active agents
- Agent registration failures
- Agent stale count increasing

**Task alerts:**
- Task queue backlog (> 100 tasks)
- Task failure rate (> 10%)
- Distribution time increasing

**Redis alerts:**
- Redis connection failures
- Redis memory usage > 80%
- Redis latency > 100ms

### Monitoring Tools

**Prometheus metrics:** (future implementation)
- Export metrics at `/metrics` endpoint
- Use Grafana for visualization

**Log aggregation:**
- Send logs to ELK stack
- Use Loki for log storage
- Configure alerting based on log patterns

## Troubleshooting Checklist

When issues occur, check in this order:

1. **Service status**
   - [ ] Service running?
   - [ ] Health check passing?
   - [ ] Logs showing errors?

2. **Redis status**
   - [ ] Redis running?
   - [ ] Connection successful?
   - [ ] Memory usage normal?

3. **Agent status**
   - [ ] Agents registered?
   - [ ] Agents active?
   - [ ] Agent capabilities valid?

4. **Task status**
   - [ ] Tasks submitting?
   - [ ] Tasks distributing?
   - [ ] Tasks completing?

5. **Network**
   - [ ] Connectivity to Redis?
   - [ ] Connectivity to agents?
   - [ ] Firewall rules correct?

6. **Configuration**
   - [ ] Environment variables set?
   - [ ] PYTHONPATH correct?
   - [ ] Port available?
