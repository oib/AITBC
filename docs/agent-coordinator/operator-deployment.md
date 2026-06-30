# Agent Coordinator - Deployment

**Last Updated**: 2026-06-30
**Version**: 1.0

> **Important:** This document describes the Agent Coordinator service. The Agent Coordinator service runs on port 9001. For the Coordinator API (job submission), use port 8203. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

## Prerequisites

- Redis server running on localhost or remote host
- Python 3.13+
- Systemd (for service management)
- AITBC blockchain node (optional, for blockchain integration)

## Installation

### 1. Install Dependencies

```bash
cd /opt/aitbc/apps/agent-coordinator
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Edit /etc/aitbc/.env
export AITBC_REDIS_URL=redis://localhost:6379
export AITBC_COORDINATOR_PORT=9001
export AITBC_LOG_LEVEL=INFO
```

### 3. Start Redis

```bash
systemctl start redis
systemctl enable redis
```

### 4. Start Coordinator Service

```bash
systemctl start aitbc-agent-coordinator.service
systemctl enable aitbc-agent-coordinator.service
```

## Service Configuration

**Service file location:** `/etc/systemd/system/aitbc-agent-coordinator.service`

**Key configuration parameters:**
- `PYTHONPATH=apps/agent-coordinator/src` - Python module path
- `uvicorn app.main:app` - FastAPI application entry point
- `--host 0.0.0.0` - Bind to all interfaces
- `--port 9001` - Service port

## Redis Configuration

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
> HGETALL agent:agent-agent
```

## Related Topics

- [Agent Registration](./operator-registration.md) - Manual and automated agent registration
- [Monitoring](./operator-monitoring.md) - Health checks, service status, and agent monitoring
- [Troubleshooting](./operator-troubleshooting.md) - Common issues and solutions
- [Performance Tuning](./operator-performance.md) - Load balancing and resource limits
- [Security](./operator-security.md) - Network security and authentication
- [Backup and Recovery](./operator-backup.md) - Redis backup and service configuration backup
- [Scaling](./operator-scaling.md) - Horizontal scaling and Redis clustering
- [Maintenance](./operator-maintenance.md) - Regular maintenance tasks and agent cleanup
- [Alerting](./operator-alerting.md) - Recommended alerts and monitoring tools
