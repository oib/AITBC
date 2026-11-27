# SLA Monitoring Guide

**Last Updated:** 2026-05-28

This guide covers SLA (Service Level Agreement) monitoring for coordinator/pool hub services in the AITBC ecosystem.

## Overview

The SLA monitoring system provides:

- Real-time tracking of miner performance metrics
- Automated SLA violation detection and alerting
- Capacity planning with forecasting and scaling recommendations
- Comprehensive API endpoints for monitoring and management

## Architecture

```
┌─────────────────┐
│   Pool-Hub      │
│                 │
│  SLA Collector  │──────┐
│  Capacity       │      │
│  Planner        │      │
│                 │      │
└────────┬────────┘      │
         │               │
         │ HTTP API      │
         │               │
┌────────▼────────┐     │
│ Coordinator-API  │◀────┘
│                 │
│ Multi-tenant DB │
└─────────────────┘
```

## SLA Metrics

### Miner Uptime

- **Definition**: Percentage of time a miner is available and responsive
- **Calculation**: Based on heartbeat intervals (5-minute threshold)
- **Threshold**: 95%
- **Alert Levels**:
  - Critical: <85.5% (threshold * 0.9)
  - High: <95% (threshold)

### Response Time

- **Definition**: Average time for miner to respond to match requests
- **Calculation**: Average of `eta_ms` from match results (last 100 results)
- **Threshold**: 1000ms (P95)
- **Alert Levels**:
  - Critical: >2000ms (threshold * 2)
  - High: >1000ms (threshold)

### Job Completion Rate

- **Definition**: Percentage of jobs completed successfully
- **Calculation**: Successful outcomes / total outcomes (last 7 days)
- **Threshold**: 90%
- **Alert Levels**:
  - Critical: <90% (threshold)

### Capacity Availability

- **Definition**: Percentage of miners available (not busy)
- **Calculation**: Active miners / Total miners
- **Threshold**: 80%
- **Alert Levels**:
  - High: <80% (threshold)

## Configuration

### Environment Variables

Add to pool-hub `.env`:

```bash
# Pool-hub settings use the POOLHUB_ env prefix (poolhub/settings.py,
# env_prefix="poolhub_").

# The SLA scheduler defaults OFF.
POOLHUB_ENABLE_SLA_COLLECTION=false

# Coordinator API (registry lookups)
POOLHUB_COORDINATOR_BILLING_URL=http://localhost:8203

# SLA thresholds are configured via POOLHUB_SLA_THRESHOLDS (JSON dict), e.g.
# POOLHUB_SLA_THRESHOLDS='{"uptime":95.0,"response_time":1000.0,
#   "completion_rate":90.0,"capacity":80.0}'

# Capacity Planning
POOLHUB_CAPACITY_FORECAST_HOURS=168

# SLA Collection
POOLHUB_SLA_COLLECTION_INTERVAL_SECONDS=300
```

### Settings File

Configuration can also be set in `poolhub/settings.py`:

```python
class Settings(BaseSettings):
    # Coordinator API (registry lookups)
    coordinator_billing_url: str = Field(default="http://localhost:8203")

    # SLA Configuration
    sla_thresholds: Dict[str, float] = Field(
        default_factory=lambda: {
            "uptime_pct": 95.0,
            "response_time_ms": 1000.0,
            "completion_rate_pct": 90.0,
            "capacity_availability_pct": 80.0,
        }
    )

    # Capacity Planning Configuration
    capacity_forecast_hours: int = Field(default=168)
    capacity_alert_threshold_pct: float = Field(default=80.0)

    # SLA Collection Configuration
    sla_collection_interval_seconds: int = Field(default=300)

    # Whether the app starts the scheduler that interval configures
    enable_sla_collection: bool = Field(default=False)
```

## Database Schema

### SLA Metrics Table

```sql
CREATE TABLE sla_metrics (
    id UUID PRIMARY KEY,
    miner_id VARCHAR(64) NOT NULL REFERENCES miners(miner_id) ON DELETE CASCADE,
    metric_type VARCHAR(32) NOT NULL,
    metric_value FLOAT NOT NULL,
    threshold FLOAT NOT NULL,
    is_violation BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_sla_metrics_miner_id ON sla_metrics(miner_id);
CREATE INDEX ix_sla_metrics_timestamp ON sla_metrics(timestamp);
CREATE INDEX ix_sla_metrics_metric_type ON sla_metrics(metric_type);
```

### SLA Violations Table

```sql
CREATE TABLE sla_violations (
    id UUID PRIMARY KEY,
    miner_id VARCHAR(64) NOT NULL REFERENCES miners(miner_id) ON DELETE CASCADE,
    violation_type VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    metric_value FLOAT NOT NULL,
    threshold FLOAT NOT NULL,
    violation_duration_ms INTEGER,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_sla_violations_miner_id ON sla_violations(miner_id);
CREATE INDEX ix_sla_violations_created_at ON sla_violations(created_at);
CREATE INDEX ix_sla_violations_severity ON sla_violations(severity);
```

### Capacity Snapshots Table

```sql
CREATE TABLE capacity_snapshots (
    id UUID PRIMARY KEY,
    total_miners INTEGER NOT NULL,
    active_miners INTEGER NOT NULL,
    total_parallel_capacity INTEGER NOT NULL,
    total_queue_length INTEGER NOT NULL,
    capacity_utilization_pct FLOAT NOT NULL,
    forecast_capacity INTEGER NOT NULL,
    recommended_scaling VARCHAR(32) NOT NULL,
    scaling_reason TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_capacity_snapshots_timestamp ON capacity_snapshots(timestamp);
```

## Database Migration

Run the migration to add SLA and capacity tables:

```bash
cd apps/pool-hub
alembic upgrade head
```

## API Endpoints

### SLA Metrics Endpoints

#### Get SLA Metrics for a Miner

```bash
GET /v1/sla/metrics/{miner_id}?hours=24
```

Response:

```json
[
  {
    "id": "uuid",
    "miner_id": "miner_001",
    "metric_type": "uptime_pct",
    "metric_value": 98.5,
    "threshold": 95.0,
    "is_violation": false,
    "timestamp": "2026-04-22T15:00:00Z",
    "metadata": {}
  }
]
```

#### Get All SLA Metrics

```bash
GET /v1/sla/metrics?hours=24
```

#### Get SLA Violations

```bash
GET /v1/sla/violations?resolved=false&miner_id=miner_001
```

#### Trigger SLA Metrics Collection

```bash
POST /v1/sla/metrics/collect
```

Response:

```json
{
  "miners_processed": 10,
  "metrics_collected": [...],
  "violations_detected": 2,
  "capacity": {
    "total_miners": 10,
    "active_miners": 8,
    "capacity_availability_pct": 80.0
  }
}
```

### Capacity Planning Endpoints

#### Get Capacity Snapshots

```bash
GET /v1/sla/capacity/snapshots?hours=24
```

#### Get Capacity Forecast

```bash
GET /v1/sla/capacity/forecast?hours_ahead=168
```

Response:

```json
{
  "forecast_horizon_hours": 168,
  "current_capacity": 1000,
  "projected_capacity": 1500,
  "recommended_scaling": "+50%",
  "confidence": 0.85,
  "source": "coordinator_api"
}
```

#### Get Scaling Recommendations

```bash
GET /v1/sla/capacity/recommendations
```

Response:

```json
{
  "current_state": "healthy",
  "recommendations": [
    {
      "action": "add_miners",
      "quantity": 2,
      "reason": "Projected capacity shortage in 2 weeks",
      "priority": "medium"
    }
  ],
  "source": "coordinator_api"
}
```

#### Configure Capacity Alerts

```bash
POST /v1/sla/capacity/alerts/configure
```

Request:

```json
{
  "threshold_pct": 80.0,
  "notification_email": "admin@example.com"
}
```

### Status Endpoint

#### Get SLA Status

```bash
GET /v1/sla/status
```

Response:

```json
{
  "status": "healthy",
  "active_violations": 0,
  "recent_metrics_count": 50,
  "timestamp": "2026-04-22T15:00:00Z"
}
```

## Automated Collection

The scheduler is started by the pool-hub app itself, from the lifespan in
`poolhub/app/main.py`, behind a flag that **defaults to off**:

| Environment variable | Default | Starts | Interval setting |
|---|---|---|---|
| `POOLHUB_ENABLE_SLA_COLLECTION` | `false` | `SLACollectorScheduler` | `POOLHUB_SLA_COLLECTION_INTERVAL_SECONDS` (300) |

With the flag off — the shipped default — SLA metrics are collected only when
something calls `POST /v1/sla/metrics/collect`.

> **Removed in #3077:** the billing-sync scheduler
> (`POOLHUB_ENABLE_BILLING_SYNC`) and the `/v1/sla/billing/*` endpoints are
> gone. They POSTed usage to `/api/billing/*` routes coordinator-api does
> not serve, so every event went nowhere while looking like a billing
> record. If usage billing is ever implemented, it needs a real
> coordinator-api route first.

### Constructing a scheduler directly

It takes a session **factory**, not a session — a loop that runs for the life
of the process opens a session per pass instead of holding one, and its pooled
connection, open indefinitely:

```python
from poolhub.database import get_session_factory
from poolhub.services.sla_collector import SLACollectorScheduler

sla = SLACollectorScheduler(get_session_factory())
await sla.start(collection_interval_seconds=300)   # every 5 minutes

# stop() cancels the loop task and awaits its exit, so shutdown does not leave
# a task parked in a sleep of up to a full interval.
await sla.stop()
```

## Monitoring and Alerting

### Prometheus Metrics

Pool-hub exposes Prometheus metrics with the namespace `poolhub`, but only
the match/matcher series are implemented (`poolhub_match_requests_total`,
`poolhub_match_candidates_total`, `poolhub_match_failures_total`,
`poolhub_match_latency_seconds`, `poolhub_miners_online` — see
`poolhub/app/prometheus.py`). **The `poolhub_sla_*` and
`poolhub_sla_*` series below are planned, not exported** — do not build
alerts on them. The alert rules further down reference these nonexistent
series and would never fire.

### Alert Rules

Example Prometheus alert rules:

```yaml
groups:
  - name: poolhub_sla
    rules:
      - alert: HighSLAViolationRate
        expr: rate(poolhub_sla_violations_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: High SLA violation rate

      - alert: LowMinerUptime
        expr: poolhub_sla_uptime_pct < 95
        for: 5m
        labels:
          severity: high
        annotations:
          summary: Miner uptime below threshold

      - alert: HighResponseTime
        expr: poolhub_sla_response_time_ms > 1000
        for: 5m
        labels:
          severity: high
        annotations:
          summary: Response time above threshold
```

## Troubleshooting

### SLA Metrics Not Recording

**Symptom**: SLA metrics are not being recorded in the database

**Solutions**:

1. Check SLA collector is running: `ps aux | grep sla_collector`
2. Verify database connection: Check pool-hub database logs
3. Check SLA collection interval: Ensure `sla_collection_interval_seconds` is configured
4. Verify miner heartbeats: Check `miner_status.last_heartbeat_at` is being updated

### Capacity Alerts Not Triggering

**Symptom**: Capacity alerts are not being generated

**Solutions**:

1. Verify capacity snapshots are being created: Check `capacity_snapshots` table
2. Check alert thresholds: Ensure `capacity_alert_threshold_pct` is configured
3. Verify alert configuration: Check alert configuration endpoint
4. Review coordinator-api capacity planning: Ensure it's receiving pool-hub data

## Testing

Run the SLA integration tests:

```bash
cd apps/pool-hub

# Run all SLA tests
pytest tests/test_sla_collector.py

# Run with coverage
pytest --cov=poolhub.services.sla_collector tests/test_sla_collector.py
```

## Best Practices

1. **Monitor SLA Metrics Regularly**: Set up automated monitoring dashboards to track SLA metrics in real-time
2. **Configure Appropriate Thresholds**: Adjust SLA thresholds based on your service requirements
3. **Review Violations Promptly**: Investigate and resolve SLA violations quickly to maintain service quality
4. **Plan Capacity Proactively**: Use capacity forecasting to anticipate scaling needs
5. **Keep Documentation Updated**: Maintain up-to-date documentation for SLA configurations and procedures

## Integration with Existing Systems

### Coordinator-API Integration

Pool-hub reads coordinator service-registry data over HTTP for validation
(`services/validation.py`, via `POOLHUB_COORDINATOR_BILLING_URL`). The former
usage-billing integration was removed in #3077: it posted to
`/api/billing/usage`, a route coordinator-api does not serve, so every event
was dropped while looking recorded. Any future billing export needs a real
coordinator-api route first.

1. **Capacity Planning**: Pool-hub provides capacity data to coordinator-api's capacity planning system

### Prometheus Integration

SLA metrics are automatically exposed to Prometheus:

- Metrics are labeled by miner_id, metric_type, and other dimensions
- Use Prometheus query language to create custom dashboards
- Set up alert rules based on SLA thresholds

### Alerting Integration

SLA violations can trigger alerts through:

- Prometheus Alertmanager
- Custom webhook integrations
- Email notifications (via coordinator-api)
- Slack/Discord integrations (via coordinator-api)

## Security Considerations

1. **API Key Security**: Store coordinator API credentials securely (use environment variables or secret management)
2. **Database Access**: Ensure database connections use SSL/TLS in production
3. **Audit Logging**: Enable audit logging for SLA operations
4. **Access Control**: Restrict access to SLA endpoints to authorized users

## Performance Considerations

1. **Index Optimization**: Ensure database indexes are properly configured for SLA queries
2. **Caching**: Use Redis caching for frequently accessed SLA metrics
3. **Async Processing**: Use async operations for SLA collection
4. **Data Retention**: Implement data retention policies for SLA metrics and capacity snapshots

## Maintenance

### Regular Tasks

1. **Review SLA Thresholds**: Quarterly review and adjust SLA thresholds based on service performance
2. **Clean Up Old Data**: Regularly clean up old SLA metrics and capacity snapshots (e.g., keep 90 days)
3. **Review Capacity Forecasts**: Monthly review of capacity forecasts and scaling recommendations
4. **Update Documentation**: Keep documentation updated with any configuration changes

### Backup and Recovery

1. **Database Backups**: Ensure regular backups of SLA tables
2. **Configuration Backups**: Backup configuration files and environment variables
3. **Recovery Procedures**: Document recovery procedures for SLA systems
4. **Testing Backups**: Regularly test backup and recovery procedures

## References

- [Pool-Hub README](../../apps/pool-hub/README.md)
- [Coordinator-API Documentation](../../apps/coordinator-api/README.md)
- Roadmap
- Deployment Guide
